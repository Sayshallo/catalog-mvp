import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import Command
import aiohttp

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_API_TOKEN = os.getenv("BOT_API_TOKEN")
API_URL = os.getenv("API_URL", "http://backend:8000")
WEBAPP_URL = os.getenv("WEBAPP_URL")
ADMIN_ID_VALUE = os.getenv("ADMIN_ID")

if not BOT_API_TOKEN: raise RuntimeError("Не был задан BOT_API_TOKEN")
if not ADMIN_ID_VALUE: raise RuntimeError("Не был задан ADMIN_ID_VALUE")
if not WEBAPP_URL: raise RuntimeError("Не был задан WEBAPP_URL")
if not BOT_TOKEN: raise RuntimeError("Не был задан BOT_TOKEN")

ADMIN_ID = int(ADMIN_ID_VALUE)
bot = Bot(token = BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard = [[
            InlineKeyboardButton(text="-> Открыть каталог <-",
                web_app = WebAppInfo(url=WEBAPP_URL))
        ]]
    )
    await message.answer("У меня есть товар! Нажмите кнопку, чтобы открыть каталог", reply_markup=kb)

@dp.message(F.photo & F.caption)
async def add_product(message: Message): 
    if message.from_user is None or message.from_user.id != ADMIN_ID:
        return
    caption = message.caption.strip()

    if not caption:
        await message.answer("Укажите название товара в подписи к фотографии")
        return

    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    photo_stream = await bot.download_file(file.file_path)

    if photo_stream is None:
        await message.answer("Не удалось загрузить фотографию")
        return

    photo_bytes = photo_stream.read()

    async with aiohttp.ClientSession() as session:
        form = aiohttp.FormData()
        form.add_field("title", caption)
        form.add_field("image", photo_bytes, filename = "photo.jpg", content_type = "image/jpeg")

        try:
            async with session.post(f"{API_URL}/api/products", data=form, headers = {"Authorization": f"Bearer {BOT_API_TOKEN}"}) as response:
                if response.status == 200:
                    await message.answer("Товар успешно добавлен!")
                else:
                    await message.answer("Ошибка при добавлении товара...")
        except aiohttp.ClientError: await message.answer("Произошла ошибка при связи с сервером, попробуйте позже")
        except TimeoutError: await message.answer("Превышено время ожидания, попробуйте позже")


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())