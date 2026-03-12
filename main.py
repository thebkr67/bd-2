
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

REPLY_TEXT = """Одобрено WB:
1. Введите фразу: Classmark
2. Оформляйте заказ (сверьте артикул и магазин)
3. Прикрепите скриншот заказа с датой доставки и ПВЗ
4. Забрать товар необходимо в день прихода на ПВЗ
5. Присылайте скрины и данные в директ
6. Выплата кэшбэка в течение 7 дней"""

# Ответ если написали "в личку"
DM_REPLY = "@anastasia1732"

DB_PATH = Path("bot_state.sqlite3")
SLOTS_RE = re.compile(r"МЕСТ\s*[:\-]?\s*(\d+)", re.IGNORECASE)

# триггеры "в личку"
DM_PATTERNS = [
    r"в\s*личку",
    r"лс",
    r"личные",
    r"напишите\s*в\s*личку"
]

def get_bot_token():
    for name in ("BOT_TOKEN","TELEGRAM_BOT_TOKEN","TOKEN","TG_BOT_TOKEN"):
        value=os.getenv(name,"").strip()
        if value:
            return value
    return ""

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS approved_users (
            chat_id INTEGER,
            root_message_id INTEGER,
            user_id INTEGER,
            PRIMARY KEY(chat_id,root_message_id,user_id)
        )
        """)
        conn.commit()

def extract_slots_limit(text):
    if not text:
        return None
    m=SLOTS_RE.search(text)
    return int(m.group(1)) if m else None

def get_post_text(reply):
    parts=[]
    if reply.text:
        parts.append(reply.text)
    if reply.caption:
        parts.append(reply.caption)
    return "\n".join(parts)

def is_dm_message(text):
    text=text.lower()
    for p in DM_PATTERNS:
        if re.search(p,text):
            return True
    return False

def is_user_approved(chat_id,root_id,user_id):
    with sqlite3.connect(DB_PATH) as conn:
        row=conn.execute(
        "SELECT 1 FROM approved_users WHERE chat_id=? AND root_message_id=? AND user_id=?",
        (chat_id,root_id,user_id)).fetchone()
    return row is not None

def approved_count(chat_id,root_id):
    with sqlite3.connect(DB_PATH) as conn:
        row=conn.execute(
        "SELECT COUNT(*) FROM approved_users WHERE chat_id=? AND root_message_id=?",
        (chat_id,root_id)).fetchone()
    return row[0] if row else 0

def add_user(chat_id,root_id,user_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
        "INSERT OR IGNORE INTO approved_users VALUES (?,?,?)",
        (chat_id,root_id,user_id))
        conn.commit()

async def handle_comment(update:Update,context:ContextTypes.DEFAULT_TYPE):

    message=update.effective_message
    if not message or not message.text or not message.from_user:
        return

    text=message.text.lower()

    # если пишут "в личку" или "лс"
    if is_dm_message(text):
        await message.reply_text(DM_REPLY)
        return

    reply_to=message.reply_to_message

    if not(reply_to and reply_to.sender_chat):
        return

    post_text=get_post_text(reply_to)
    limit=extract_slots_limit(post_text)

    if limit is None:
        return

    chat_id=message.chat_id
    root_id=reply_to.message_id
    user_id=message.from_user.id

    if is_user_approved(chat_id,root_id,user_id):
        await message.reply_text("Вы уже заняли место под этим постом.")
        return

    count=approved_count(chat_id,root_id)

    if count>=limit:
        await message.reply_text("Набор закрыт.")
        return

    add_user(chat_id,root_id,user_id)

    place=count+1

    await message.reply_text(f"Место {place}/{limit} занято.\n\n{REPLY_TEXT}")

    if place>=limit:
        await message.reply_text("Набор закрыт.")

def main():

    token=get_bot_token()

    if not token:
        print("Не найден BOT_TOKEN")
        sys.exit(1)

    init_db()

    app=Application.builder().token(token).build()

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND,handle_comment)
    )

    print("Бот запущен")

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=="__main__":
    main()
