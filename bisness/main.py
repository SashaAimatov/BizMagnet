import asyncio
import time
from collections import defaultdict
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage

import db
import logic
import utils
from config import BOT_TOKEN

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ========== КЛИКЕР (защита) ==========
user_clicks = defaultdict(list)

# ========== FSM ДЛЯ СОЗДАНИЯ БИЗНЕСА ==========
class CreateBusiness(StatesGroup):
    waiting_for_type = State()
    waiting_for_city = State()
    waiting_for_name = State()

# ========== FSM ДЛЯ НАСТРОЙКИ БИЗНЕСА ==========
class ConfigBusiness(StatesGroup):
    waiting_for_biz_id = State()
    waiting_for_field = State()
    waiting_for_value = State()

# ========== ГЛАВНОЕ МЕНЮ ==========
async def main_menu(user_id: int):
    user = await db.get_user(user_id)
    balance = await db.get_balance(user_id)
    level = await db.get_level(user_id)
    text = (f"🏆 *Бизнес-Магнат*\n\n"
            f"👤 Ник: {user['nickname']}\n"
            f"📊 Уровень: {level}\n"
            f"💰 Баланс: {utils.format_number(balance)} ₽\n\n"
            f"Выберите действие:")
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📋 Мои бизнесы", callback_data="my_businesses"),
        InlineKeyboardButton("🏭 Открыть бизнес", callback_data="open_business"),
        InlineKeyboardButton("💰 Заработать", callback_data="clicker"),
        InlineKeyboardButton("₿ Криптовалюта", callback_data="crypto"),
        InlineKeyboardButton("🏆 Рейтинг", callback_data="rating"),
        InlineKeyboardButton("⚙️ Настройки", callback_data="settings")
    )
    await bot.send_message(user_id, text, reply_markup=kb, parse_mode="Markdown")

# ========== МОИ БИЗНЕСЫ ==========
async def show_businesses(user_id: int):
    businesses = await db.get_businesses(user_id)
    if not businesses:
        await bot.send_message(user_id, "У вас пока нет бизнесов. Откройте первый через меню.")
        return
    for biz in businesses:
        income = logic.calculate_business_income(biz)
        text = (f"🏭 *{biz['name']}*\n"
                f"📍 Город: {biz['city']}\n"
                f"📦 Тип: {biz['type'].replace('_', ' ')}\n"
                f"💰 Доход: +{utils.format_number(income)} ₽/мин\n"
                f"⚙️ Настройки: {utils.format_business_config(biz['type'], biz.get('config', {}))}")
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("⚙️ Настроить", callback_data=f"config_{biz['id']}"),
            InlineKeyboardButton("✏️ Переименовать (1M ₽)", callback_data=f"rename_{biz['id']}")
        )
        await bot.send_message(user_id, text, reply_markup=kb, parse_mode="Markdown")

# ========== ОТКРЫТИЕ БИЗНЕСА (FSM) ==========
@dp.callback_query_handler(lambda c: c.data == "open_business")
async def open_business_start(callback: types.CallbackQuery):
    available = []
    user = await db.get_user(callback.from_user.id)
    user_level = user["level"]
    for biz_type, unlock_level in logic.BUSINESS_UNLOCK.items():
        if user_level >= unlock_level:
            available.append(biz_type)
    if not available:
        await callback.message.edit_text("❌ Нет доступных бизнесов для вашего уровня.")
        return
    kb = InlineKeyboardMarkup(row_width=2)
    for biz in available:
        cost = logic.BUSINESS_BASE_COST.get(biz, 0)
        name = biz.replace('_', ' ').title()
        kb.add(InlineKeyboardButton(f"{name} ({utils.format_number(cost)} ₽)", callback_data=f"biztype_{biz}"))
    await callback.message.edit_text("Выберите тип бизнеса:", reply_markup=kb)
    await CreateBusiness.waiting_for_type.set()

