import time
from collections import defaultdict
import db

click_timestamps = defaultdict(list)


async def check_anticlicker(user_id: int) -> tuple:
    """Возвращает (штраф, сообщение, новый баланс если был штраф)"""
    now = time.time()
    timestamps = click_timestamps[user_id]
    timestamps.append(now)
    timestamps = [t for t in timestamps if now - t < 1.0]
    click_timestamps[user_id] = timestamps
    cps = len(timestamps)

    if cps <= 80:
        return (0, None, None)

    warns = await db.get_click_warns(user_id) + 1
    await db.update_click_warns(user_id, warns)

    if warns == 1:
        return (0, "⚠️ Предупреждение! Не используйте автокликер. При повторном нарушении будет штраф.", None)
    elif warns == 2:
        await db.update_balance(user_id, -10000)
        new_balance = await db.get_balance(user_id)
        return (10000, f"💰 Штраф 10 000 рублей! Баланс: {new_balance:,} ₽", new_balance)
    else:
        balance = await db.get_balance(user_id)
        penalty = int(balance * 2 / 3)
        await db.update_balance(user_id, -penalty)
        new_balance = await db.get_balance(user_id)
        return (penalty, f"💀 Вычтено 2/3 баланса за автокликер! Потеряно: {penalty:,} ₽. Баланс: {new_balance:,} ₽",
                new_balance)


def format_number(num: int) -> str:
    return f"{num:,}".replace(",", " ")


def format_business_config(biz_type: str, config: dict) -> str:
    """Красивый вывод конфига бизнеса"""
    if not config:
        return "Не настроен"

    if biz_type == "shop":
        return f"🏪 Поставщик: {config.get('supplier', 'medium')}, Качество: {config.get('product_quality', 5)}/10, Покупателей: {config.get('customers', 100)}"
    elif biz_type == "taxi":
        return f"🚖 Авто: {config.get('cars', 1)}, Модель: {config.get('car_model', 'comfort')}, Спрос: {config.get('city_demand', 5)}/10"
    elif biz_type == "bank":
        return f"🏦 Ставка кредита: {config.get('loan_rate', 15)}%, Ставка вклада: {config.get('deposit_rate', 5)}%, Капитал: {format_number(config.get('capital', 0))} ₽"
    elif biz_type == "airport":
        return f"✈️ ВПП: {config.get('runways', 1)}, Терминалов: {config.get('terminals', 1)}, Направлений: {config.get('destinations', 10)}"
    else:
        return "⚙️ Настроен"