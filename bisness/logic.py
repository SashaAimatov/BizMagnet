from config import LEVEL_UP_THRESHOLDS, BUSINESS_UNLOCK, MAX_FACTORIES_PER_CITY, MAX_SHOPS_PER_CITY, \
    MAX_AIRPORTS_PER_CITY
import db
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
    """Возвращает (можно, причина)"""
    user = await db.get_user(user_id)
    if not user:
        return False, "Пользователь не найден"

    if not is_business_unlocked(biz_type, user["level"]):
        return False, f"Бизнес {biz_type} откроется на {BUSINESS_UNLOCK[biz_type]} уровне"

    from config import BUSINESS_BASE_COST
    cost = BUSINESS_BASE_COST.get(biz_type, 0)
    if user["balance"] < cost:
        return False, f"Не хватает денег. Нужно: {cost:,} ₽"

    businesses = await db.get_businesses(user_id)
    city_businesses = [b for b in businesses if b["city"] == city]

    if biz_type in ["pipe_factory", "brick_factory", "metallurgy", "car_factory", "construction", "tech_factory",
                    "it_company", "logistics", "space_agency"]:
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
    """Расчёт ежеминутного дохода бизнеса на основе его конфига"""
    biz_type = biz["type"]
    config = biz.get("config")
    if not config:
        return 0

    if biz_type == "shop":
        # config: {"supplier": "cheap/medium/premium", "product_quality": 1-10, "customers": 100-1000}
        base = 1000
        supplier_mult = {"cheap": 0.8, "medium": 1.0, "premium": 1.5}.get(config.get("supplier", "medium"), 1.0)
        quality_mult = 0.5 + config.get("product_quality", 5) / 10
        customers = config.get("customers", 100)
        return int(base * supplier_mult * quality_mult * (customers / 100))

    elif biz_type == "taxi":
        # config: {"cars": 1-50, "car_model": "econom/comfort/business", "city_demand": 1-10}
        cars = config.get("cars", 1)
        car_mult = {"econom": 0.5, "comfort": 1.0, "business": 2.0}.get(config.get("car_model", "comfort"), 1.0)
        demand = config.get("city_demand", 5)
        return int(cars * 500 * car_mult * (demand / 5))

    elif biz_type in ["pipe_factory", "brick_factory"]:
        # config: {"workers": 1-100, "shift": 1-3, "equipment_lvl": 1-10}
        workers = config.get("workers", 10)
        shift = config.get("shift", 1)
        equipment = config.get("equipment_lvl", 1)
        return int(workers * shift * 100 * (equipment / 5))

    elif biz_type == "metallurgy":
        # config: {"furnaces": 1-20, "raw_supply": 1-10, "automation": 1-10}
        furnaces = config.get("furnaces", 5)
        raw = config.get("raw_supply", 5)
        automation = config.get("automation", 1)
        return int(furnaces * 2000 * (raw / 5) * (automation / 5))

    elif biz_type == "car_factory":
        # config: {"assembly_lines": 1-10, "robots": 1-100, "brand": "econom/business/premium"}
        lines = config.get("assembly_lines", 1)
        robots = config.get("robots", 10)
        brand_mult = {"econom": 0.7, "business": 1.0, "premium": 2.0}.get(config.get("brand", "business"), 1.0)
        return int(lines * 5000 + robots * 200 * brand_mult)

    elif biz_type == "construction":
        # config: {"cranes": 1-10, "trucks": 1-50, "workers": 10-500}
        cranes = config.get("cranes", 1)
        trucks = config.get("trucks", 5)
        workers = config.get("workers", 50)
        return int(cranes * 3000 + trucks * 500 + workers * 50)

    elif biz_type == "tech_factory":
        # config: {"assembly_lines": 1-20, "components_supply": 1-10, "product_type": "phone/laptop/headphones"}
        lines = config.get("assembly_lines", 5)
        supply = config.get("components_supply", 5)
        product_mult = {"phone": 1.0, "laptop": 2.0, "headphones": 0.5}.get(config.get("product_type", "phone"), 1.0)
        return int(lines * 2000 * supply * product_mult)

    elif biz_type == "bank":
        # config: {"loan_rate": 5-30, "deposit_rate": 1-15, "capital": сумма в банке}
        loan_rate = config.get("loan_rate", 15)
        deposit_rate = config.get("deposit_rate", 5)
        capital = config.get("capital", 0)
        # чем выше loan_rate, тем меньше кредитов; чем выше deposit_rate, тем больше вкладов
        loans = max(0, 100 * (30 - loan_rate) / 25)
        deposits = max(0, 100 * (deposit_rate - 1) / 14)
        income = int(capital * (loan_rate - deposit_rate) / 100 * (loans + deposits) / 100)
        return max(0, income)

    elif biz_type == "airport":
        # config: {"runways": 1-3, "terminals": 1-5, "destinations": 1-50}
        runways = config.get("runways", 1)
        terminals = config.get("terminals", 1)
        destinations = config.get("destinations", 10)
        return int(runways * 10000 + terminals * 5000 + destinations * 1000)

    elif biz_type == "it_company":
        # config: {"programmers": 1-200, "projects": 1-20, "servers": 1-50}
        programmers = config.get("programmers", 10)
        projects = config.get("projects", 2)
        servers = config.get("servers", 5)
        return int(programmers * 300 + projects * 5000 + servers * 1000)

    elif biz_type == "logistics":
        # config: {"trucks": 1-100, "warehouses": 1-20, "routes": 1-50}
        trucks = config.get("trucks", 10)
        warehouses = config.get("warehouses", 2)
        routes = config.get("routes", 5)
        return int(trucks * 400 + warehouses * 2000 + routes * 800)

    elif biz_type == "media_holding":
        # config: {"tv_channels": 1-5, "radio": 1-10, "online_portals": 1-20}
        tv = config.get("tv_channels", 1)
        radio = config.get("radio", 2)
        online = config.get("online_portals", 5)
        return int(tv * 15000 + radio * 2000 + online * 1000)

    elif biz_type == "space_agency":
        # config: {"satellites": 1-10, "rockets": 1-5, "launch_pads": 1-3}
        satellites = config.get("satellites", 1)
        rockets = config.get("rockets", 1)
        launch_pads = config.get("launch_pads", 1)
        return int(satellites * 50000 + rockets * 100000 + launch_pads * 50000)

    return 0


async def calculate_all_incomes():
    """Фоновый пересчёт дохода для всех пользователей"""
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