@dp.callback_query_handler(lambda c: c.data.startswith("biztype_"), state=CreateBusiness.waiting_for_type)
async def biz_type_chosen(callback: types.CallbackQuery, state: FSMContext):
    biz_type = callback.data.split("_")[1]
    await state.update_data(biz_type=biz_type)
    cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань"]
    kb = InlineKeyboardMarkup(row_width=2)
    for city in cities:
        kb.add(InlineKeyboardButton(city, callback_data=f"city_{city}"))
    await callback.message.edit_text("Выберите город:", reply_markup=kb)
    await CreateBusiness.waiting_for_city.set()

@dp.callback_query_handler(lambda c: c.data.startswith("city_"), state=CreateBusiness.waiting_for_city)
async def city_chosen(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_")[1]
    await state.update_data(city=city)
    await callback.message.edit_text("Введите название бизнеса (можно отправить текстом):")
    await CreateBusiness.waiting_for_name.set()

@dp.message_handler(state=CreateBusiness.waiting_for_name)
async def biz_name_entered(message: types.Message, state: FSMContext):
    name = message.text
    data = await state.get_data()
    biz_type = data["biz_type"]
    city = data["city"]
    user_id = message.from_user.id
    
    can, reason = await logic.can_open_business(user_id, biz_type, city)
    if not can:
        await message.answer(f"❌ {reason}")
        await state.finish()
        await main_menu(user_id)
        return
    
    cost = logic.BUSINESS_BASE_COST.get(biz_type, 0)
    await db.update_balance(user_id, -cost)
    default_config = {}
    if biz_type == "shop":
        default_config = {"supplier": "medium", "product_quality": 5, "customers": 100}
    elif biz_type == "taxi":
        default_config = {"cars": 1, "car_model": "comfort", "city_demand": 5}
    else:
        default_config = {}
    biz_id = await db.create_business(user_id, biz_type, city, name, default_config)
    await message.answer(f"✅ Бизнес «{name}» открыт! Стоимость: {utils.format_number(cost)} ₽")
    await state.finish()
    await main_menu(user_id)

# ========== НАСТРОЙКА БИЗНЕСА ==========
@dp.callback_query_handler(lambda c: c.data.startswith("config_"))
async def config_business(callback: types.CallbackQuery):
    biz_id = int(callback.data.split("_")[1])
    businesses = await db.get_businesses(callback.from_user.id)
    biz = next((b for b in businesses if b["id"] == biz_id), None)
    if not biz:
        await callback.answer("Бизнес не найден")
        return
    if biz["type"] == "shop":
        config = biz.get("config", {})
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔄 Поставщик", callback_data=f"set_supplier_{biz_id}"))
        kb.add(InlineKeyboardButton("⭐ Качество (1-10)", callback_data=f"set_quality_{biz_id}"))
        kb.add(InlineKeyboardButton("👥 Количество покупателей", callback_data=f"set_customers_{biz_id}"))
        await callback.message.edit_text(f"Настройка {biz['name']}:\nТекущие: {utils.format_business_config(biz['type'], config)}", reply_markup=kb)
    else:
        await callback.answer("Настройки для этого бизнеса скоро появятся")

@dp.callback_query_handler(lambda c: c.data.startswith("set_supplier_"))
async def set_supplier(callback: types.CallbackQuery):
    biz_id = int(callback.data.split("_")[2])
    kb = InlineKeyboardMarkup()
    for sup in ["cheap", "medium", "premium"]:
        kb.add(InlineKeyboardButton(sup.capitalize(), callback_data=f"supplier_{biz_id}_{sup}"))
    await callback.message.edit_text("Выберите поставщика:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("supplier_"))
async def supplier_chosen(callback: types.CallbackQuery):
    _, biz_id, supplier = callback.data.split("_")
    biz_id = int(biz_id)
    businesses = await db.get_businesses(callback.from_user.id)
    biz = next((b for b in businesses if b["id"] == biz_id), None)
    if biz:
        config = biz.get("config", {})
        config["supplier"] = supplier
        await db.update_business_config(biz_id, config)
        await callback.answer("Поставщик изменён!")
    await show_businesses(callback.from_user.id)

# ========== ПЕРЕИМЕНОВАНИЕ БИЗНЕСА ==========
@dp.callback_query_handler(lambda c: c.data.startswith("rename_"))
async def rename_business_callback(callback: types.CallbackQuery):
    biz_id = int(callback.data.split("_")[1])
    balance = await db.get_balance(callback.from_user.id)
    if balance < 1_000_000:
        await callback.answer("Не хватает 1 000 000 ₽", show_alert=True)
        return
    await db.update_balance(callback.from_user.id, -1_000_000)
    await callback.message.answer("Введите новое название бизнеса (текстом):")
    await ConfigBusiness.waiting_for_biz_id.set()
    await dp.current_state().update_data(biz_id=biz_id)

@dp.message_handler(state=ConfigBusiness.waiting_for_biz_id)
async def new_biz_name(message: types.Message, state: FSMContext):
    new_name = message.text
    data = await state.get_data()
    biz_id = data["biz_id"]
    await db.rename_business(biz_id, new_name)
    await message.answer(f"✅ Бизнес переименован в «{new_name}»")
    await state.finish()
    await main_menu(message.from_user.id)

# ========== КЛИКЕР ==========
@dp.callback_query_handler(lambda c: c.data == "clicker")
async def clicker_menu(callback: types.CallbackQuery):
    text = "💰 *Кликер*\n\nНажми на кнопку ниже, чтобы заработать 100 ₽.\n\n⚠️ За автокликер – штраф!"
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("💸 Заработать!", callback_data="do_click"))
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data == "do_click")
async def do_click(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    now = time.time()
    clicks = user_clicks[user_id]
    clicks = [t for t in clicks if now - t < 1.0]
    cps = len(clicks) + 1
    if cps > 80:
        penalty, msg, new_balance = await utils.check_anticlicker(user_id)
        if penalty > 0:
            await callback.answer(f"⚠️ {msg}", show_alert=True)
        else:
            await callback.answer(msg, show_alert=True)
    else:
        clicks.append(now)
        user_clicks[user_id] = clicks
        new_balance = await db.update_balance(user_id, 100)
        await callback.answer("+100 ₽!", show_alert=False)
    await callback.message.delete()
    await main_menu(user_id)

# ========== КРИПТОВАЛЮТА ==========
@dp.callback_query_handler(lambda c: c.data == "crypto")
async def crypto_menu(callback: types.CallbackQuery):
    price = await db.get_crypto_price()
    amount = await db.get_crypto_amount(callback.from_user.id)
    balance = await db.get_balance(callback.from_user.id)
    text = (f"₿ *Криптовалюта*\n\n"
            f"💰 Цена: {price:.2f} ₽\n"
            f"📦 Ваши монеты: {amount:.4f}\n"
            f"💵 Баланс: {utils.format_number(balance)} ₽\n\n"
            f"Выберите действие:")
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📈 Купить", callback_data="buy_crypto"),
        InlineKeyboardButton("📉 Продать", callback_data="sell_crypto"),
        InlineKeyboardButton("◀️ Назад", callback_data="back")
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data == "buy_crypto")
async def buy_crypto_prompt(callback: types.CallbackQuery):
    await callback.message.answer("Введите сумму в ₽, которую хотите потратить на покупку:")
    await ConfigBusiness.waiting_for_value.set()
    await dp.current_state().update_data(action="buy")

