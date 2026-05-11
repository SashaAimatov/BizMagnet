import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiohttp import web
import db
import api
import logic
from config import BOT_TOKEN, WEBAPP_URL

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"

    user = await db.get_user(user_id)
    if not user:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Открыть бизнес-империю", web_app=WebAppInfo(url=WEBAPP_URL))]
        ])
        await message.answer(
            "🏆 Добро пожаловать в Бизнес-Магнат!\n\n"
            "У вас 1 000 000 ₽ стартового капитала.\n"
            "Открывайте бизнесы, инвестируйте в крипту, стройте империю!\n\n"
            "👇 Нажмите кнопку ниже, чтобы начать",
            reply_markup=keyboard
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏢 Моя империя", web_app=WebAppInfo(url=WEBAPP_URL))]
        ])
        await message.answer(f"С возвращением, {user['nickname']}!", reply_markup=keyboard)


async def background_income_updater():
    """Фоновая задача: обновление дохода каждые 60 секунд"""
    while True:
        await asyncio.sleep(logic.INCOME_UPDATE_INTERVAL)
        try:
            await logic.calculate_all_incomes()
            print("✅ Доходы обновлены")
        except Exception as e:
            print(f"❌ Ошибка обновления доходов: {e}")


async def main():
    print("🚀 Инициализация БД...")
    await db.init_db()
    print("✅ БД готова")

    asyncio.create_task(background_income_updater())

    app = api.create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    print(f"✅ API запущен на порту 8080")

    print("🤖 Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())