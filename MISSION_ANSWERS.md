# Day 14 Lab — Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns phát hiện trong `01-localhost-vs-production/develop/app.py`

1. **Hardcode secrets trong mã nguồn (dòng 17–18):** `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`. Nếu push lên GitHub, secret bị lộ ngay lập tức và nằm vĩnh viễn trong lịch sử git.
2. **In secret ra log bằng `print()` (dòng 33–38):** dùng `print()` không có cấu trúc, không có mức log/timestamp, đặc biệt dòng 34 còn in trực tiếp `OPENAI_API_KEY` ra stdout.
3. **Không quản lý cấu hình theo môi trường (dòng 21–22):** `DEBUG = True`, `MAX_TOKENS = 500` được gán cứng trong code, không đọc từ environment variables nên không thể đổi cấu hình giữa dev/staging/prod mà không sửa code.
4. **Không có health check / readiness endpoint (dòng 42–43):** thiếu `/health` và `/ready`, nên cloud platform hoặc load balancer không biết container còn sống hay đã sẵn sàng nhận traffic để tự restart / ngắt route.
5. **Bind `host="localhost"`, cứng `port=8000` và bật `reload=True` (dòng 49–53):** `host="localhost"` chỉ nhận kết nối nội bộ nên chạy trong Docker/cloud không truy cập được từ ngoài; `port=8000` không đọc biến `PORT` do Railway/Render cấp; `reload=True` gây tốn tài nguyên và không ổn định trên production.
6. **Không xử lý Graceful Shutdown:** thiếu `lifespan` hoặc xử lý `SIGTERM`, khi tắt server sẽ cắt ngang các request đang xử lý.

### Exercise 1.2: Kết quả chạy bản `develop`

Lệnh chạy:
```bash
curl -sS -i -X POST "http://127.0.0.1:8000/ask?question=Hello"
```

Kết quả đo thực tế:
```http
HTTP/1.1 200 OK
date: Fri, 27 Nov 2026 02:33:54 GMT
server: uvicorn
content-length: 126
content-type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

### Exercise 1.3: Bảng so sánh `develop` vs `production`

| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Tại sao quan trọng? |
| --- | --- | --- | --- |
| **Config & Secrets** | Hardcode trực tiếp (`OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG=True`, dòng 17–22) | Đọc từ biến môi trường qua `config.settings` (dòng 24, 51–54) | Tránh lộ secret lên Git; dùng chung 1 artifact/image cho dev, staging, production theo chuẩn 12-Factor. |
| **Health & Readiness** | Không có endpoint `/health`, `/ready` | Có `GET /health` (liveness, dòng 135–149) và `GET /ready` (readiness, trả 503 khi chưa sẵn sàng, dòng 152–161) | Platform tự phát hiện container chết để restart (`/health`) và Load Balancer chỉ route traffic tới instance sẵn sàng (`/ready`). |
| **Logging** | `print("[DEBUG] ...")`, thậm chí in cả `OPENAI_API_KEY` (dòng 33–38) | Structured JSON logging qua `logging` + `json.dumps` (dòng 28–32, 111–122), không log secret | Dễ thu thập, tìm kiếm, lọc và vẽ cảnh báo trên hệ thống log tập trung (Loki, Datadog, Cloud Logging) và không làm lộ thông tin nhạy cảm. |
| **Shutdown** | Tắt đột ngột, không dọn dẹp | Có `lifespan` (dòng 39–68) đặt `is_ready = False` trước khi tắt và xử lý `SIGTERM` (dòng 180–189) | Cho phép các request đang xử lý (in-flight) hoàn thành trước khi thoát, tránh lỗi 502/mất dữ liệu khi rolling deploy. |
| **Network Binding & Port** | `host="localhost"`, `port=8000`, `reload=True` (dòng 51–53) | `host=settings.host` (`0.0.0.0`), `port=settings.port` (đọc `PORT`), `reload=settings.debug` (dòng 194–199) | Container/cloud bắt buộc lắng nghe trên `0.0.0.0` và cổng `PORT` do nền tảng cấp; không bật auto-reload ở production. |
| **CORS & Validation** | Không có CORS, nhận `question` qua query param | Có `CORSMiddleware` giới hạn `allowed_origins` (dòng 77–82), validate body JSON trả 422 khi thiếu `question` (dòng 107–108) | Kiểm soát origin được phép gọi API và trả mã lỗi chuẩn rõ ràng khi input không hợp lệ. |

---

## Part 2: Docker Containerization

### Exercise 2.1: Trả lời 4 câu hỏi về `02-docker/develop/Dockerfile`

1. **Base image là gì?** `python:3.11` (dòng 8) — bản Python đầy đủ kèm Debian và nhiều công cụ build/hệ thống (~1 GB trở lên).
2. **Working directory là gì?** `/app` (dòng 11: `WORKDIR /app`) — mọi lệnh `COPY`, `RUN`, `CMD` sau đó thực thi trong thư mục này.
3. **Tại sao `COPY requirements.txt` trước `COPY app.py`?** Để tận dụng **Docker layer cache**. `requirements.txt` ít thay đổi hơn mã nguồn; nếu chỉ sửa `app.py`, Docker tái sử dụng cache của layer `RUN pip install -r requirements.txt` mà không phải tải và cài lại toàn bộ thư viện.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?** `CMD` định nghĩa lệnh mặc định (có thể bị ghi đè dễ dàng khi truyền lệnh ở cuối `docker run <image> <cmd>`), còn `ENTRYPOINT` cố định file thực thi chính của container (các tham số truyền thêm trong `docker run` sẽ được nối làm đối số cho `ENTRYPOINT`).

### Exercise 2.2: Build và chạy container `my-agent:develop`

Lệnh build từ gốc repo và gọi thử container:
```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --rm -p 8000:8000 my-agent:develop
curl -sS -i -X POST "http://127.0.0.1:8000/ask?question=What%20is%20Docker%3F"
```

Kết quả:
```http
HTTP/1.1 200 OK
date: Fri, 27 Nov 2026 02:35:46 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3: So sánh kích thước image (Multi-stage build)

