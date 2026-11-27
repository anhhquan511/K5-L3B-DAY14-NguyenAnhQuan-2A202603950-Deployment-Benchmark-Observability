# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được trích trực tiếp từ các file JSON trong `reports/`, CSV trong `benchmark-results/`, log JSON và screenshot trong `screenshots/`.

**Họ tên:** Nguyen Anh Quan (MSSV: 2A202603950)
**Ngày chạy:** 2026-11-27
**Môi trường:** Windows 11 + WSL2 Ubuntu (Python 3.14.4, `os.name == 'posix'`), Docker Desktop 29.9.3 / Docker Compose v5.7.1

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms | Đảm bảo 95% người dùng nhận phản hồi dưới nửa giây (trải nghiệm hội thoại mượt), không để tail latency của upstream che khuất bởi trung bình. |
| Error rate `/ask` | ≤ 2.0 % | Cho phép error budget 2% để hấp thụ lỗi ngẫu nhiên (~1%) từ LLM upstream mà vẫn duy trì độ tin cậy cao cho người dùng cuối. |
| Accuracy trên golden dataset | ≥ 85 % (mục tiêu ≥ 100% sau khi bổ sung KB, 0 regression) | Ngăn chặn suy giảm chất lượng trả lời khi thay đổi prompt, model hoặc knowledge base trước khi merge/deploy. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

*(Dữ liệu khớp 100% với `reports/load_v2_c1.json`, `load_v2_c10.json`, `load_v2_c50.json`, `load_v2_c100.json`; mỗi lần 300 requests, SLO p95 ≤ 500ms, error rate ≤ 2.0%)*

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.44 | 190.4 | 222.0 | 1703.2 | 0.33% | ✅ PASS |
| 10 | 36.09 | 193.1 | 221.9 | 1693.2 | 1.33% | ✅ PASS |
| 50 | 61.75 | 272.7 | 1739.2 | 2557.1 | 1.00% | ❌ FAIL (p95 > 500ms) |
| 100 | 51.46 | 852.4 | 3968.0 | 4604.6 | 1.67% | ❌ FAIL (p95 > 500ms) |

**Nhận xét:** RPS **không tăng tuyến tính** theo concurrency. Từ `c=1` lên `c=10`, RPS tăng gần tuyến tính (`4.44 → 36.09 req/s`) trong khi p50/p95 hầu như không đổi (`~193ms / ~222ms`) vì 1 process async còn dư năng lực xử lý các tác vụ I/O chờ LLM. Tuy nhiên từ `c=50` trở lên, hàng đợi event-loop/socket và các request bị tail latency tích tụ khiến tốc độ tăng RPS chững lại (`61.75 req/s`) và thậm chí giảm ở `c=100` (`51.46 req/s`) trong khi p95 vọt lên `1739.2 ms` rồi `3968.0 ms` (vượt SLO).

### 2.2 Tail latency

*(Dữ liệu khớp 100% với `reports/load_v2_slow_0.json`, `load_v2_slow_0.03.json`, `load_v2_slow_0.1.json`; mỗi lần 300 requests, `concurrency=20`)*

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 192.0 | 223.4 | 245.9 |
| 0.03 (mặc định) | 253.6 | 241.9 | 1709.2 |
| 0.1 | 339.5 | 1694.1 | 1717.6 |

**Nhận xét:** **p99 và p95** là hai chỉ số nhạy nhất với request chậm bất thường (tail latency):
- Khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03` (3% request chậm thêm ~1500ms), `avg` chỉ tăng nhẹ `+61.6 ms` (`192.0 → 253.6 ms`) nhưng **p99 nhảy vọt gần 7 lần** (`245.9 → 1709.2 ms`).
- Khi tăng lên `0.1` (10% request chậm > 5%), `avg` mới ở mức `339.5 ms` (nhìn qua tưởng vẫn dưới 500ms), nhưng **p95 đã nhảy lên `1694.1 ms`** và làm vi phạm SLO.
- Vì vậy, **SLO không bao giờ nên đặt theo average**, vì giá trị trung bình bị 90–97% request nhanh kéo xuống và che giấu hoàn toàn trải nghiệm tồi tệ của nhóm người dùng gặp tail latency.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

*(Dữ liệu khớp 100% với `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`; chạy trên `golden_dataset.jsonl` gồm 23 câu hỏi)*

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.8 | 108.7 | 113.8 |
| Tổng cost (USD) | $0.000414 | $0.000756 | $0.000792 |
| Cost / câu đúng (USD) | $0.00041355 | $0.00003599 | $0.00003443 |
| Latency p95 (ms) | 182.3 | 214.4 | 219.2 |
| Quality gate | ❌ FAIL | ✅ PASS (0 regression vs v1) | ✅ PASS (accuracy ≥ 100%, 0 regression vs v2) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry từ khoá `["jwt"]` vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`) giải thích sự khác biệt giữa API key và JWT (token có chữ ký số, chứa thông tin user và thời điểm hết hạn). |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry từ khoá `["hpa", "kubernetes", "autoscal"]` vào `KNOWLEDGE_BASE` mô tả Kubernetes HPA tự động scale pod dựa trên CPU, memory hoặc custom metrics (RPS, độ dài hàng đợi). |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- Agent v2 bổ sung bước retrieval (RAG) đưa ngữ cảnh vào prompt nên **tốn gần gấp đôi token/câu** (`108.7–113.8` vs `57.8`), tổng chi phí 23 câu tăng ~1.9× (`$0.000792` vs `$0.000414`) và latency p95 tăng thêm ~`32–37 ms` (do bước `search_knowledge_base` ~20ms + prompt dài hơn).
- Đổi lại, độ chính xác nhảy từ **4.3% lên 91.3% → 100.0%**. Khi tính theo **chi phí trên mỗi câu trả lời đúng (`cost / câu đúng`)**, v2 (`$0.00003443`) **rẻ hơn khoảng 12 lần** so với v1 (`$0.00041355`).

