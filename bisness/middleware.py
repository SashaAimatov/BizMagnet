from aiohttp import web
import time
from collections import defaultdict
from config import CLICK_RATE_LIMIT

click_rates = defaultdict(list)

@web.middleware
async def auth_middleware(request, handler):
    """Проверка user_id из Telegram WebApp данных"""
    # Для простоты пропускаем, т.к. в реальности проверяем hash от Telegram
    return await handler(request)

@web.middleware
async def rate_limit_middleware(request, handler):
    """Ограничение RPS на пользователя (не более 10 запросов/сек)"""
    user_id = request.headers.get("X-User-Id")
    if user_id:
        now = time.time()
        timestamps = click_rates[user_id]
        timestamps = [t for t in timestamps if now - t < 1.0]
        if len(timestamps) >= 10:
            return web.json_response({"error": "Too many requests"}, status=429)
        timestamps.append(now)
        click_rates[user_id] = timestamps
    return await handler(request)