import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "8701660709:AAEKa-j1RwIcMQXkosGPfDVXO_K9Cz65haQ")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://business_db_od8s_user:fhzKXD4mc6i0oLSbpYpuIBH3ri1LkEfX@dpg-d80uv13tqb8s738hob1g-a.oregon-postgres.render.com/business_db_od8s")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-domain.com")

# Оптимизация
POOL_MIN_SIZE = 10
POOL_MAX_SIZE = 50
BALANCE_CACHE_TTL = 60
CLICK_RATE_LIMIT = 80
INCOME_UPDATE_INTERVAL = 60
RATING_CACHE_TTL = 300

# Лимиты городов
MAX_FACTORIES_PER_CITY = 5
MAX_SHOPS_PER_CITY = 50
MAX_AIRPORTS_PER_CITY = 1

# Уровни перехода
LEVEL_UP_THRESHOLDS = {
    1: 0,
    2: 50_000_000,
    3: 100_000_000,
    4: 500_000_000,
    5: 1_000_000_000
}

# Доступность бизнесов по уровням
BUSINESS_UNLOCK = {
    "shop": 1,
    "taxi": 1,
    "agro": 1,
    "pipe_factory": 1,
    "brick_factory": 1,
    "metallurgy": 1,
    "car_factory": 2,
    "construction": 2,
    "tech_factory": 2,
    "bank": 3,
    "airport": 3,
    "own_crypto": 3,
    "it_company": 4,
    "logistics": 4,
    "media_holding": 5,
    "space_agency": 5
}

# Базовые доходы и стоимость открытия бизнесов
BUSINESS_BASE_COST = {
    "shop": 1_000_000,
    "taxi": 1_000_000,
    "agro": 1_000_000,
    "pipe_factory": 2_500_000,
    "brick_factory": 2_500_000,
    "metallurgy": 5_000_000,
    "car_factory": 50_000_000,
    "construction": 30_000_000,
    "tech_factory": 40_000_000,
    "bank": 50_000_000,
    "airport": 80_000_000,
    "own_crypto": 100_000_000,
    "it_company": 500_000_000,
    "logistics": 300_000_000,
    "media_holding": 1_000_000_000,
    "space_agency": 2_000_000_000
}
