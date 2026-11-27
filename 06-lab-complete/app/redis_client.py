"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

App vẫn khởi động được khi Redis chưa sẵn sàng (lazy client, không ping lúc import).
"""
from typing import Optional

import redis

from app.config import settings

r: Optional[redis.Redis] = None
if settings.redis_url:
    r = redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
    )


def redis_healthy() -> bool:
    """Kiểm tra kết nối Redis cho endpoint GET /ready."""
    if r is None:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False


def close_redis() -> None:
    """Đóng kết nối Redis gọn gàng khi shutdown."""
    if r is not None:
        try:
            r.close()
        except Exception:
            pass
