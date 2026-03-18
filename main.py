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
    r"в\s*личку",
    r"\bлс\b",
    r"подскаж",
    r"расскаж",
    r"уточн",
    r"скажи",
    r"скажите",
    r"не\s*находит",
    r"не\s*могу\s*найти",
    r"где\s*найти",
]

CANCEL_PATTERNS = [
    r"отмена",
    r"отказ",
    r"передумал",
    r"передумала",
    r"не\s*буду",
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
        conn.execute(
            """CREATE TABLE IF NOT EXISTS reservations (
                chat_id INTEGER,
                root_id INTEGER,
                user_id INTEGER,
                seats INTEGER,
                PRIMARY KEY(chat_id, root_id, user_id)
            )"""
        )
        conn.commit()

def extract_quantity(text):
    text = (text or "").lower()
    for pattern in QUANTITY_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return max(1, int(m.group(1)))
    return 1

def is_cancel(text):
    text = (text or "").lower()
    return any(re.search(pattern, text) for pattern in CANCEL_PATTERNS)

def should_tag(message):
    text = ((message.text or "") + "\n" + (message.caption or "")).lower()
    if getattr(message, "photo", None) or getattr(message, "document", None):
        return True
    if "?" in text:
        return True
    return any(re.search(pattern, text) for pattern in DM_PATTERNS)

def get_post_text(msg):
    return ((msg.text or "") + "\n" + (msg.caption or "")).strip()

def extract_limit(text):
    m = SLOTS_RE.search(text or "")
    return int(m.group(1)) if m else None

def get_taken(chat, root):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(seats),0) FROM reservations WHERE chat_id=? AND root_id=?",
            (chat, root),
        ).fetchone()
    return int(row[0]) if row else 0

def get_user(chat, root, user):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT seats FROM reservations WHERE chat_id=? AND root_id=? AND user_id=?",
            (chat, root, user),
        ).fetchone()
    return int(row[0]) if row else 0

def set_user(chat, root, user, seats):
    with sqlite3.connect(DB_PATH) as conn:
        if seats > 0:
            conn.execute(
                "INSERT OR REPLACE INTO reservations VALUES (?,?,?,?)",
                (chat, root, user, seats),
            )
        else:
            conn.execute(
                "DELETE FROM reservations WHERE chat_id=? AND root_id=? AND user_id=?",
                (chat, root, user),
            )
        conn.commit()

def extract_phrase(text):
    tags = HASHTAG_RE.findall(text or "")
    if len(tags) >= 2:
        return tags[1].replace("_", " ")
    return "товар"

def build_reply_text(post_text, add, user_total, total_taken, limit):
    phrase = extract_phrase(post_text)
    return (
        f"Занято: {add}. Всего у вас: {user_total}. {total_taken}/{limit}\n\n"
        f"1. Введите фразу: {phrase}\n"
        "2. Оформляйте заказ (сверьте артикул и магазин)\n"
        "3. Прикрепите скриншот заказа с датой доставки и ПВЗ\n"
        "4. Забрать товар необходимо в день прихода на ПВЗ\n"
        "5. Присылайте скрины и данные в директ\n"
        "6. Выплата кэшбэка в течение 7 дней"
    )

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
    text = m.text or m.caption or ""

    current_user_seats = get_user(chat, root, user)

    # Отмена работает после уже существующей брони
    if is_cancel(text):
        qty = extract_quantity(text)
        removed = min(current_user_seats, qty)
        set_user(chat, root, user, current_user_seats - removed)
        if removed:
            await m.reply_text(f"Освобождено мест: {removed}")
        return

    limit = extract_limit(get_post_text(m.reply_to_message))
    if not limit:
        return

    # Если пользователь уже бронировал под этим постом, новые сообщения не учитываем
    if current_user_seats > 0:
        return

    qty = extract_quantity(text)
    taken = get_taken(chat, root)
    free = limit - taken

    if free <= 0:
        await m.reply_text("Набор закрыт")
        return

    add = min(qty, free)
    set_user(chat, root, user, add)
    total_taken = taken + add

    reply_text = build_reply_text(
        get_post_text(m.reply_to_message),
        add,
        add,
        total_taken,
        limit,
    )
    await m.reply_text(reply_text)

    if add < qty:
        await m.reply_text(f"Свободных мест было меньше, чем запрошено. Добавлено только {add}")

    if total_taken >= limit:
        await m.reply_text("Набор закрыт")

def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("NO TOKEN")
        sys.exit(1)

    init_db()
    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(~filters.COMMAND, handle))
    app.run_polling()

if __name__ == "__main__":
    main()
