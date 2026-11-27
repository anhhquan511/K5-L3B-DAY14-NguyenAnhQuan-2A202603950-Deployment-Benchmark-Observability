# Deployment Information

## Public URL
https://k5-l3b-day14-nguyenanhquan-2a202603950-deploymen-production.up.railway.app

## Platform
**Railway** (project `lucky-energy`, environment `production`, root directory `06-lab-complete`, config `railway.toml` + multi-stage `Dockerfile`, linked with Railway **Redis** service)

## Test Commands (CP6 Verification)

Đặt biến môi trường trước khi chạy (không ghi key thật vào tài liệu/repo):

```bash
export BASE="https://k5-l3b-day14-nguyenanhquan-2a202603950-deploymen-production.up.railway.app"
export AGENT_API_KEY="<YOUR_RAILWAY_AGENT_API_KEY>"
```

### 1. Kiểm tra 4 mã HTTP chuẩn CP6

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"                                                                                 # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"                                                                                  # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'             # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'  # 200
```

### 2. Health Check (`GET /health`)

```bash
curl -sS "$BASE/health"
# Kết quả thực tế:
# {"status":"ok","environment":"production"}
```

### 3. Readiness Check (`GET /ready` — kiểm tra kết nối Redis trên cloud)

```bash
curl -sS "$BASE/ready"
# Kết quả thực tế:
# {"status":"ready","redis":"connected"}
```

### 4. API Test — Không có API Key (401) & Có API Key (200)

```bash
# Không có API key → 401
curl -sS -X POST "$BASE/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# Kết quả thực tế:
# {"detail":"Invalid or missing API key"}

# Có API key hợp lệ → 200
curl -sS -X POST "$BASE/ask" \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
# Kết quả thực tế:
# {"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","user_id":null,"cost_usd":1.05e-05}
```

## Environment Variables Set (trên Railway Dashboard)
- `PORT` (do Railway tự inject: `8080`, Public Networking target port: `8080`)
- `REDIS_URL` (`${{Redis.REDIS_URL}}` — trỏ tới Railway Redis service)
- `AGENT_API_KEY` (đặt trực tiếp trên Railway Variables, không lưu trong code/git)
- `ENVIRONMENT` (`production`)
- `LOG_LEVEL` (`INFO`)
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`10.0`)
- `MONTHLY_BUDGET_USD` (`10.0`)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running & logs](screenshots/running.png)
- [CP6 API test results](screenshots/test.png)
