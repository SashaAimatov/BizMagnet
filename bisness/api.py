import json
from aiohttp import web
import db
import logic
import utils
from config import BUSINESS_BASE_COST, WEBAPP_URL
from middleware import auth_middleware, rate_limit_middleware

routes = web.RouteTableDef()


@routes.get("/")
async def index(request):
    with open("templates/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    return web.Response(text=html, content_type="text/html")


@routes.post("/api/init")
async def init_user(request):
    data = await request.json()
    user_id = data.get("user_id")
    nickname = data.get("nickname")

    existing = await db.get_user(user_id)
    if not existing:
        await db.create_user(user_id, nickname)
    else:
        if existing["nickname"] != nickname:
            success = await db.update_nickname(user_id, nickname)
            if not success:
                return web.json_response({"error": "Никнейм уже занят"}, status=400)

    user = await db.get_user(user_id)
    user["balance"] = await db.get_balance(user_id)
    user["level"] = await db.get_level(user_id)
    return web.json_response(user)


@routes.post("/api/click")
async def click_handler(request):
    data = await request.json()
    user_id = data.get("user_id")
    clicks_per_sec = data.get("clicks_per_sec", 0)

    # Если клиент подозрительно много отправил, проверяем
    if clicks_per_sec > 100:
        penalty, msg, new_balance = await utils.check_anticlicker(user_id)
        if penalty > 0:
            return web.json_response({"status": "penalty", "message": msg, "new_balance": new_balance})
        elif msg:
            return web.json_response({"status": "warning", "message": msg})

    # Нормальный клик +100 руб
    new_balance = await db.update_balance(user_id, 100)
    await db.update_last_seen(user_id)
    return web.json_response({"status": "ok", "new_balance": new_balance})


@routes.get("/api/businesses")
async def get_businesses(request):
    user_id = int(request.query.get("user_id"))
    businesses = await db.get_businesses(user_id)
    for biz in businesses:
        biz["income"] = logic.calculate_business_income(biz)
        biz["config_preview"] = utils.format_business_config(biz["type"], biz.get("config", {}))
    return web.json_response(businesses)


@routes.post("/api/business/create")
async def create_business(request):
    data = await request.json()
    user_id = data["user_id"]
    biz_type = data["type"]
    city = data.get("city", "Москва")
    name = data.get("name", f"{biz_type} в {city}")

    # Проверка возможности открытия
    can, reason = await logic.can_open_business(user_id, biz_type, city)
    if not can:
        return web.json_response({"error": reason}, status=400)

    # Списание денег
    cost = BUSINESS_BASE_COST.get(biz_type, 0)
    await db.update_balance(user_id, -cost)

    # Создание бизнеса с дефолтным конфигом
    default_config = {}
    if biz_type == "shop":
        default_config = {"supplier": "medium", "product_quality": 5, "customers": 100}
    elif biz_type == "taxi":
        default_config = {"cars": 1, "car_model": "comfort", "city_demand": 5}
    elif biz_type == "bank":
        default_config = {"loan_rate": 15, "deposit_rate": 5, "capital": 0}
    elif biz_type == "airport":
        default_config = {"runways": 1, "terminals": 1, "destinations": 10}
    elif biz_type in ["pipe_factory", "brick_factory"]:
        default_config = {"workers": 10, "shift": 1, "equipment_lvl": 1}
    elif biz_type == "metallurgy":
        default_config = {"furnaces": 1, "raw_supply": 5, "automation": 1}
    elif biz_type == "car_factory":
        default_config = {"assembly_lines": 1, "robots": 10, "brand": "business"}
    elif biz_type == "construction":
        default_config = {"cranes": 1, "trucks": 5, "workers": 50}
    elif biz_type == "tech_factory":
        default_config = {"assembly_lines": 5, "components_supply": 5, "product_type": "phone"}
    elif biz_type == "it_company":
        default_config = {"programmers": 10, "projects": 2, "servers": 5}
    elif biz_type == "logistics":
        default_config = {"trucks": 10, "warehouses": 2, "routes": 5}
    elif biz_type == "media_holding":
        default_config = {"tv_channels": 1, "radio": 2, "online_portals": 5}
    elif biz_type == "space_agency":
        default_config = {"satellites": 1, "rockets": 1, "launch_pads": 1}
    elif biz_type == "own_crypto":
        default_config = {"coin_name": "MyCoin", "total_supply": 1000000, "price": 1.0}

    biz_id = await db.create_business(user_id, biz_type, city, name, default_config)

    if biz_type == "own_crypto":
        await db.create_own_crypto(biz_id, default_config["coin_name"], default_config["total_supply"],
                                   default_config["price"])

    return web.json_response({"id": biz_id, "message": f"Бизнес {name} создан!"})


@routes.post("/api/business/update")
async def update_business(request):
    data = await request.json()
    biz_id = data["id"]
    config_updates = data.get("config", {})

    biz_list = await db.get_businesses(data["user_id"])
    biz = next((b for b in biz_list if b["id"] == biz_id), None)
    if not biz:
        return web.json_response({"error": "Бизнес не найден"}, status=404)

    new_config = {**biz.get("config", {}), **config_updates}
    await db.update_business_config(biz_id, new_config)

    return web.json_response({"message": "Бизнес обновлён"})


@routes.post("/api/business/rename")
async def rename_business(request):
    data = await request.json()
    biz_id = data["id"]
    new_name = data["new_name"]

    balance = await db.get_balance(data["user_id"])
    if balance < 1_000_000:
        return web.json_response({"error": "Не хватает 1 000 000 ₽ для переименования"}, status=400)

    await db.update_balance(data["user_id"], -1_000_000)
    await db.rename_business(biz_id, new_name)

    return web.json_response({"message": "Бизнес переименован"})


@routes.get("/api/cities")
async def get_cities(request):
    # Статический список городов
    cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань"]
    return web.json_response(cities)


@routes.get("/api/crypto/price")
async def crypto_price(request):
    price = await db.get_crypto_price()
    return web.json_response({"price": price})


@routes.post("/api/crypto/buy")
async def crypto_buy(request):
    data = await request.json()
    user_id = data["user_id"]
    amount_rub = data["amount"]

    price = await db.get_crypto_price()
    crypto_amount = amount_rub / price

    balance = await db.get_balance(user_id)
    if balance < amount_rub:
        return web.json_response({"error": "Не хватает денег"}, status=400)

    await db.update_balance(user_id, -amount_rub)
    await db.update_crypto_amount(user_id, crypto_amount)

    return web.json_response(
        {"message": f"Куплено {crypto_amount:.4f} монет", "new_balance": await db.get_balance(user_id)})


@routes.post("/api/crypto/sell")
async def crypto_sell(request):
    data = await request.json()
    user_id = data["user_id"]
    crypto_amount = data["amount"]

    price = await db.get_crypto_price()
    rub_amount = crypto_amount * price

    holdings = await db.get_crypto_amount(user_id)
    if holdings < crypto_amount:
        return web.json_response({"error": "Не хватает монет"}, status=400)

    await db.update_crypto_amount(user_id, -crypto_amount)
    await db.update_balance(user_id, rub_amount)

    return web.json_response(
        {"message": f"Продано за {rub_amount:.2f} ₽", "new_balance": await db.get_balance(user_id)})


@routes.get("/api/rating/top")
async def rating_top(request):
    top = await db.get_top_players(10)
    return web.json_response(top)


@routes.get("/api/rating/profile")
async def rating_profile(request):
    user_id = int(request.query.get("user_id"))
    profile = await db.get_player_profile(user_id)
    return web.json_response(profile)


@routes.post("/api/settings/theme")
async def set_theme(request):
    data = await request.json()
    user_id = data["user_id"]
    dark = data["dark"]
    await db.update_theme(user_id, dark)
    return web.json_response({"message": "Тема обновлена"})


@routes.post("/api/settings/rename")
async def rename_user(request):
    data = await request.json()
    user_id = data["user_id"]
    new_nickname = data["nickname"]

    success = await db.update_nickname(user_id, new_nickname)
    if not success:
        return web.json_response({"error": "Никнейм уже занят"}, status=400)
    return web.json_response({"message": "Никнейм изменён"})


@routes.get("/api/available_businesses")
async def available_businesses(request):
    user_id = int(request.query.get("user_id"))
    user = await db.get_user(user_id)
    level = user["level"] if user else 1
    businesses = []
    for biz_type, unlock_level in logic.BUSINESS_UNLOCK.items():
        businesses.append({
            "type": biz_type,
            "name": biz_type.replace("_", " ").title(),
            "unlock_level": unlock_level,
            "available": level >= unlock_level,
            "cost": BUSINESS_BASE_COST.get(biz_type, 0)
        })
    return web.json_response(businesses)


def create_app():
    app = web.Application(middlewares=[auth_middleware, rate_limit_middleware])
    app.add_routes(routes)
    return app