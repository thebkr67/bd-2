import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

# вставьте токен вашего бота от @BotFather
BOT_TOKEN = "PASTE_YOUR_BOT_TOKEN_HERE"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message

    if not message or not message.text:
        return

    # реагируем только на "+"
    if message.text.strip() != "+":
        return

    # проверяем что это комментарий к посту канала
    if message.reply_to_message and message.reply_to_message.sender_chat:
        await message.reply_text("принято")

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment)
    )

    print("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
