import logging
import os
import sys

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Можно задать токен через переменную окружения BOT_TOKEN
# или вписать его прямо в строку ниже.
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip() or "PASTE_YOUR_BOT_TOKEN_HERE"

async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message

    if not message or not message.text:
        return

    # Реагируем только на "+"
    if message.text.strip() != "+":
        return

    # Только комментарии к постам канала:
    # у комментария есть reply_to_message, а у самого поста есть sender_chat
    reply_to = message.reply_to_message
    if reply_to and reply_to.sender_chat:
        await message.reply_text("принято")

def validate_token(token: str) -> None:
    if not token or token == "PASTE_YOUR_BOT_TOKEN_HERE":
        print(
            "Ошибка: не указан токен бота.\n"
            "Вставьте токен в переменную BOT_TOKEN в файле main.py\n"
            "или задайте переменную окружения BOT_TOKEN."
        )
        sys.exit(1)

def main() -> None:
    validate_token(BOT_TOKEN)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment))

    print("Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
