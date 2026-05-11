import asyncpg
import json
from typing import Optional, Dict, List, Any
from config import DATABASE_URL, POOL_MIN_SIZE, POOL_MAX_SIZE

pool = None
balance_cache = {}


async def init_db():
    global pool
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=POOL_MIN_SIZE,
        max_size=POOL_MAX_SIZE,
        command_timeout=60
    )
    async with pool.acquire() as conn:
        await conn.execute('''
                           CREATE TABLE IF NOT EXISTS users
                           (
                               user_id
                               BIGINT
                               PRIMARY
                               KEY,
                               nickname
                               TEXT
                               UNIQUE,
                               balance
                               BIGINT
                               DEFAULT
                               1000000,
                               level
                               INTEGER
                               DEFAULT
                               1,
                               dark_theme
                               BOOLEAN
                               DEFAULT
                               FALSE,
                               total_earned
                               BIGINT
                               DEFAULT
                               0,
                               click_warns
                               INTEGER
                               DEFAULT
                               0,
                               last_seen
                               TIMESTAMP
                               DEFAULT
                               NOW
                           (
                           )
                               )
                           ''')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_total_earned ON users(total_earned DESC)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen)')

        await conn.execute('''
                           CREATE TABLE IF NOT EXISTS businesses
                           (
                               id
                               SERIAL
                               PRIMARY
                               KEY,
                               user_id
                               BIGINT
                               REFERENCES
                               users
                           (
                               user_id
                           ) ON DELETE CASCADE,
                               type TEXT,
                               city TEXT,
                               name TEXT,
                               config JSONB,
                               created_at TIMESTAMP DEFAULT NOW
                           (
                           )
                               )
                           ''')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_businesses_user ON businesses(user_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_businesses_type ON businesses(type)')

        await conn.execute('''
                           CREATE TABLE IF NOT EXISTS crypto_holdings
                           (
                               user_id
                               BIGINT
                               PRIMARY
                               KEY
                               REFERENCES
                               users
                           (
                               user_id
                           ) ON DELETE CASCADE,
                               amount REAL DEFAULT 0
                               )
                           ''')

        await conn.execute('''
                           CREATE TABLE IF NOT EXISTS global_crypto
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               CHECK
                           (
                               id =
                               1
                           ),
                               price REAL DEFAULT 100.0
                               )
                           ''')
        await conn.execute("INSERT INTO global_crypto (id, price) VALUES (1, 100) ON CONFLICT (id) DO NOTHING")

        await conn.execute('''
                           CREATE TABLE IF NOT EXISTS own_crypto
                           (
                               business_id
                               INTEGER
                               PRIMARY
                               KEY
                               REFERENCES
                               businesses
                           (
                               id
                           ) ON DELETE CASCADE,
                               coin_name TEXT,
                               total_supply REAL,
                               price REAL
                               )
                           ''')


async def get_user(user_id: int) -> Optional[Dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(row) if row else None


async def create_user(user_id: int, nickname: str):
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO users (user_id, nickname, balance, total_earned) VALUES ($1, $2, 1000000, 0)",
                user_id, nickname
            )
            await conn.execute("INSERT INTO crypto_holdings (user_id, amount) VALUES ($1, 0)", user_id)
            balance_cache[user_id] = {"balance": 1000000, "dirty": False}


async def get_balance(user_id: int) -> int:
    if user_id in balance_cache:
        return balance_cache[user_id]["balance"]
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", user_id)
        balance = row["balance"] if row else 1000000
        balance_cache[user_id] = {"balance": balance, "dirty": False}
        return balance


async def update_balance(user_id: int, delta: int) -> int:
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "UPDATE users SET balance = balance + $1 WHERE user_id = $2 RETURNING balance",
                delta, user_id
            )
            new_balance = row["balance"]
            if user_id in balance_cache:
                balance_cache[user_id]["balance"] = new_balance
            else:
                balance_cache[user_id] = {"balance": new_balance, "dirty": False}

            if delta > 0:
                await conn.execute(
                    "UPDATE users SET total_earned = total_earned + $1 WHERE user_id = $2",
                    delta, user_id
                )
            return new_balance


async def update_nickname(user_id: int, new_nickname: str) -> bool:
    async with pool.acquire() as conn:
        try:
            await conn.execute("UPDATE users SET nickname = $1 WHERE user_id = $2", new_nickname, user_id)
            return True
        except asyncpg.UniqueViolationError:
            return False


async def update_theme(user_id: int, dark: bool):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET dark_theme = $1 WHERE user_id = $2", dark, user_id)


async def get_click_warns(user_id: int) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT click_warns FROM users WHERE user_id = $1", user_id)
        return row["click_warns"] if row else 0


async def update_click_warns(user_id: int, warns: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET click_warns = $1 WHERE user_id = $2", warns, user_id)


async def update_last_seen(user_id: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET last_seen = NOW() WHERE user_id = $1", user_id)


async def get_level(user_id: int) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT level, total_earned FROM users WHERE user_id = $1", user_id)
        if not row:
            return 1
        from logic import get_level_from_earned
        new_level = get_level_from_earned(row["total_earned"])
        if new_level != row["level"]:
            await conn.execute("UPDATE users SET level = $1 WHERE user_id = $2", new_level, user_id)
        return new_level


async def get_businesses(user_id: int) -> List[Dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM businesses WHERE user_id = $1 ORDER BY id", user_id)
        return [dict(r) for r in rows]


async def create_business(user_id: int, biz_type: str, city: str, name: str, config: Dict) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO businesses (user_id, type, city, name, config) VALUES ($1, $2, $3, $4, $5) RETURNING id",
            user_id, biz_type, city, name, json.dumps(config)
        )
        return row["id"]


async def update_business_config(biz_id: int, config: Dict):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE businesses SET config = $1 WHERE id = $2", json.dumps(config), biz_id)


async def rename_business(biz_id: int, new_name: str):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE businesses SET name = $1 WHERE id = $2", new_name, biz_id)


async def delete_business(biz_id: int):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM businesses WHERE id = $1", biz_id)


async def get_crypto_price() -> float:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT price FROM global_crypto WHERE id = 1")
        return row["price"] if row else 100.0


async def update_crypto_price(new_price: float):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE global_crypto SET price = $1 WHERE id = 1", new_price)


async def get_crypto_amount(user_id: int) -> float:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT amount FROM crypto_holdings WHERE user_id = $1", user_id)
        return row["amount"] if row else 0.0


async def update_crypto_amount(user_id: int, delta: float):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE crypto_holdings SET amount = amount + $1 WHERE user_id = $2",
            delta, user_id
        )


async def get_own_crypto(business_id: int) -> Optional[Dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM own_crypto WHERE business_id = $1", business_id)
        return dict(row) if row else None


async def create_own_crypto(business_id: int, coin_name: str, total_supply: float, price: float):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO own_crypto (business_id, coin_name, total_supply, price) VALUES ($1, $2, $3, $4)",
            business_id, coin_name, total_supply, price
        )


async def get_top_players(limit: int = 10) -> List[Dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id, nickname, balance, total_earned, level, last_seen FROM users ORDER BY total_earned DESC LIMIT $1",
            limit
        )
        return [dict(r) for r in rows]


async def get_player_profile(user_id: int) -> Optional[Dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id, nickname, balance, total_earned, level, last_seen FROM users WHERE user_id = $1",
            user_id
        )
        if not row:
            return None
        profile = dict(row)
        businesses = await get_businesses(user_id)
        profile["businesses_count"] = len(businesses)
        profile["crypto_amount"] = await get_crypto_amount(user_id)
        return profile