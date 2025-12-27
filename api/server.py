import io
import uuid
import json
import os
import aio_pika
import asyncio
import functools
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from minio import Minio
from dotenv import load_dotenv
from prometheus_fastapi_instrumentator import Instrumentator

# Import local modules
from .database import engine, get_db, Base
from .models import Job

load_dotenv()

Base.metadata.create_all(engine)

import io
import uuid
import json
import os
import aio_pika
import asyncio
import functools
from contextlib import asynccontextmanager  # <--- NEW IMPORT
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from minio import Minio
from dotenv import load_dotenv
from prometheus_fastapi_instrumentator import Instrumentator

# Import our local modules
from .database import engine, get_db, Base
from .models import Job

load_dotenv()

Base.metadata.create_all(engine)

# --- GLOBAL VARIABLES ---
rabbitmq_connection = None
rabbitmq_channel = None
background_tasks = set()

# --- LIFESPAN MANAGER ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up application...")
    global rabbitmq_channel, rabbitmq_connection
    
    # Connect to RabbitMQ (Publisher)
    try:
        connection_str = f"amqp://{os.getenv('RABBITMQ_USER')}:{os.getenv('RABBITMQ_PASS')}@{os.getenv('RABBITMQ_HOST')}/"
        rabbitmq_connection = await aio_pika.connect_robust(connection_str)
        rabbitmq_channel = await rabbitmq_connection.channel()
        await rabbitmq_channel.declare_queue("job_queue", durable=True)
        print("Connected to RabbitMQ for publishing.")
    except Exception as e:
        print(f"Failed to connect to RabbitMQ: {e}")

    # Start Background Consumer (Listener)
    task = asyncio.create_task(consume_events())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    
    yield
    
    print("Shutting down Application")
    
    # Close RabbitMQ
    if rabbitmq_connection:
        await rabbitmq_connection.close()
        
    for task in background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

# --- APP INITIALIZATION ---
app = FastAPI(lifespan=lifespan)

Instrumentator().instrument(app).expose(app)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Websocket Manager
class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, job_id: str):
        await websocket.accept()
        self.active_connections[job_id] = websocket
    
    def disconnect(self, job_id: str):
        if job_id in self.active_connections:
            del self.active_connections[job_id]
    
    async def send_update(self, job_id: str, message: dict):
        if job_id in self.active_connections:
            websocket = self.active_connections[job_id]
            try:
                await websocket.send_json(message)
            except Exception as e:
                print(f"Error sending message to {job_id}: {e}")
                self.disconnect(job_id)

manager = ConnectionManager()

# Background RabbitMQ Consumer
async def consume_events():    
    try:
        connection_str = f"amqp://{os.getenv('RABBITMQ_USER')}:{os.getenv('RABBITMQ_PASS')}@{os.getenv('RABBITMQ_HOST')}/"
        connection = await aio_pika.connect_robust(connection_str)
        
        async with connection:
            channel = await connection.channel()   
            exchange = await channel.declare_exchange('job_events', aio_pika.ExchangeType.FANOUT)
            queue = await channel.declare_queue(exclusive=True)
            await queue.bind(exchange)
            
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process():
                        data = json.loads(message.body)
                        await manager.send_update(data['job_id'], data)
    except Exception as e:
        print(f"CRITICAL ERROR in Background Listener: {e}")

# --- MINNIO SETUP ---
minio_client = Minio(
    os.getenv("MINIO_ENDPOINT"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
    secure=os.getenv("MINIO_SECURE") == "True"
)
minio_executor = ThreadPoolExecutor(max_workers=100)
BUCKET_NAME = "code-uploads"

if not minio_client.bucket_exists(BUCKET_NAME):
    minio_client.make_bucket(BUCKET_NAME)
    
# --- ENDPOINTS ---

@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    await manager.connect(websocket, job_id)
    try:
        while True:
            await websocket.receive()
    except WebSocketDisconnect:
        manager.disconnect(job_id)

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("static/index.html") as f:
        return f.read()
    

@app.post("/submit")
async def submit_job(file: UploadFile = File(...), db: Session = Depends(get_db)):
    
    job_id = str(uuid.uuid4())
    
    try:
        content = await file.read() 
        
        # minio_client.put_object(
        #     BUCKET_NAME,
        #     job_id,
        #     io.BytesIO(content),
        #     length = len(content),
        #     part_size = 10*1024*1024
        # )
        
        # Get the running event loop
        loop = asyncio.get_running_loop()
        
        # Create a partial function to pass arguments to the blocking call
        upload_func = functools.partial(
            minio_client.put_object,
            BUCKET_NAME,
            job_id,
            io.BytesIO(content),
            length=len(content),
            part_size=10*1024*1024
        )
        # Run it in a separate thread so the main loop stays free
        await loop.run_in_executor(minio_executor, upload_func)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MinIO Upload Failed: {str(e)}")
    
    
    new_job = Job(id=job_id, filename = file.filename, status = "QUEUED")
    db.add(new_job)
    db.commit()
    # db.refresh(new_job)
    
    try:
        message_body = json.dumps({"job_id":job_id}).encode()
        await rabbitmq_channel.default_exchange.publish(
            aio_pika.Message(
                body=message_body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key="job_queue"
        )
    except Exception as e:
        print(f"CRITICAL: Failed to publish job{job_id} to RABBITMQ: {e}")
    
    return {"job_id": job_id, "status": "QUEUED"}

@app.get("/status/{job_id}")
def get_status(job_id: str, db: Session=Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job_id,
        "status": job.status,
        "submitted_at": job.created_at,
        "logs": job.logs
    }
    
# @app.get("/", reponse_class=HTMLResponse)
# async def read_root():
#     with open("static/index.html") as f:
#         return f.read()
    