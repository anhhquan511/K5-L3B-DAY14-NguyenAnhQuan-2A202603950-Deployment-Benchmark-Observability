"""
Cost guard (tiêu chí 8).

Cộng dồn chi phí LLM (tính theo token) vào Redis; vượt DAILY_BUDGET_USD hoặc
MONTHLY_BUDGET_USD → HTTP 402 Payment Required.
"""
import datetime
import threading

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

_mem_lock = threading.Lock()
_mem_daily_cost = 0.0
_mem_monthly_cost = 0.0


def _cost_keys() -> tuple[str, str]:
    today = datetime.datetime.now(datetime.timezone.utc)
    return (
        f"cost:daily:{today.strftime('%Y-%m-%d')}",
        f"cost:monthly:{today.strftime('%Y-%m')}",
    )


def _get_current_costs() -> tuple[float, float]:
    daily_key, monthly_key = _cost_keys()
    if r is not None:
        try:
            daily_val, monthly_val = r.mget(daily_key, monthly_key)
            return float(daily_val or 0.0), float(monthly_val or 0.0)
        except Exception:
            pass
    with _mem_lock:
        return _mem_daily_cost, _mem_monthly_cost


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    daily_spent, monthly_spent = _get_current_costs()
    if daily_spent >= settings.daily_budget_usd or monthly_spent >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="Budget exceeded. Please increase budget or try again later.",
        )


def estimate_tokens(text: str) -> int:
    """Ước lượng số token (~4 ký tự / token, tối thiểu 1)."""
    return max(1, (len(text) + 3) // 4)


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí request vào tổng trong Redis, trả về chi phí request."""
    global _mem_daily_cost, _mem_monthly_cost
    cost = (input_tokens / 1000.0) * PRICE_INPUT_PER_1K + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    daily_key, monthly_key = _cost_keys()

    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.incrbyfloat(daily_key, cost)
            pipe.expire(daily_key, 86400 * 2)
            pipe.incrbyfloat(monthly_key, cost)
            pipe.expire(monthly_key, 86400 * 35)
            pipe.execute()
            return cost
        except Exception:
            pass

    with _mem_lock:
        _mem_daily_cost += cost
        _mem_monthly_cost += cost
    return cost
