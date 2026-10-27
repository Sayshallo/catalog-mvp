
import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton, BotCommand, BotCommandScopeChat
from aiogram.filters import Command
import aiogram.exceptions
import aiohttp
from aiogram.exceptions import TelegramNetworkError

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_API_TOKEN = os.getenv("BOT_API_TOKEN")
API_URL = os.getenv("API_URL", "http://195.93.252.55:8000")
WEBAPP_URL = os.getenv("WEBAPP_URL")
ADMIN_ID_VALUE = os.getenv("ADMIN_ID")

if not BOT_API_TOKEN: raise RuntimeError("Не был задан BOT_API_TOKEN")
if not ADMIN_ID_VALUE: raise RuntimeError("Не был задан ADMIN_ID_VALUE")
if not WEBAPP_URL: raise RuntimeError("Не был задан WEBAPP_URL")
if not BOT_TOKEN: raise RuntimeError("Не был задан BOT_TOKEN")

ADMIN_ID = int(ADMIN_ID_VALUE)
bot = Bot(token = BOT_TOKEN)
dp = Dispatcher()
waiting_for_product = set()

def get_keyboard(user_id):
    buttons = [
        [KeyboardButton(text="Открыть каталог", web_app=WebAppInfo(url=WEBAPP_URL))],
        [KeyboardButton(text="Помощь")]
    ]

    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="Добавить товар")])
        buttons.append([KeyboardButton(text="Отмена")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


@dp.message(Command("start"))
async def start(message: Message):
    user_id = message.from_user.id if message.from_user else 0

    kb = InlineKeyboardMarkup(
        inline_keyboard = [[
            InlineKeyboardButton(text="-> Открыть каталог <-",
                web_app = WebAppInfo(url=WEBAPP_URL))
        ]]
    )
    await message.answer("У меня есть товар! Нажмите кнопку, чтобы открыть каталог", reply_markup=kb)
    await message.answer("Выберите действие", reply_markup=get_keyboard(user_id))


@dp.message(Command("help"))
@dp.message(F.text == "Помощь")
async def help_command(message: Message):
    user_id = message.from_user.id if message.from_user else 0

    help_text = "Доступные команды:\n" \
            "/start - открыть каталог\n" \
            "/help - помощь\n"

    if user_id == ADMIN_ID:
        help_text += "/add_product - добавить товар\n" \
                "/cancel - отменить добавление товара\n\n" \
                "Чтобы добавить товар, нажмите «Добавить товар» и отправьте фотографию с названием в подписи."

    await message.answer(help_text, reply_markup=get_keyboard(user_id))


@dp.message(Command("add_product"))
@dp.message(F.text == "Добавить товар")
async def start_add_product(message: Message):
    
    if message.from_user is None or message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет прав для совершения данной операции")
        return

    waiting_for_product.add(message.from_user.id) 
    await message.answer(
        "Пришлите фотографию товара с названием в подписи.\n"
        "Сообщения без фотографии или описания - будут игнорироваться!\n"
        "Для отмены отправьте /cancel."
    )


@dp.message(Command("cancel"))
@dp.message(F.text == "Отмена")
async def cancel_add_product(message: Message):
    if message.from_user is None:
        return

    if message.from_user.id in waiting_for_product:
        waiting_for_product.discard(message.from_user.id)
        await message.answer("Добавление товара отменено.")
    else:
        await message.answer("Сейчас добавление товара не запущено.")


@dp.message(F.photo & F.caption)
async def add_product(message: Message):
    if message.from_user is None or message.from_user.id != ADMIN_ID:
        return

    if message.from_user.id not in waiting_for_product:
        return

    caption = message.caption.strip()


    if not message.photo:
        await message.answer("Пришлите фотографию товара с названием в подписи")
        return

    if not message.caption or not message.caption.strip():
        await message.answer("Укажите название товара в подписи к фотографии")
        return

    
    photo = message.photo[-1]

    try:
        file = await bot.get_file(photo.file_id)
        photo_stream = await bot.download_file(file.file_path)
    except Exception as exc:
        from aiogram.exceptions import TelegramNetworkError
        if isinstance(exc, TelegramNetworkError):
            await message.answer("Произошла ошибка при связи с сервером, попробуйте позже")
            print("Ошибка при загрузке фотографии:", repr(exc))
            return
        raise

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
                    waiting_for_product.discard(message.from_user.id)
                else:
                    await message.answer("Ошибка при добавлении товара...")
        except aiohttp.ClientError: await message.answer("Произошла ошибка при связи с сервером, попробуйте позже")
        except TimeoutError: await message.answer("Превышено время ожидания, попробуйте позже")


@dp.message()
async def unknown_message(message: Message):
    text = message.text or ""

    if text.startswith("/"):
        await message.answer("Не распознал такой команды")
    else:
        await message.answer("Не понял сообщение. Используйте /help для списка доступных команд.")


async def main():
    try:

        await bot.set_my_commands([
            BotCommand(command="start", description="Открыть каталог"),
            BotCommand(command="help", description="Помощь"),
        ])

        await bot.set_my_commands(
            [
                BotCommand(command="add_product", description="Добавить товар"),
                BotCommand(command="cancel", description="Отменить добавление товара"),
            ],
            scope=BotCommandScopeChat(chat_id=ADMIN_ID),
        )

        await dp.start_polling(bot)
    except TelegramNetworkError as tg_ex:
        print(f"Не удалось установить команду {tg_ex}")

if __name__ == "__main__":
    asyncio.run(main())
