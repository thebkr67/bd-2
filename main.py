import logging
import os
import sys

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

def get_bot_token() -> str:
    """
    Ищем токен в нескольких популярных переменных окружения.
    Это удобно для Render / Railway / Docker / панели хостинга.
    """
    possible_names = [
        "BOT_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "TOKEN",
        "TG_BOT_TOKEN",
    ]

    for name in possible_names:
        value = os.getenv(name, "").strip()
        if value:
            return value

    return ""

async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message

    if not message or not message.text:
        return

    # Реагируем только на "+"
    if message.text.strip() != "+":
        return

    # Только комментарии к постам канала
    reply_to = message.reply_to_message
    if reply_to and reply_to.sender_chat:
        await message.reply_text("принято")

def main() -> None:
    token = get_bot_token()

    if not token:
        print(
            "ОШИБКА: токен бота не найден.\n\n"
            "Добавьте переменную окружения с одним из названий:\n"
            "BOT_TOKEN\n"
            "TELEGRAM_BOT_TOKEN\n"
            "TOKEN\n"
            "TG_BOT_TOKEN\n\n"
            "Пример для Render/Railway: создайте переменную BOT_TOKEN и вставьте туда токен от @BotFather."
        )
        sys.exit(1)

    if ":" not in token:
        print(
            "ОШИБКА: токен выглядит некорректно.\n"
            "Проверьте, что вы вставили полный токен от @BotFather, например:\n"
            "123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        )
        sys.exit(1)

    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment))

    print("Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
