from locust import HttpUser, task, between
import random

class RCEUser(HttpUser):
    # Wait 1-5 seconds between jobs
    wait_time = between(1, 5)
    host = "http://localhost:8000"

    @task(5) # 5 times: Simple print (Fast I/O test)
    def hello_world(self):
        self.submit_job("print('Hello from the fast lane!')")

    @task(1) # 1 times: CPU Stress Test (Factorial)
    def cpu_stress(self):
        # Calculates factorial of 5000 (CPU heavy, fast RAM usage)
        code = """
import sys
sys.set_int_max_str_digits(100000)
import math
print(f"Factorial of 5000 is {len(str(math.factorial(5000)))} digits long")
"""
        self.submit_job(code)

    def submit_job(self, script_content):
        files = {'file': ('test.py', script_content, 'text/x-python')}
        with self.client.post("/submit", files=files, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed with {response.status_code}")