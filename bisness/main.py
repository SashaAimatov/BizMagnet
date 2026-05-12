import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
import db
import api
import logic
from config import BOT_TOKEN, WEBAPP_URL

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if not user:
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton("🚀 Открыть бизнес-империю", web_app=WebAppInfo(url=WEBAPP_URL))
        )
        await message.answer("Добро пожаловать! У вас 1 млн рублей.", reply_markup=keyboard)
    else:
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton("🏢 Моя империя", web_app=WebAppInfo(url=WEBAPP_URL))
        )
        await message.answer(f"С возвращением, {user['nickname']}!", reply_markup=keyboard)

async def background_income_updater():
    while True:
        await asyncio.sleep(60)
        try:
            await logic.calculate_all_incomes()
            print("✅ Доходы обновлены")
        except Exception as e:
            print(f"❌ Ошибка: {e}")

async def main():
    print("🚀 Инициализация БД...")
    await db.init_db()
    print("✅ БД готова")
    asyncio.create_task(background_income_updater())
    
    app = api.create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"✅ API запущен на порту {port}")
    
    print("🤖 Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())