@dp.callback_query_handler(lambda c: c.data == "sell_crypto")
async def sell_crypto_prompt(callback: types.CallbackQuery):
    await callback.message.answer("Введите количество монет, которое хотите продать (например 1.5):")
    await ConfigBusiness.waiting_for_value.set()
    await dp.current_state().update_data(action="sell")

@dp.message_handler(state=ConfigBusiness.waiting_for_value)
async def process_crypto_action(message: types.Message, state: FSMContext):
    data = await state.get_data()
    action = data.get("action")
    user_id = message.from_user.id
    try:
        if action == "buy":
            amount_rub = float(message.text)
            if amount_rub <= 0:
                raise ValueError
            price = await db.get_crypto_price()
            crypto_amount = amount_rub / price
            balance = await db.get_balance(user_id)
            if balance < amount_rub:
                await message.answer("❌ Не хватает денег.")
            else:
                await db.update_balance(user_id, -amount_rub)
                await db.update_crypto_amount(user_id, crypto_amount)
                await message.answer(f"✅ Куплено {crypto_amount:.4f} монет за {utils.format_number(amount_rub)} ₽")
        elif action == "sell":
            crypto_amount = float(message.text)
            if crypto_amount <= 0:
                raise ValueError
            price = await db.get_crypto_price()
            rub_amount = crypto_amount * price
            holdings = await db.get_crypto_amount(user_id)
            if holdings < crypto_amount:
                await message.answer("❌ У вас столько монет нет.")
            else:
                await db.update_crypto_amount(user_id, -crypto_amount)
                await db.update_balance(user_id, rub_amount)
                await message.answer(f"✅ Продано {crypto_amount:.4f} монет за {utils.format_number(rub_amount)} ₽")
    except ValueError:
        await message.answer("❌ Введите корректное число.")
    await state.finish()
    await crypto_menu(await message.answer("."))  # костыль для обновления
    await main_menu(user_id)

