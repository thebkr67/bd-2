import logging
import os
import re
import sqlite3
import sys
from pathlib import Path

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)

DM_REPLY = "@anastasia1732"

DB_PATH = Path("bot_state.sqlite3")
SLOTS_RE = re.compile(r"МЕСТ\s*[:\-]?\s*(\d+)", re.IGNORECASE)
HASHTAG_RE = re.compile(r"#([^\s#]+)")

DM_PATTERNS = [
    r"в\s*личку", r"\bлс\b", r"подскаж", r"расскаж", r"уточн",
    r"скажи", r"скажите", r"не\s*находит", r"не\s*могу\s*найти", r"где\s*найти"
]

CANCEL_PATTERNS = [
    r"отмена", r"отказ", r"передумал", r"передумала", r"не\s*буду"
]

QUANTITY_PATTERNS = [
    r"\b(\d+)\s*\+",
    r"\b(\d+)\s*акк",
    r"\b(\d+)\s*аккаунт",
    r"\b(\d+)\s*мест",
    r"\b(\d+)\s*(?:отмена|отказ|передумал|передумала|не\s*буду)",
    r"\b(\d+)\b",
]

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS reservations (
            chat_id INTEGER,
            root_id INTEGER,
            user_id INTEGER,
            seats INTEGER,
            PRIMARY KEY(chat_id, root_id, user_id)
        )""")
        conn.commit()

def extract_quantity(text):
    text = text.lower()
    for p in QUANTITY_PATTERNS:
        m = re.search(p, text)
        if m:
            return max(1, int(m.group(1)))
    return 1

def is_cancel(text):
    text = text.lower()
    return any(re.search(p, text) for p in CANCEL_PATTERNS)

def should_tag(message):
    text = (message.text or "").lower()
    if message.photo or message.document:
        return True
    if "?" in text:
        return True
    return any(re.search(p, text) for p in DM_PATTERNS)

def get_post_text(msg):
    return (msg.text or "") + (msg.caption or "")

def extract_limit(text):
    m = SLOTS_RE.search(text)
    return int(m.group(1)) if m else None

def get_taken(chat, root):
    with sqlite3.connect(DB_PATH) as conn:
        r = conn.execute("SELECT COALESCE(SUM(seats),0) FROM reservations WHERE chat_id=? AND root_id=?", (chat, root)).fetchone()
    return r[0]

def get_user(chat, root, user):
    with sqlite3.connect(DB_PATH) as conn:
        r = conn.execute("SELECT seats FROM reservations WHERE chat_id=? AND root_id=? AND user_id=?", (chat, root, user)).fetchone()
    return r[0] if r else 0

def set_user(chat, root, user, seats):
    with sqlite3.connect(DB_PATH) as conn:
        if seats > 0:
            conn.execute("INSERT OR REPLACE INTO reservations VALUES (?,?,?,?)", (chat, root, user, seats))
        else:
            conn.execute("DELETE FROM reservations WHERE chat_id=? AND root_id=? AND user_id=?", (chat, root, user))
        conn.commit()

def extract_phrase(text):
    tags = HASHTAG_RE.findall(text)
    if len(tags) >= 2:
        return tags[1].replace("_"," ")
    return "товар"

async def handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    m = update.effective_message
    if not m or not m.from_user:
        return

    if should_tag(m):
        await m.reply_text(DM_REPLY)
        return

    if not (m.reply_to_message and m.reply_to_message.sender_chat):
        return

    chat = m.chat_id
    root = m.reply_to_message.message_id
    user = m.from_user.id
    text = (m.text or "")

    if is_cancel(text):
        qty = extract_quantity(text)
        cur = get_user(chat, root, user)
        removed = min(cur, qty)
        set_user(chat, root, user, cur - removed)
        if removed:
            await m.reply_text(f"Освобождено мест: {removed}")
        return

    limit = extract_limit(get_post_text(m.reply_to_message))
    if not limit:
        return

    qty = extract_quantity(text)
    taken = get_taken(chat, root)
    free = limit - taken

    if free <= 0:
        await m.reply_text("Набор закрыт")
        return

    add = min(qty, free)
    cur = get_user(chat, root, user)
    set_user(chat, root, user, cur + add)

    phrase = extract_phrase(get_post_text(m.reply_to_message))

    await m.reply_text(
        f"Занято: {add}. Всего у вас: {cur+add}. {taken+add}/{limit}\n\n"
        f"1. Введите фразу: {phrase}"
        "2. Оформляйте заказ (сверьте артикул и магазин)\n"
        "3. Прикрепите скриншот заказа с датой доставки и ПВЗ\n"
        "4. Забрать товар необходимо в день прихода на ПВЗ\n"
        "5. Присылайте скрины и данные в директ\n"
        "6. Выплата кэшбэка в течение 7 дней"
    )

def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("NO TOKEN"); sys.exit(1)

    init_db()
    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(~filters.COMMAND, handle))
    app.run_polling()

if __name__ == "__main__":
    main()