**Cách dùng exit code của `run_eval.py` làm Quality Gate trong CI:**
- Đã kiểm chứng trực tiếp: chạy `python eval/run_eval.py --url http://127.0.0.1:8001 --baseline reports/eval_v2.json` báo **20 câu regression**, `Quality gate ❌ FAIL` và trả về **exit code `1`**.
- Đã tạo workflow GitHub Actions tại `.github/workflows/eval.yml` chạy trên mỗi `pull_request`: tự khởi động agent v2, chạy `python eval/run_eval.py --min-accuracy 0.85 --baseline ../../../reports/eval_v2_fixed.json`. Nếu accuracy tụt dưới 85% hoặc có bất kỳ câu nào bị regression, script thoát với exit code `1` làm CI job fail và **chặn merge PR**.

---

## 4. Observability stack (production)

### 4.1 Screenshot & trả lời Exercise 7.4

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [`screenshots/grafana-dashboard.png`](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span chiếm thời gian): [`screenshots/jaeger-slow-trace.png`](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`): [`screenshots/jaeger-error-trace.png`](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với cả 4 alert đang **firing**: [`screenshots/prometheus-alert-firing.png`](screenshots/prometheus-alert-firing.png)

**Trả lời câu hỏi Exercise 7.1 & 7.4 (số liệu đo thực tế từ Grafana & Prometheus):**
1. **Exercise 7.1 — Phân loại metric & cardinality của label `route`:**
   - Ví dụ metric: **Counter** = `http_requests_total`, **Gauge** = `agent_in_flight_requests`, **Histogram** = `http_request_duration_seconds` và `agent_question_length_chars` (đã thêm vào `develop/app.py`).
   - Middleware `observe_requests` dùng `route.path` (template như `"/ask"`, không khớp gán `"unmatched"`) thay vì `request.url.path` thật để **chống bùng nổ cardinality**: nếu bot quét gọi hàng nghìn URL ngẫu nhiên (`/wp-admin`, `/.env`, `/a1b2c3`...), mỗi URL sẽ tạo thêm nhiều time series mới (đặc biệt với Histogram có 12+ bucket), làm Prometheus cạn RAM và chậm truy vấn.
2. **Exercise 7.4 — Đọc dashboard Grafana dưới tải:**
   - **Golden Signals (30 users):** Traffic `18.9 req/s`, Error rate `1.06%`, Latency p95 `297.71 ms` (Prometheus 5m window: `p95 = 295.0 ms`, `avg = 236.2 ms`), Saturation (in-flight) `3`, Instances up `2`, LLM cost (1h) `$0.5626`. Khoảng cách giữa `p95` (`~295 ms`), `p99` (`~1.7 s`) và `avg` (`~236 ms`) phản ánh phân bố lệch phải do ~3% request gặp tail latency.
   - **Requests/s theo instance:** Nginx chia traffic rất đều giữa các instance (`172.18.0.7:8000`: `21.46 req/s` vs `172.18.0.8:8000`: `21.56 req/s` trong cửa sổ 5m).
   - **Input tokens/s vs Output tokens/s:** `input = 3,308.9 tok/s` lớn hơn gần gấp đôi `output = 1,734.2 tok/s` vì agent v2 (RAG) ghép thêm `SYSTEM_PROMPT` + tài liệu truy xuất từ `KNOWLEDGE_BASE` + câu hỏi người dùng vào prompt đầu vào, trong khi câu trả lời ngắn gọn hơn.
   - **`curl -i http://localhost:8080/metrics`:** trả về **`HTTP/1.1 404 Not Found`** vì trong `nginx/nginx.conf` có rule `location = /metrics { return 404; }`. `/metrics` chỉ được Prometheus scrape trực tiếp trong mạng nội bộ `obs_net`, không mở public qua Nginx để tránh rò rỉ thông tin vận hành nội bộ (lưu lượng, tên route, chi phí, số instance).

### 4.2 Thí nghiệm "phá hệ thống" & Unit test Alert Rules

- **Unit test alert rules (`promtool test rules /p/alert_rules_test.yml`):** `SUCCESS` ✅.

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`value=20.65%`) | **75 giây** (pending ở 15s, `for: 1m`) | Golden Signals → **Error rate** (đỏ > 5%) & Latency/Traffic → **Requests/s theo status code** (`503` tăng mạnh) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`value=1.92s`) | **130 giây** (pending ở 10s, `for: 2m`) | Golden Signals → **Latency p95** (đỏ > 1s) & **Latency /ask — p50/p95/p99** |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`value=$11.24–$14.24/giờ`) | **165 giây** (pending ở 45s, `for: 2m`) | LLM → **Cost burn rate (USD/giờ)** tăng vọt > $2/h & **LLM latency p95** tăng ~2.5× |
| D | `docker pause k5-day14-observability-agent-2` | `AgentInstanceDown` (`instance=172.18.0.8:8000`, `value=0`) | **40 giây** (pending ở 10s, `for: 30s`) | Golden Signals → **Instances up** giảm từ 2 xuống 1; Requests/s theo instance dồn toàn bộ về instance còn lại |
| E | `AGENT_VERSION=v1` | **Không có alert nào firing** | Không firing | LLM → **Retrieval hit ratio** tụt về 0%, **Tokens/s** giảm gần một nửa, bảng **Phiên bản đang chạy** đổi từ `v2` sang `v1` |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**
- Các alert hạ tầng (error rate, p95 latency, instance up, cost) đều vẫn **xanh** thậm chí latency còn nhanh hơn và cost rẻ hơn khi chuyển nhầm về `v1`, nhưng độ chính xác đã sụp từ 100% xuống 4.3%.
- Để phát hiện sự cố suy giảm chất lượng (silent regression) trong production, cần kết hợp:
  1. **Eval quality gate trong CI/CD** chạy `golden_dataset` trước mọi lần deploy (như `.github/workflows/eval.yml`).
  2. **Online eval / LLM-as-a-Judge** chấm điểm định kỳ trên một tỷ lệ mẫu (vd 1–5%) traffic production thật và xuất metric `agent_eval_accuracy` cho Prometheus cảnh báo.
  3. **Theo dõi tín hiệu gián tiếp (proxy metrics)** như **Retrieval hit ratio** (tụt đột ngột về 0% là dấu hiệu hỏng RAG), phân bố độ dài câu trả lời, và tỷ lệ phản hồi tiêu cực (thumbs-down / retry rate) từ người dùng.
