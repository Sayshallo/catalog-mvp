import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton, BotCommand, BotCommandScopeChat
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.exceptions import TelegramNetworkError
import aiohttp

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_API_TOKEN = os.getenv("BOT_API_TOKEN")
API_URL = os.getenv("API_URL", "http://backend:8000")
WEBAPP_URL = os.getenv("WEBAPP_URL")
ADMIN_ID_VALUE = os.getenv("ADMIN_ID")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/telegram/webhook")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
WEB_SERVER_HOST = os.getenv("WEB_SERVER_HOST", "0.0.0.0")
WEB_SERVER_PORT = int(os.getenv("WEB_SERVER_PORT", "8080"))

if not BOT_API_TOKEN: raise RuntimeError("Не был задан BOT_API_TOKEN")
if not ADMIN_ID_VALUE: raise RuntimeError("Не был задан ADMIN_ID_VALUE")
if not WEBAPP_URL: raise RuntimeError("Не был задан WEBAPP_URL")
if not BOT_TOKEN: raise RuntimeError("Не был задан BOT_TOKEN")
if not WEBHOOK_URL: raise RuntimeError("Не был задан WEBHOOK_URL")
if not WEBHOOK_SECRET: raise RuntimeError("Не был задан WEBHOOK_SECRET")

ADMIN_ID = int(ADMIN_ID_VALUE)
bot = Bot(token=BOT_TOKEN)
storage = RedisStorage.from_url(REDIS_URL)
dp = Dispatcher(storage=storage)


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
async def start_add_product(message: Message, state: FSMContext):
    if message.from_user is None or message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет прав для совершения данной операции")
        return

    await state.set_state("waiting_for_product")
    await message.answer(
        "Пришлите фотографию товара с названием в подписи.\n"
        "Сообщения без фотографии или описания - будут игнорироваться!\n"
        "Для отмены отправьте /cancel."
    )


@dp.message(Command("cancel"))
@dp.message(F.text == "Отмена")
async def cancel_add_product(message: Message, state: FSMContext):
    if message.from_user is None:
        return

    current_state = await state.get_state()
    if current_state == "waiting_for_product":
        await state.clear()
        await message.answer("Добавление товара отменено.")
    else:
        await message.answer("Сейчас добавление товара не запущено.")


@dp.message(F.photo & F.caption)
async def add_product(message: Message, state: FSMContext):
    if message.from_user is None or message.from_user.id != ADMIN_ID:
        return

    current_state = await state.get_state()
    if current_state != "waiting_for_product":
        return

    caption = message.caption.strip()
    photo = message.photo[-1]

    try:
        file = await bot.get_file(photo.file_id)
        photo_stream = await bot.download_file(file.file_path)
    except Exception as exc:
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
        form.add_field("image", photo_bytes, filename="photo.jpg", content_type="image/jpeg")

        try:
            async with session.post(f"{API_URL}/api/products", data=form, headers={"Authorization": f"Bearer {BOT_API_TOKEN}"}) as response:
                if response.status == 200:
                    await message.answer("Товар успешно добавлен!")
                    await state.clear()
                else:
                    await message.answer("Ошибка при добавлении товара...")
        except aiohttp.ClientError: await message.answer("Произошла ошибка при связи с сервером, попробуйте позже")
        except TimeoutError: await message.answer("Превышено время ожидания, попробуйте позже")


@dp.message()
async def unknown_message(message: Message):
    text = message.text or ""

    if text.startswith("/"):
        await message.answer("Не распознал такую команду")
    else:
        await message.answer("Не понял сообщение. Используйте /help для списка доступных команд.")


async def webhook_handler(request: web.Request):
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        raise web.HTTPUnauthorized()

    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)
    return web.Response(text="ok")


async def on_startup(app: web.Application):
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
    await bot.set_webhook(
        url=WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET,
        allowed_updates=dp.resolve_used_update_types(),
    )


async def on_shutdown(app: web.Application):
    await storage.close()
    await bot.session.close()


async def main():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, webhook_handler)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_shutdown)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
    await site.start()
    print(f"Webhook server started on {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
