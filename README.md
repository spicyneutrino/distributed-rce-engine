# Distributed Remote Code Execution (RCE) Engine

A scalable, secure, and asynchronous code execution engine built with Python, FastAPI, RabbitMQ, and Podman.

##  Features
* **Secure Isolation:** Executes untrusted Python code inside ephemeral **Podman** containers (Rootless & Daemonless).
* **Horizontal Scaling:** RabbitMQ distributes jobs across multiple worker nodes.
* **Asynchronous Processing:** Non-blocking API handles uploads while workers process in the background.
* **Defense in Depth:** Static Analysis (AST) blocks dangerous imports (`os`, `subprocess`) before execution.
* **Data Science Ready:** Custom container images support `numpy` and `pandas`.

##  Architecture
1.  **API (FastAPI):** Accepts code uploads and stores them in **MinIO** (S3 compatible).
2.  **Queue (RabbitMQ):** Publishes Job IDs to a durable task queue.
3.  **Worker:** Consumes jobs, pulls code from MinIO, and spins up a secure container.
4.  **Compute:** A custom Docker image (`rce-datascience`) executes the code.
5.  **Result:** Logs and status are saved to **PostgreSQL** and retrieved by the client.

##  Tech Stack
* **Language:** Python 3.9+
* **Containerization:** Podman (Docker compatible)
* **Orchestration:** Docker Compose / Podman Compose
* **Broker:** RabbitMQ
* **Database:** PostgreSQL
* **Storage:** MinIO

##  How to Run
1.  **Start Infrastructure:**
    ```bash
    podman-compose up -d
    ```
2.  **Build Compute Image:**
    ```bash
    podman build -t rce-datascience ./images
    ```
3.  **Start API:**
    ```bash
    uv run uvicorn api.server:app --reload
    ```
4.  **Start Worker:**
    ```bash
    uv run worker/main.py
    ```
5.  **Visit UI:**
    Open `http://localhost:8000` to submit jobs.