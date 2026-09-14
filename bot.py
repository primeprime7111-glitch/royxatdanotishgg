import asyncio
import logging
import os
from datetime import datetime
 
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
import httpx
 
# ---------------------------------------------------------------------------
# SOZLAMALAR (.env faylidan o'qiladi)
# ---------------------------------------------------------------------------
load_dotenv()
 
BOT_TOKEN = os.getenv("BOT_TOKEN")
CARD_NUMBER = os.getenv("CARD_NUMBER", "0000 0000 0000 0000")
CARD_OWNER = os.getenv("CARD_OWNER", "F. F.")
MONTHLY_PRICE = os.getenv("MONTHLY_PRICE", "250 000")
SITE_URL = os.getenv("SITE_URL", "")  # index.html joylashgan manzil (masalan GitHub Pages)
 
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi! .env faylini tekshiring.")
 
_admin_id_raw = os.getenv("ADMIN_ID")
if not _admin_id_raw:
    raise RuntimeError("ADMIN_ID topilmadi! .env faylini tekshiring.")
ADMIN_ID = int(_admin_id_raw)  # chat_id albatta butun son (int) bo'lishi kerak
 
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL yoki SUPABASE_KEY topilmadi! .env faylini tekshiring.")
 
logging.basicConfig(level=logging.INFO)
 
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)
 
# ---------------------------------------------------------------------------
# MA'LUMOTLAR BAZASI (Supabase REST API orqali, to'g'ridan-to'g'ri httpx bilan
# - qo'shimcha og'ir kutubxona shart emas, Railway'da ziddiyat chiqarmaydi)
# ---------------------------------------------------------------------------
async def save_student(data: dict, telegram_id: int, username: str | None):
    payload = {
        "telegram_id": telegram_id,
        "username": username or "-",
        "age": data.get("age"),
        "purpose": data.get("purpose"),
        "why_math": data.get("why_math"),
        "level": data.get("level"),
        "full_name": data.get("full_name"),
    }
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    url = f"{SUPABASE_URL}/rest/v1/students"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
    except Exception as e:
        logging.error(f"Supabase'ga yozishda xato: {e}")
 
 
# ---------------------------------------------------------------------------
# HOLATLAR (FSM) - foydalanuvchi bilan bosqichma-bosqich suhbat
# ---------------------------------------------------------------------------
class Reg(StatesGroup):
    age = State()
    purpose = State()
    why_math = State()
    level = State()
    full_name = State()
    waiting_payment_proof = State()
 
 
# ---------------------------------------------------------------------------
# TUGMALAR
# ---------------------------------------------------------------------------
def age_keyboard() -> InlineKeyboardMarkup:
    ages = list(range(12, 26))  # 12 dan 25 gacha
    rows = []
    row = []
    for i, age in enumerate(ages, start=1):
        row.append(InlineKeyboardButton(text=str(age), callback_data=f"age:{age}"))
        if i % 5 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)
 
 
def purpose_keyboard() -> InlineKeyboardMarkup:
    options = [
        ("Sertifikat uchun", "purpose:sertifikat"),
        ("DTM savollariga tayyorlanish uchun", "purpose:dtm"),
        ("Maktab uchun", "purpose:maktab"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=cb)] for t, cb in options]
    )
 
 
def level_keyboard() -> InlineKeyboardMarkup:
    options = [
        ("0 dan boshlashim kerak", "level:0"),
        ("O'quvlarim yaxshi, lekin baribir xotirjam emasman", "level:1"),
        ("Maktabda hammadan zo'r bo'lishim kerak", "level:2"),
        ("Sertifikatim bor, lekin yana o'qimoqchiman", "level:3"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=cb)] for t, cb in options]
    )
 
 
def site_keyboard() -> InlineKeyboardMarkup | None:
    if not SITE_URL:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🌐 Markaz haqida batafsil", url=SITE_URL)]]
    )
 
 
# ---------------------------------------------------------------------------
# HANDLERLAR
# ---------------------------------------------------------------------------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Assalomu alaykum, {message.from_user.first_name}! 👋\n\n"
        "Matematika o'quv markazimizga xush kelibsiz.\n"
        "Ro'yxatdan o'tish uchun bir nechta savolga javob bering.\n\n"
        "Necha yoshdasiz?",
        reply_markup=age_keyboard(),
    )
    site_kb = site_keyboard()
    if site_kb:
        await message.answer("Markazimiz haqida ko'proq bilmoqchi bo'lsangiz:", reply_markup=site_kb)
    await state.set_state(Reg.age)
 
 