- **Stage 1 (`builder`):** dùng `python:3.11-slim`, cài `gcc`, `libpq-dev` và biên dịch/cài dependencies vào `/root/.local`.
- **Stage 2 (`runtime`):** bắt đầu lại từ `python:3.11-slim` sạch, tạo non-root user `appuser`, chỉ `COPY --from=builder /root/.local` và mã nguồn sang, thêm `HEALTHCHECK` và chạy `uvicorn`.
- **Lý do image nhỏ hơn:** loại bỏ hoàn toàn compiler (`gcc`), header C (`libpq-dev`), cache pip và dùng base `slim` thay vì `python:3.11` bản full.

Kết quả đo thật bằng `docker images` và `docker image inspect`:
```text
REPOSITORY   TAG        SIZE
my-agent     advanced   240MB
my-agent     develop    1.67GB
```
- **Develop (`my-agent:develop`):** `1,667.8 MB` (`1,590.5 MiB` / `1.67 GB`)
- **Production (`my-agent:advanced`):** `239.8 MB` (`228.7 MiB` / `240 MB`)
- **Chênh lệch:** giảm **85.6%** dung lượng (nhỏ hơn gần 7 lần).

### Exercise 2.4: Docker Compose stack (`02-docker/production`)

**Kiến trúc các service trong mạng nội bộ `internal`:**
```text
Client ──► Nginx (:80 / :443) ──► Agent (:8000, không expose ra host)
                                     ├──► Redis (:6379, volume redis_data)
                                     └──► Qdrant (:6333, volume qdrant_data)
```

- Các service khởi chạy: `nginx` (reverse proxy, cổng 80/443), `agent` (FastAPI, chỉ nằm trong mạng `internal`, `depends_on` `redis` & `qdrant` healthy), `redis` (`redis:7-alpine`, cache/session), `qdrant` (`qdrant/qdrant:v1.9.0`, vector database).

