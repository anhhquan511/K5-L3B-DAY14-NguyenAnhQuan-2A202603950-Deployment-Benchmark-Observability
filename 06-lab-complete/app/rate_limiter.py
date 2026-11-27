"""
Rate limiting (tiêu chí 7).

Sliding window 60 giây cho mỗi API key, lưu state trong Redis để stateless
giữa nhiều worker / instance và giữ nguyên state sau khi restart agent.
"""
import threading
import time
import uuid
from collections import defaultdict, deque

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60

# Lua script đảm bảo kiểm tra và ghi sliding window là atomic giữa các worker
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry = window
    if oldest and #oldest >= 2 then
        retry = math.max(1, math.ceil(window - (now - tonumber(oldest[2]))))
    end
    return {0, retry}
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, window + 5)
return {1, 0}
"""

# Fallback trong RAM chỉ dùng khi không cấu hình hoặc không kết nối được Redis
_mem_lock = threading.Lock()
_mem_windows: dict[str, deque[float]] = defaultdict(deque)


def _check_memory_rate_limit(key: str, limit: int, now: float) -> None:
    with _mem_lock:
        dq = _mem_windows[key]
        cutoff = now - WINDOW_SECONDS
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if len(dq) >= limit:
            retry_after = max(1, int(WINDOW_SECONDS - (now - dq[0])) + 1)
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
        dq.append(now)


def check_rate_limit(key: str) -> None:
    limit = settings.rate_limit_per_minute
    now = time.time()

    if r is not None:
        redis_key = f"ratelimit:{key}"
        member = f"{now}:{uuid.uuid4().hex[:8]}"
        try:
            allowed, retry_after = r.eval(
                _SLIDING_WINDOW_LUA,
                1,
                redis_key,
                str(now),
                str(WINDOW_SECONDS),
                str(limit),
                member,
            )
            if int(allowed) == 0:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(max(1, int(retry_after)))},
                )
            return
        except HTTPException:
            raise
        except Exception:
            # Nếu Redis tạm lỗi kết nối, fallback sang bộ đếm local thay vì crash
            pass

    _check_memory_rate_limit(key, limit, now)