@router.callback_query(Reg.age, F.data.startswith("age:"))
async def process_age(callback: CallbackQuery, state: FSMContext):
    age = callback.data.split(":")[1]
    await state.update_data(age=age)
    await callback.message.edit_text(f"Yoshingiz: {age} ✅")
    await callback.message.answer(
        "Matematikaga topshirishingizdan maqsadingiz nima?",
        reply_markup=purpose_keyboard(),
    )
    await state.set_state(Reg.purpose)
    await callback.answer()
 
 
@router.callback_query(Reg.purpose, F.data.startswith("purpose:"))
async def process_purpose(callback: CallbackQuery, state: FSMContext):
    mapping = {
        "sertifikat": "Sertifikat uchun",
        "dtm": "DTM savollariga tayyorlanish uchun",
        "maktab": "Maktab uchun",
    }
    key = callback.data.split(":")[1]
    await state.update_data(purpose=mapping[key])
    await callback.message.edit_text(f"Maqsad: {mapping[key]} ✅")
    await callback.message.answer("Nima uchun aynan sizga matematika kerak? (bir necha so'z bilan yozing)")
    await state.set_state(Reg.why_math)
    await callback.answer()
 
 
@router.message(Reg.why_math)
async def process_why_math(message: Message, state: FSMContext):
    await state.update_data(why_math=message.text)
    await message.answer(
        "Darajangiz qanday?",
        reply_markup=level_keyboard(),
    )
    await state.set_state(Reg.level)
 
 
@router.callback_query(Reg.level, F.data.startswith("level:"))
async def process_level(callback: CallbackQuery, state: FSMContext):
    mapping = {
        "0": "0 dan boshlashim kerak",
        "1": "O'quvlarim yaxshi, lekin baribir xotirjam emasman",
        "2": "Maktabda hammadan zo'r bo'lishim kerak",
        "3": "Sertifikatim bor, lekin yana o'qimoqchiman",
    }
    key = callback.data.split(":")[1]
    await state.update_data(level=mapping[key])
    await callback.message.edit_text(f"Daraja: {mapping[key]} ✅")
    await callback.message.answer("Ism va familyangizni to'liq yozing:")
    await state.set_state(Reg.full_name)
    await callback.answer()
 
 
@router.message(Reg.full_name)
async def process_full_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    data = await state.get_data()
 
    summary = (
        "Ma'lumotlaringiz qabul qilindi ✅\n\n"
        f"👤 Ism familya: {data['full_name']}\n"
        f"🎂 Yosh: {data['age']}\n"
        f"🎯 Maqsad: {data['purpose']}\n"
        f"📝 Nega matematika kerak: {data['why_math']}\n"
        f"📊 Daraja: {data['level']}\n\n"
        "O'quv markazimiz sizni o'qitishga tayyor. Davom etish uchun avval "
        "o'quv haqini to'lashingiz kerak bo'ladi.\n\n"
        f"💰 1 oylik o'qish narxi: {MONTHLY_PRICE} so'm\n"
        f"💳 Karta raqami: {CARD_NUMBER}\n"
        f"👤 Karta egasi: {CARD_OWNER}\n\n"
        "To'lovni amalga oshirgach, chekning skrinshotini shu yerga (rasm sifatida) yuboring."
    )
    await message.answer(summary)
    await state.set_state(Reg.waiting_payment_proof)
 
 
@router.message(Reg.waiting_payment_proof, F.photo)
async def process_payment_proof(message: Message, state: FSMContext):
    data = await state.get_data()
    await save_student(data, message.from_user.id, message.from_user.username)
 
    # Adminга hamma ma'lumot + chek rasmi yuboriladi
    caption = (
        "🆕 Yangi to'lov cheki!\n\n"
        f"👤 Ism familya: {data['full_name']}\n"
        f"🎂 Yosh: {data['age']}\n"
        f"🎯 Maqsad: {data['purpose']}\n"
        f"📝 Nega matematika kerak: {data['why_math']}\n"
        f"📊 Daraja: {data['level']}\n"
        f"🆔 Telegram ID: {message.from_user.id}\n"
        f"👤 Username: @{message.from_user.username or '-'}"
    )
    await bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption=caption)
 
    await message.answer(
        "Rahmat! Chekingiz qabul qilindi ✅\n"
        "Tez orada operatorlarimiz siz bilan bog'lanadi."
    )
    await state.clear()
 
 
@router.message(Reg.waiting_payment_proof)
async def waiting_photo_reminder(message: Message):
    await message.answer("Iltimos, to'lov chekining rasmini (skrinshotini) yuboring 📸")
 
 
# ---------------------------------------------------------------------------
# ISHGA TUSHIRISH
# ---------------------------------------------------------------------------
async def main():
    await dp.start_polling(bot)
 
 
if __name__ == "__main__":
    asyncio.run(main())
 