**Kết quả test qua Nginx:**
```http
# GET http://localhost/health
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":1.0,"version":"2.0.0","timestamp":"2026-11-27T02:36:17.006029"}

# POST http://localhost/ask
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy Agent Part 6 lên Cloud

- **Nền tảng chính:** **Railway** (deploy thư mục `06-lab-complete/` kèm **Redis** database trên cùng project, dùng `railway.toml` + multi-stage `Dockerfile`, đặt đủ biến môi trường trên Railway Dashboard).
- **Public URL:** https://k5-l3b-day14-nguyenanhquan-2a202603950-deploymen-production.up.railway.app (chi tiết xem [DEPLOYMENT.md](DEPLOYMENT.md))
- **Kết quả tự kiểm 4 lệnh CP6 (không lộ key):**
  - `GET /health` → **`200`** (`{"status":"ok","environment":"production"}`)
  - `GET /ready` → **`200`** (`{"status":"ready","redis":"connected"}`)
  - `POST /ask` (không có `X-API-Key`) → **`401`** (`{"detail":"Invalid or missing API key"}`)
  - `POST /ask` (có `X-API-Key: $AGENT_API_KEY`) → **`200`** (`{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","user_id":null,"cost_usd":1.05e-05}`)
- **Screenshots:** [dashboard.png](screenshots/dashboard.png), [running.png](screenshots/running.png), [test.png](screenshots/test.png)

### So sánh `railway.toml` vs `render.yaml`

| Tiêu chí | `railway.toml` (Railway) | `render.yaml` (Render Blueprint) | Vì sao khác nhau? |
| --- | --- | --- | --- |
| **Định dạng & phạm vi** | TOML, cấu hình build & deploy cho **1 service** (`[build]`, `[deploy]`). | YAML, chuẩn **Infrastructure as Code (IaC)** khai báo được **nhiều service** (`services:` gồm cả `web` và `redis`) trong 1 file. | Render Blueprint hướng tới khai báo cả stack (app + Redis + disk) trong git, còn Railway quản lý các service (như Redis add-on) độc lập trên project canvas / CLI. |
| **Cấu hình build** | `builder = "DOCKERFILE"` hoặc `"NIXPACKS"`, `dockerfilePath`. | `runtime: docker` (hoặc `python` kèm `buildCommand`, `startCommand`). | Railway dùng Nixpacks/Dockerfile tự động hóa cao; Render cho khai báo rõ `runtime`, `region`, `plan` (`free`/`starter`...). |
| **Health check & Restart** | `healthcheckPath = "/health"`, `healthcheckTimeout = 30`, `restartPolicyType = "ON_FAILURE"`, `restartPolicyMaxRetries = 3`. | `healthCheckPath: /health`, `autoDeploy: true`. | Cả hai đều cần đường dẫn health check cho zero-downtime deploy, nhưng Railway cho tinh chỉnh trực tiếp retry policy ngay trong file TOML. |
| **Quản lý biến môi trường & secret** | Không khai báo env vars trong `railway.toml`; đặt qua Dashboard hoặc `railway variables set`. | Khai báo ngay trong `envVars:` của `render.yaml`, dùng `generateValue: true` (tự sinh random secret) hoặc `sync: false` (nhập tay trên Dashboard). | Giúp tránh lộ secret trong git nhưng Render vẫn đồng bộ danh sách tên biến cần thiết ngay trong file Blueprint. |

### Exercise 3.3: Tóm tắt CI/CD pipeline GCP Cloud Run (`03-cloud-deployment/production-cloud-run/`)

Pipeline trong `cloudbuild.yaml` tự động chạy 4 bước tuần tự khi push lên `main`: **(1) `test`** dùng `python:3.11-slim` cài dependencies và chạy `pytest`; **(2) `build`** đóng gói Docker image gắn tag `$COMMIT_SHA` và `latest` (tận dụng `--cache-from`); **(3) `push`** đẩy toàn bộ tag lên Container Registry (`gcr.io/$PROJECT_ID/ai-agent`); **(4) `deploy`** dùng `gcloud run deploy` triển khai image vừa build lên Cloud Run tại `asia-southeast1` với `min-instances=1` (tránh cold start), `max-instances=10`, `512Mi` RAM và nạp secret từ Secret Manager. File `service.yaml` định nghĩa cấu hình dịch vụ dạng Knative IaC tương ứng gồm autoscaling (`containerConcurrency: 80`), resource limits/requests, `secretKeyRef`, cùng `livenessProbe` (`/health`) và `startupProbe` (`/ready`).

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop`)

- **Vị trí kiểm tra:** Dependency `verify_api_key` đọc header `X-API-Key` qua `APIKeyHeader(name="X-API-Key", auto_error=False)` và được gắn vào `/ask` bằng `Depends(verify_api_key)`.
- **Khi thiếu hoặc sai key:** thiếu key → `401 Unauthorized`; sai key → `403 Forbidden` (ở Part 6 chuẩn hoá đều trả `401`).
- **Cách rotate key an toàn:** không hardcode key; hỗ trợ chấp nhận song song 2 key (`CURRENT_KEY` và `PREVIOUS_KEY`) trong giai đoạn chuyển tiếp qua biến môi trường trên cloud, cập nhật client sang key mới rồi gỡ key cũ.

**Kết quả test thật (`AGENT_API_KEY=secret-key-123`):**
```http
# Không có API key → 401
HTTP/1.1 401 Unauthorized
date: Fri, 27 Nov 2026 02:33:56 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# Có API key hợp lệ → 200
HTTP/1.1 200 OK
date: Fri, 27 Nov 2026 02:33:56 GMT
server: uvicorn
content-length: 122
content-type: application/json

{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production`)

- **Thuật toán Rate Limiting trong `rate_limiter.py`:** **Sliding Window Counter** (dùng `deque` lưu timestamp các request trong cửa sổ `window_seconds = 60`, loại bỏ các timestamp cũ hơn `now - 60`).
- **Giới hạn:** `rate_limiter_user` = **10 requests/phút** (tài khoản `student`), `rate_limiter_admin` = **100 requests/phút** (tài khoản `admin`).
- **Bypass / nâng giới hạn cho admin:** kiểm tra `role` giải mã từ JWT payload để chọn limiter riêng (`rate_limiter_admin`) hoặc bỏ qua check với role đặc quyền.

**Kết quả test thật (`POST /auth/token` với `student` / `demo123`, token đã che):**
```text
JWT acquired (masked): eyJhbGciOiJI...[REDACTED]
```
```http
# Request 1 với Bearer JWT → 200
HTTP/1.1 200 OK
date: Fri, 27 Nov 2026 02:33:59 GMT
server: uvicorn
content-length: 192
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block

{"question":"Explain JWT","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}

# Request 2..10: HTTP 200

# Request 11 vượt giới hạn 10 req/phút → 429
HTTP/1.1 429 Too Many Requests
date: Fri, 27 Nov 2026 02:34:00 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795746901
retry-after: 59
content-length: 98
content-type: application/json

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cách cài đặt Cost Guard & vì sao cần cả Rate Limit lẫn Cost Guard

- **Cách thiết kế Cost Guard với Redis:**
  - Dùng khóa theo ngày/tháng như `cost:daily:YYYY-MM-DD` và `cost:monthly:YYYY-MM` (hoặc theo user `budget:<user_id>:YYYY-MM`).
  - **Trước khi gọi LLM (`check_budget`):** đọc tổng chi phí hiện tại từ Redis; nếu `spent >= budget_usd` thì chặn ngay với `HTTP 402 Payment Required` (không gọi LLM, không phát sinh chi phí).
  - **Sau khi gọi LLM (`record_cost`):** tính chi phí theo số `input_tokens` × giá input + `output_tokens` × giá output, cộng dồn atomic bằng `INCRBYFLOAT` và đặt `EXPIRE` tự động reset chu kỳ sau (2 ngày cho daily, 35 ngày cho monthly).
- **Vì sao cần cả hai:** Rate limit chỉ bảo vệ **tốc độ request** (chống spam/DDoS, tránh quá tải server), nhưng 1 request prompt rất dài hoặc dùng model đắt vẫn có thể tốn rất nhiều tiền trong khi vẫn dưới ngưỡng req/phút. Ngược lại, Cost Guard bảo vệ **ngân sách (tiền)** theo token/USD để tránh hóa đơn LLM tăng đột biến.

---

## Part 5: Scaling & Reliability

### Exercise 5.1–5.3: Health/Readiness, Graceful Shutdown và Stateless Design

- **Liveness (`/health`) vs Readiness (`/ready`):**
  - `/health` kiểm tra process còn sống không → nếu fail, platform **restart container**. Kể cả khi Redis tạm mất kết nối, `/health` vẫn phải trả `200` để tránh restart vòng lặp vô ích.
  - `/ready` kiểm tra các dependency thiết yếu (như `redis.ping()`) → nếu fail trả `503 Service Unavailable` để Load Balancer tạm **ngừng gửi traffic** vào instance đó mà không kill container.
- **Graceful Shutdown (`SIGTERM`):** khi orchestrator (Docker/K8s/Railway) muốn tắt hoặc rolling deploy, nó gửi `SIGTERM` trước khi gửi `SIGKILL`. App ngừng nhận kết nối mới, chờ các request in-flight xử lý xong và đóng kết nối Redis sạch sẽ rồi thoát với exit code `0`, tránh cắt ngang request người dùng.
- **Stateless Design:** không lưu session, rate-limit counter hay budget trong RAM của từng process, vì khi chạy nhiều instance (hoặc nhiều worker), mỗi request có thể được Load Balancer chuyển đến một instance khác nhau → mất lịch sử chat và đếm sai rate limit. Chuyển toàn bộ state sang **Redis** giúp mọi instance chia sẻ cùng trạng thái và sống sót qua việc restart/scale.

### Exercise 5.4 & 5.5: Chạy stack 3 instance với Nginx + Redis và test stateless

Lệnh chạy trong `05-scaling-reliability/production/`:
```bash
docker compose -p k5-day14-scaling up -d --build --scale agent=3
python test_stateless.py
docker compose -p k5-day14-scaling down
```

**Kết quả thực tế từ `test_stateless.py` (cổng `8080`, endpoint `POST /chat`):**
```text
============================================================
Stateless Scaling Demo
============================================================

Session ID: 60936210-18ed-460f-9058-831ce904bb28

Request 1: [instance-4ea1a3]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-638431]
  Q: Why do we need containers?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 3: [instance-36d240]
  Q: What is Kubernetes?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 4: [instance-4ea1a3]
  Q: How does load balancing work?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

Request 5: [instance-638431]
  Q: What is Redis used for?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-36d240', 'instance-4ea1a3', 'instance-638431'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: What is Kubernetes?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: How does load balancing work?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...
  [user]: What is Redis used for?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...

✅ Session history preserved across all instances via Redis!
```

**Giải thích:** 5 request trong cùng một `session_id` được Nginx phân phối lần lượt (round-robin) cho cả 3 container agent khác nhau (`instance-4ea1a3`, `instance-638431`, `instance-36d240`), nhưng khi gọi `GET /chat/{session_id}/history` vẫn đọc đủ **10 tin nhắn** (5 câu hỏi + 5 câu trả lời) vì toàn bộ lịch sử được lưu tập trung trong Redis.

---

## Part 6: Final Project — Output `check_production_ready.py`

Chạy trong WSL2 (`os.name == 'posix'`) tại `06-lab-complete/` với Docker Desktop đang hoạt động:
- Docker image size đo được: **238 MB** (< 500 MB), build trong 29s.
- Graceful shutdown: SIGTERM in-flight request trả `200`, `docker stop` thoát với **exit code 0 trong 0.7s**.

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log

Theo quy định tại `RULES.md`:

1. **Thiết lập môi trường WSL2 & Docker:** Dùng trợ lý AI (Antigravity / Gemini) kiểm tra môi trường Windows, tạo user Ubuntu WSL2, thiết lập virtualenv Python và cài đặt các gói thư viện cần thiết. Tự khởi động lại máy, mở Docker Desktop và bật WSL Integration, sau đó kiểm chứng bằng `python -c "import os; print(os.name)"` (`posix`) và `docker info`.
2. **Viết code Part 6 (`06-lab-complete/`):** Tham khảo AI cấu trúc các module `config.py`, `redis_client.py`, `auth.py`, `rate_limiter.py` (Lua sliding window trong Redis), `cost_guard.py`, `main.py` (JSON logger + lifespan), `Dockerfile` multi-stage, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`. Đã kiểm tra và xác nhận đạt `PASS 12/12 (43/43 checks passed)` bằng lệnh thật `python check_production_ready.py` trong WSL2 + Docker.
3. **Thực nghiệm Part 1, 2, 4, 5 & Part 7:** Dùng AI hỗ trợ viết script chạy tự động các lệnh thực nghiệm trong bài và định dạng báo cáo `MISSION_ANSWERS.md` / `BENCHMARK_REPORT.md`. Toàn bộ số liệu (kích thước image `1.67 GB` vs `240 MB`, output `curl -i` mã `401/200/429`, kết quả `test_stateless.py`, toàn bộ file JSON/CSV Part 7 và ảnh chụp) đều thu từ lệnh chạy thực tế trên máy, không bịa số liệu.
