# Distributed Remote Code Execution (RCE) Engine

> **A high-performance, distributed compute engine designed to execute untrusted code in secure, ephemeral sandboxes. Capable of handling 500+ concurrent users with sub-30ms latency.**

## Engineering Impact

This system was engineered to simulate a production-grade coding platform (like LeetCode). It prioritizes **security** and **hardware saturation** over simple functionality.

* **Concurrency:** Successfully handled **500 concurrent users** without degradation by implementing SQLAlchemy connection pooling and async worker scaling.
* **Throughput:** Scaled to **168 RPS** (~14.5M requests/day) on single-node consumer hardware.
* **Latency Optimization:** Reduced median API latency from **2.6s** to **24ms** (99% reduction) by refactoring blocking I/O into non-blocking async threads.
* **Reliability:** Decoupled execution logic using **RabbitMQ**, ensuring zero lost jobs even during worker crashes.
* **Security:** Implemented "Defense in Depth" using **Rootless Podman**, Air-Gapping, and Seccomp Kernel Filters.

---

##  System Architecture

**[INSERT FIGURE 1 HERE: High-Level Architecture Diagram]**

### The Workflow

1. **Ingestion:** Client submits code → **FastAPI** validates payload.
2. **Persistence:** Code acts as a blob and is offloaded to **MinIO** (S3-compatible) via a non-blocking ThreadPool. Metadata is stored in **PostgreSQL**.
3. **Queuing:** Job ID is pushed to **RabbitMQ** (Topic Exchange). API immediately acknowledges receipt (Async pattern).
4. **Execution:** **Worker Service** (Stateless) pulls job, spawns a **Rootless Podman** container, pipes code via Stdin, and captures output.
5. **Streaming:** Logs are streamed back to the user in real-time via **WebSockets**.

---

## Architectural Decisions (Why I built it this way)

| Decision | Alternative | Why I chose this path |
| --- | --- | --- |
| **RabbitMQ** | Redis Pub/Sub | **Durability.** Redis is faster but fires-and-forgets. RabbitMQ ensures that if a worker crashes, the job is not lost but redelivered. |
| **Podman** | Docker | **Security.** Docker requires a root daemon (`root` privileges). Podman is daemonless and rootless, significantly reducing the blast radius of a container escape. |
| **Stdin Piping** | Volume Mounts | **Atomicity.** Mounting temp files caused race conditions and "Invalid Reference" errors on the host. Piping code via Standard Input (stdin) keeps the entire execution in memory and stateless. |

---

## Security: Defense in Depth

Executing arbitrary user code is inherently dangerous. This system assumes **all code is malicious**.

| Layer | Protection | Mechanism |
| --- | --- | --- |
| **1. Static Analysis** | **AST Linter** | Parses the Abstract Syntax Tree to block dangerous imports (`os`, `subprocess`) *before* the container even starts. |
| **2. Network Gap** | **`--net=none`** | The container has no network interface. It cannot download malware, open reverse shells, or scan the internal network. |
| **3. Capability Drop** | **`--cap-drop=ALL`** | Drops all Linux capabilities (e.g., `CAP_CHOWN`, `CAP_KILL`). Even as "root" inside the container, the process is powerless. |
| **4. Kernel Sandbox** | **Seccomp** | Applies a custom BPF filter to the Linux Kernel, rejecting dangerous syscalls (`ptrace`, `kexec_load`) at the OS level. |

---

## Performance Optimization

**The Bottleneck:**
Initial load testing with **Locust** showed a hard cap at **109 RPS**. Telemetry (Prometheus) indicated the Event Loop was blocking during file uploads, and at **200 concurrent users**, the database began rejecting connections.

**The Solution:**

1. **I/O Blocking:** Moved MinIO upload operations to a `ThreadPoolExecutor` (100 workers).
2. **Connection Starvation:** Implemented aggressive **SQLAlchemy Connection Pooling** with overflow protection.

**The Results:**
| Metric | Before Optimization | After Optimization |
| :--- | :--- | :--- |
| **Concurrency** | Crashed at 200 Users | **Stable at 500 Users** |
| **Median Latency** | 2,600ms | **24ms** |
| **Throughput** | 109 RPS | **168 RPS** |
| **Hardware State** | CPU Idle / I/O Wait | **100% SSD Saturation** |

*Note: The system successfully pushed the bottleneck from software logic to the physical limits of the NVMe drive.*

---

## How to Run

This project uses `podman-compose` for orchestration.

1. **Setup & Configure:**
```bash
git clone https://github.com/spicyneutrino/distributed-rce-engine.git
cd distributed-rce-engine
cp .env.example .env
uv sync
```

2. **Build the Sandbox Image:**

You must build the isolation image that acts as the runtime for untrusted code. The worker nodes rely on this image existing locally.
```bash
podman build -t rce-datascience ./images
```


3. **Launch System:**
```bash
podman-compose up --build
```


4. **Access:**
* **API Docs:** `http://localhost:8000/docs`
* **Grafana Dashboards:** `http://localhost:3000` (Default: admin/admin)

---

### Scaling
This application is designed to be stateless, allowing for horizontal scaling of both the API and Worker nodes.

**Using Podman Compose:**
You can scale the background workers to handle a higher volume of tasks using the `--scale` flag.
```bash
# Scale to 3 worker instances and 2 API instances
podman-compose up -d --scale worker=3 --scale api=2
```
 
 
**Note:** Ensure your infrastructure can support the increased connection count.


---

## Tech Stack

* **Compute:** Python 3.13, FastAPI, Uvicorn
* **Broker:** RabbitMQ (AMQP)
* **Database:** PostgreSQL, MinIO (Object Storage)
* **Runtime:** Podman (Rootless Containers)
* **Monitoring:** Prometheus, Grafana


---

## Testing & Performance

Currently, this project focuses on **Load Testing** to ensure the system scales effectively under traffic.

**Test Location:** `tests/locustfile.py`

### Running Load Tests

We use [Locust](https://locust.io) to simulate user traffic.

**1. Interactive Mode:**

```bash
locust -f tests/locustfile.py
```

* Access the dashboard at `http://localhost:8089`.

**2. Headless Mode (CLI):**

```bash
# Simulate 50 users, spawning 5/sec, for 1 minute
locust -f tests/locustfile.py --headless -u 50 -r 5 --run-time 1m --host http://localhost:8000
```


## Roadmap & Future Improvements
* [ ] **Testing Strategy:** Implement `pytest` for unit testing core logic to complement the current `locust` load tests.
* [ ] **CI/CD Pipeline:** Set up GitHub Actions to automate linting (flake8/black) and testing on pull requests.
* [ ] **Caching:** Integrate Redis caching to reduce database load under the high-traffic scenarios tested in Locust.
* [ ] **Orchestration:** Add Kubernetes manifests (k8s) for deploying the containerized workers in a production environment.