# ========== РЕЙТИНГ ==========
@dp.callback_query_handler(lambda c: c.data == "rating")
async def rating_menu(callback: types.CallbackQuery):
    top = await db.get_top_players(10)
    profile = await db.get_player_profile(callback.from_user.id)
    text = "🏆 *Топ-10 игроков*\n\n"
    for i, p in enumerate(top, 1):
        text += f"{i}. {p['nickname']} — уровень {p['level']} (заработано {utils.format_number(p['total_earned'])} ₽)\n"
    text += f"\n📊 *Ваш профиль*\n"
    text += f"💰 Баланс: {utils.format_number(profile['balance'])} ₽\n"
    text += f"🏢 Бизнесов: {profile['businesses_count']}\n"
    text += f"₿ Крипта: {profile['crypto_amount']:.4f} монет\n"
    text += f"🏆 Всего заработано: {utils.format_number(profile['total_earned'])} ₽"
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Назад", callback_data="back"))
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

# ========== НАСТРОЙКИ ==========
@dp.callback_query_handler(lambda c: c.data == "settings")
async def settings_menu(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    theme = "🌞 Светлая" if not user.get("dark_theme") else "🌙 Тёмная"
    text = f"⚙️ *Настройки*\n\nТема: {theme}\nНикнейм: {user['nickname']}"
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🎨 Сменить тему", callback_data="toggle_theme"),
        InlineKeyboardButton("✏️ Сменить никнейм", callback_data="change_nickname"),
        InlineKeyboardButton("◀️ Назад", callback_data="back")
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data == "toggle_theme")
async def toggle_theme(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    new_dark = not user.get("dark_theme", False)
    await db.update_theme(callback.from_user.id, new_dark)
    await callback.answer("Тема изменена!")
    await settings_menu(callback)

@dp.callback_query_handler(lambda c: c.data == "change_nickname")
async def change_nickname_prompt(callback: types.CallbackQuery):
    await callback.message.answer("Введите новый никнейм (уникальный):")
    await ConfigBusiness.waiting_for_value.set()
    await dp.current_state().update_data(action="nickname")

@dp.message_handler(state=ConfigBusiness.waiting_for_value)
async def process_nickname_change(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if data.get("action") == "nickname":
        new_nick = message.text
        success = await db.update_nickname(message.from_user.id, new_nick)
        if success:
            await message.answer(f"✅ Никнейм изменён на {new_nick}")
        else:
            await message.answer("❌ Никнейм уже занят.")
        await state.finish()
        await main_menu(message.from_user.id)
    else:
        await state.finish()

# ========== НАЗАД ==========
@dp.callback_query_handler(lambda c: c.data == "back")
async def back_to_menu(callback: types.CallbackQuery):
    await main_menu(callback.from_user.id)

# ========== СТАРТ ==========
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if not user:
        nickname = f"User{user_id}"
        await db.create_user(user_id, nickname)
    await main_menu(user_id)

# ========== ФОНОВАЯ ЗАДАЧА (ДОХОД) ==========
async def background_income():
    while True:
        await asyncio.sleep(60)
        try:
            await logic.calculate_all_incomes()
            print("✅ Доходы обновлены")
        except Exception as e:
            print(f"❌ Ошибка дохода: {e}")

# ========== ЗАПУСК ==========
async def main():
    await db.init_db()
    asyncio.create_task(background_income())
    print("🤖 Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())