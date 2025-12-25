import pika
import json
import os
import sys
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from minio import Minio

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.models import Job
from api.database import SessionLocal
from worker.run_container import run_code_in_container
from worker.security import scan_code

load_dotenv()

# Setup Connections
BUCKET_NAME = "code-uploads"

minio_client = Minio(
    os.getenv("MINIO_ENDPOINT"),
    access_key= os.getenv("MINIO_ACCESS_KEY"),
    secret_key= os.getenv("MINIO_SECRET_KEY"),
    secure= os.getenv("MINIO_SECURE") == "True"
)

def  publish_event(ch, job_id, status, logs):
    message = json.dumps({
        "job_id": job_id,
        "status": status,
        "logs": logs
    })
    
    ch.exchange_declare(exchange="job_events", exchange_type="fanout")
    
    ch.basic_publish(
        exchange="job_events",
        routing_key='',
        body=message
    )
    

def process_job(ch, method, properties, body):
    data = json.loads(body)
    job_id = data.get("job_id")
    print(f" [x] Recieved Job: {job_id}")
    
    db: Session = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    
    if not job:
        print("Job not found in DB")
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return
    
    # Update Status -> Processing
    job.status = "PROCESSING"
    db.commit()
    
    try:
        response = minio_client.get_object(BUCKET_NAME, job_id)
        code_content = response.read()
        response.close()
        response.release_conn()
        
        # print(f"DEBUG: Downloaded Code for {job_id}: ")
        # print(code_content.decode('utf-8'))
        
        print(f"DEBUG: Checking security for job {job_id}...")
        scan_code(code_content)
        print(f"    Security Scan: PASSED")
        
        
        print("  Running container...")
        logs = run_code_in_container(code_content)
        
        job.logs = logs
        job.status = "COMPLETED"
        publish_event(ch,job_id, job.status, logs)
        print(f"    Finished. Result: {logs}...")
    
    except ValueError as sec_err:
        print(f"    Security/Syntax Violation: {sec_err}")
        job.status = "FAILED"
        job.logs = str(sec_err)
        publish_event(ch,job_id, job.status, f"    Security/Syntax Violation: {str(sec_err)}")
    
    except Exception as e:
        print(f"    Failed: {e}")
        job.status = "FAILED"
        job.logs = str(e)
        publish_event(ch, job_id, job.status, f"System Error: {str(e)}")
        
    finally:
        db.commit()
        db.close()
        
        ch.basic_ack(delivery_tag = method.delivery_tag)
        
def main():
    print(" [*] Worker connecting to RabbitMQ...")
    credentials = pika.PlainCredentials(os.getenv("RABBITMQ_USER"), os.getenv("RABBITMQ_PASS"))
    parameters = pika.ConnectionParameters(host=os.getenv("RABBITMQ_HOST"), credentials=credentials)
    
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    
    channel.queue_declare(queue="job_queue", durable=True)
    
    # Only handle 1 job at a time per worker
    channel.basic_qos(prefetch_count=1)
    
    channel.basic_consume(queue='job_queue', on_message_callback=process_job)
    
    print(" [*] Waiting for messages. To exit press CTRL+C")
    channel.start_consuming()
    
if __name__ == '__main__':
    main()