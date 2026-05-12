import db
from config import LEVEL_UP_THRESHOLDS, BUSINESS_UNLOCK, MAX_FACTORIES_PER_CITY, MAX_SHOPS_PER_CITY, MAX_AIRPORTS_PER_CITY

# ЭТА ПЕРЕМЕННАЯ БЫЛА ПРОПУЩЕНА
INCOME_UPDATE_INTERVAL = 60

def get_level_from_earned(total_earned: int) -> int:
    level = 1
    for lvl, threshold in sorted(LEVEL_UP_THRESHOLDS.items()):
        if total_earned >= threshold:
            level = lvl
    return level

def is_business_unlocked(biz_type: str, level: int) -> bool:
    return BUSINESS_UNLOCK.get(biz_type, 99) <= level

async def can_open_business(user_id: int, biz_type: str, city: str) -> tuple:
    user = await db.get_user(user_id)
    if not user:
        return False, "Пользователь не найден"
    
    if not is_business_unlocked(biz_type, user["level"]):
        return False, f"Бизнес {biz_type} откроется на {BUSINESS_UNLOCK.get(biz_type, 99)} уровне"
    
    from config import BUSINESS_BASE_COST
    cost = BUSINESS_BASE_COST.get(biz_type, 0)
    if user["balance"] < cost:
        return False, f"Не хватает денег. Нужно: {cost:,} ₽"
    
    businesses = await db.get_businesses(user_id)
    city_businesses = [b for b in businesses if b["city"] == city]
    
    factory_types = ["pipe_factory", "brick_factory", "metallurgy", "car_factory", "construction", "tech_factory", "it_company", "logistics", "space_agency"]
    if biz_type in factory_types:
        if len(city_businesses) >= MAX_FACTORIES_PER_CITY:
            return False, f"В городе {city} уже {MAX_FACTORIES_PER_CITY} заводов (максимум)"
    elif biz_type == "shop":
        if len(city_businesses) >= MAX_SHOPS_PER_CITY:
            return False, f"В городе {city} уже {MAX_SHOPS_PER_CITY} магазинов (максимум)"
    elif biz_type == "airport":
        if any(b["type"] == "airport" and b["city"] == city for b in businesses):
            return False, f"В городе {city} уже есть аэропорт (можно только 1)"
    
    return True, "OK"

def calculate_business_income(biz: dict) -> int:
    biz_type = biz["type"]
    config = biz.get("config")
    if not config:
        return 100  # базовый доход, чтобы не было 0
    
    if biz_type == "shop":
        base = 1000
        supplier_mult = {"cheap": 0.8, "medium": 1.0, "premium": 1.5}.get(config.get("supplier", "medium"), 1.0)
        quality_mult = 0.5 + config.get("product_quality", 5) / 10
        customers = config.get("customers", 100)
        return int(base * supplier_mult * quality_mult * (customers / 100))
    
    elif biz_type == "taxi":
        cars = config.get("cars", 1)
        car_mult = {"econom": 0.5, "comfort": 1.0, "business": 2.0}.get(config.get("car_model", "comfort"), 1.0)
        demand = config.get("city_demand", 5)
        return int(cars * 500 * car_mult * (demand / 5))
    
    return 100  # доход по умолчанию

async def calculate_all_incomes():
    from db import pool
    async with pool.acquire() as conn:
        businesses = await conn.fetch("SELECT id, user_id, type, config FROM businesses")
        income_by_user = {}
        for biz in businesses:
            biz_dict = {"type": biz["type"], "config": biz["config"]}
            income = calculate_business_income(biz_dict)
            if income > 0:
                income_by_user[biz["user_id"]] = income_by_user.get(biz["user_id"], 0) + income
        
        for user_id, total_income in income_by_user.items():
            await conn.execute(
                "UPDATE users SET balance = balance + $1, total_earned = total_earned + $1 WHERE user_id = $2",
                total_income, user_id
            )
            if user_id in db.balance_cache:
                db.balance_cache[user_id]["balance"] += total_income