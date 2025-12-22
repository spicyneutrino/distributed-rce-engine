import io
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from minio import Minio
import pika
import uuid
import json
import os
from dotenv import load_dotenv

# Import our local modules
from .database import engine, get_db, Base
from .models import Job

load_dotenv()

Base.metadata.create_all(engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

minio_client = Minio(
    os.getenv("MINIO_ENDPOINT"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
    secure=os.getenv("MINIO_SECURE") == "True"
)

BUCKET_NAME = "code-uploads"

if not minio_client.bucket_exists(BUCKET_NAME):
    minio_client.make_bucket(BUCKET_NAME)
    
def publish_message(job_id: str):
    credentials = pika.PlainCredentials(os.getenv("RABBITMQ_USER"), os.getenv("RABBITMQ_PASS"))
    parameters = pika.ConnectionParameters(host = os.getenv("RABBITMQ_HOST"), credentials=credentials)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    
    channel.queue_declare(queue='job_queue', durable=True)
    
    channel.basic_publish(
        exchange='',
        routing_key="job_queue",
        body= json.dumps({"job_id": job_id}),
        properties= pika.BasicProperties(
            delivery_mode=2
        )
    )
    connection.close()
    
# Endpoints

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("static/index.html") as f:
        return f.read()
    

@app.post("/submit")
async def submit_job(file: UploadFile = File(...), db: Session = Depends(get_db)):
    
    job_id = str(uuid.uuid4())
    
    try:
        content = await file.read() 
        
        minio_client.put_object(
            BUCKET_NAME,
            job_id,
            io.BytesIO(content),
            length = len(content),
            part_size = 10*1024*1024
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MinIO Upload Failed: {str(e)}")
    
    
    new_job = Job(id=job_id, filename = file.filename, status = "QUEUED")
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    
    try:
        publish_message(job_id)
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
    