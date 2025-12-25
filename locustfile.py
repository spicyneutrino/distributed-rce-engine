from locust import HttpUser, task, between
import random

class RCEUser(HttpUser):
    wait_time = between(1,5)
    
    @task
    def submit_job(self):
        script_content = f"""
import time
import random
print("Load test job starting...")
time.sleep({random.uniform(0.1, 1.0)})
print("Job done!")
"""
        files = {
            'file': ("stress_test.py", script_content, 'text/x-python')
        }
        
        self.client.post("/submit", files=files)