- *(Ghi chú thêm về Thí nghiệm D)*: Dùng `docker pause` thay vì `docker stop` vì container bị stop biến mất khỏi Docker DNS nên Prometheus không còn target để báo `up == 0`; còn lỗi `504 Gateway Timeout` do Nginx sinh ra khi agent treo không hiện trong metric của chính agent vì request chưa bao giờ đi tới middleware của agent — do đó production cần giám sát thêm ở tầng Load Balancer / Nginx và synthetic probe từ bên ngoài.

### 4.3 Debug bằng trace

Trace chậm nhất tìm được trong Jaeger ([`screenshots/jaeger-slow-trace.png`](screenshots/jaeger-slow-trace.png)):

- `trace_id`: `b2ce876318aac7eb54f3ada3ef90b53f`
- Tổng thời gian: **1726.6 ms** (hiển thị `1.7s` trên Jaeger UI)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (**1697.6 ms**, chiếm **98.3%** tổng thời gian request; trong khi `agent.retrieve_context` chỉ tốn `15.2 ms`, tức ~0.9%)
- Dòng log JSON tương ứng (trích trực tiếp từ `docker compose -p k5-day14-observability logs agent` theo `trace_id`):

```json
{"ts": "2026-11-27T02:54:42.641753+00:00", "level": "INFO", "service": "observable-agent", "instance": "aa82e8467c7e", "event": "llm_call", "trace_id": "b2ce876318aac7eb54f3ada3ef90b53f", "span_id": "842d83fb67c46dcb", "request_id": "b00ff4c09d09", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1697.6}
{"ts": "2026-11-27T02:54:42.643635+00:00", "level": "INFO", "service": "observable-agent", "instance": "aa82e8467c7e", "event": "http_request", "trace_id": "b2ce876318aac7eb54f3ada3ef90b53f", "span_id": "842d83fb67c46dcb", "request_id": "b00ff4c09d09", "method": "POST", "route": "/ask", "status": 200, "ms": 1726.6}
```

Trace lỗi đã kiểm tra trong Jaeger ([`screenshots/jaeger-error-trace.png`](screenshots/jaeger-error-trace.png)):
- `trace_id`: `d0929e35e048a3635c95429f3530de01` (tổng thời gian `114 ms`, span `chat mock-llm-small` `90.0 ms` ghi nhận event `exception`: `utils.mock_llm.LLMError: Upstream LLM error: 503 Service Unavailable (mock)`).
- Dòng log JSON khớp `trace_id`:

```json
{"ts": "2026-11-27T02:52:06.379431+00:00", "level": "INFO", "service": "observable-agent", "instance": "b84b4331d556", "event": "llm_error", "trace_id": "d0929e35e048a3635c95429f3530de01", "span_id": "c75654512d92b372", "request_id": "395fdeffc8f3", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

*(Dữ liệu khớp 100% với `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv`)*

**Số liệu theo `Aggregated` (và chi tiết `POST /ask`):**

| Số instance | RPS (Aggregated / `/ask`) | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 65.92 (59.56 `/ask`) | 190 (`200` `/ask`) | 250 (`260` `/ask`) | 1700 (`1700` `/ask`) | 79 / 7827 (1.01%) |
| 3 | 65.82 (59.66 `/ask`) | 190 (`190` `/ask`) | 250 (`250` `/ask`) | 1700 (`1700` `/ask`) | 69 / 7876 (0.88%) |

**Giải thích kết quả:** Scale từ 1 lên 3 instance chỉ giảm nhẹ p50/p95 của `POST /ask` (`200→190 ms` và `260→250 ms`), trong khi RPS gần như giữ nguyên (`~65.8–65.9 req/s`) và p99 giữ nguyên ở `1700 ms`. Nguyên nhân là vì:
1. **Nút thắt không nằm ở CPU của FastAPI agent** tại mức 100 user có `wait_time` nghỉ giữa các request — agent chạy async I/O nên 1 container vẫn dư sức gánh ~66 RPS.
2. **Nút thắt thực sự nằm ở độ trễ của upstream LLM** (`mock-llm-small` ~120–180ms + 3% tail latency ~1500ms) và tỷ lệ lỗi upstream ~1%. Việc scale ngang nhiều instance giúp tăng khả năng chịu tải ở concurrency cao hơn rất nhiều và đảm bảo tính sẵn sàng cao (High Availability khi 1 instance chết), nhưng không làm rút ngắn độ trễ cố hữu của chính lời gọi LLM (muốn giảm p95/p99 phải tối ưu prompt/model, dùng caching, streaming hoặc timeout + hedged retry).

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Luôn đo và đặt SLO bằng percentile (p95/p99) thay vì trung bình:** chỉ cần 3–10% request chậm là trải nghiệm người dùng bị ảnh hưởng nặng trong khi latency trung bình trông vẫn rất đẹp.
  2. **Hiệu năng và chất lượng là hai trục độc lập:** metric hạ tầng (Prometheus/Grafana) không phát hiện được lỗi suy giảm chất lượng như rollback nhầm từ RAG `v2` về `v1`; bắt buộc phải có **eval tự động trên golden dataset** gắn làm quality gate trong CI và đánh giá bằng **cost / câu đúng**.
  3. **3 trụ cột Metrics – Traces – Logs phải liên kết với nhau bằng `trace_id`:** Metrics cho biết *có sự cố* (alert firing), Traces (Jaeger) chỉ ra *chính xác span nào chậm/lỗi* (`chat mock-llm-small` chiếm 98.3%), và Structured JSON Logs cho biết *ngữ cảnh chi tiết* của từng sự kiện.
- **Nếu đưa agent này lên production thật, các metric / alert sẽ bổ sung thêm:**
  - **Nginx / Load Balancer metrics** (`nginx_http_requests_total` theo status `502/504`, upstream connect/read timeout) để phát hiện lỗi trước khi request chạm tới agent.
  - **LLM & RAG quality metrics:** `agent_retrieval_hit_ratio` (alert nếu tụt đột ngột dưới ngưỡng, giúp bắt sự cố như Thí nghiệm E), **Time-To-First-Token (TTFT)** nếu bật streaming, `llm_rate_limit_429_total`, và metric **Redis latency / error rate** cho tầng rate limiter & cost guard.
  - **Business / Cost protection:** Alert **budget consumption %** (cảnh báo sớm ở 80% ngân sách ngày/tháng) và **online eval accuracy** định kỳ trên mẫu traffic thật.
