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

DM_REPLY = "@anastasia1732"

DB_PATH = Path("bot_state.sqlite3")
SLOTS_RE = re.compile(r"МЕСТ\s*[:\-]?\s*(\d+)", re.IGNORECASE)
HASHTAG_RE = re.compile(r"#([^\s#]+)")

DM_PATTERNS = [
    r"в\s*личку",
    r"\bлс\b",
    r"личные",
    r"напишите\s*в\s*личку",
    r"подскажите",
    r"подскажи",
    r"расскажите",
    r"расскажи",
    r"уточните",
    r"уточни",
    r"скажите",
    r"скажи",
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
    r"\b(\d+)\s*акк(?:а|ов)?\b",
    r"\b(\d+)\s*аккаунт(?:а|ов)?\b",
    r"\b(\d+)\s*мест(?:а)?\b",
    r"\b(\d+)\s*чел(?:овек)?\b",
]

def get_bot_token():
    for name in ("BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "TOKEN", "TG_BOT_TOKEN"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reservations (
                chat_id INTEGER NOT NULL,
                root_message_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                seats INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (chat_id, root_message_id, user_id)
            )
            """
        )
        conn.commit()

def get_message_text(message):
    parts = []
    if getattr(message, "text", None):
        parts.append(message.text)
    if getattr(message, "caption", None):
        parts.append(message.caption)
    return "\n".join(parts).strip()

def extract_slots_limit(text):
    if not text:
        return None
    m = SLOTS_RE.search(text)
    return int(m.group(1)) if m else None

def should_tag_manager(message):
    text = get_message_text(message).lower()

    if getattr(message, "photo", None) or getattr(message, "document", None):
        return True

    if "?" in text:
        return True

    for pattern in DM_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def is_cancel_message(text):
    if not text:
        return False
    text = text.lower()
    return any(re.search(p, text, re.IGNORECASE) for p in CANCEL_PATTERNS)

def extract_quantity(text):
    if not text:
        return 1

    text = text.lower()
    for pattern in QUANTITY_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            qty = int(m.group(1))
            return max(1, qty)

    return 1

def extract_second_hashtag_phrase(post_text):
    if not post_text:
        return ""
    hashtags = HASHTAG_RE.findall(post_text)
    if len(hashtags) < 2:
        return ""
    return hashtags[1].replace("_", " ").strip()

def build_reply_text(post_text):
    phrase = extract_second_hashtag_phrase(post_text)
    if not phrase:
        phrase = "товар"
    return (
        "Одобрено WB:\n"
        f"1. Введите фразу: {phrase}\n"
        "2. Оформляйте заказ (сверьте артикул и магазин)\n"
        "3. Прикрепите скриншот заказа с датой доставки и ПВЗ\n"
        "4. Забрать товар необходимо в день прихода на ПВЗ\n"
        "5. Присылайте скрины и данные в директ\n"
        "6. Выплата кэшбэка в течение 7 дней"
    )

def get_user_seats(chat_id, root_id, user_id):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT seats FROM reservations WHERE chat_id=? AND root_message_id=? AND user_id=?",
            (chat_id, root_id, user_id),
        ).fetchone()
    return int(row[0]) if row else 0

def get_taken_seats(chat_id, root_id):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(seats), 0) FROM reservations WHERE chat_id=? AND root_message_id=?",
            (chat_id, root_id),
        ).fetchone()
    return int(row[0]) if row else 0

def add_user_seats(chat_id, root_id, user_id, seats_to_add):
    current = get_user_seats(chat_id, root_id, user_id)
    new_value = current + seats_to_add
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO reservations (chat_id, root_message_id, user_id, seats)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id, root_message_id, user_id)
            DO UPDATE SET seats=excluded.seats
            """,
            (chat_id, root_id, user_id, new_value),
        )
        conn.commit()
    return new_value

def remove_user_seats(chat_id, root_id, user_id, seats_to_remove):
    current = get_user_seats(chat_id, root_id, user_id)
    if current <= 0:
        return 0, 0

    removed = min(current, seats_to_remove)
    left = current - removed

    with sqlite3.connect(DB_PATH) as conn:
        if left > 0:
            conn.execute(
                "UPDATE reservations SET seats=? WHERE chat_id=? AND root_message_id=? AND user_id=?",
                (left, chat_id, root_id, user_id),
            )
        else:
            conn.execute(
                "DELETE FROM reservations WHERE chat_id=? AND root_message_id=? AND user_id=?",
                (chat_id, root_id, user_id),
            )
        conn.commit()

    return removed, left

async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.from_user:
        return

    text = get_message_text(message)
    reply_to = message.reply_to_message

    if reply_to and reply_to.sender_chat:
        chat_id = message.chat_id
        root_id = reply_to.message_id
        user_id = message.from_user.id

        if is_cancel_message(text):
            qty = extract_quantity(text)
            removed, left = remove_user_seats(chat_id, root_id, user_id, qty)
            if removed > 0:
                await message.reply_text(f"Освобождено мест: {removed}. Осталось у вас: {left}.")
            return

    if should_tag_manager(message):
        await message.reply_text(DM_REPLY)
        return

    if not (reply_to and reply_to.sender_chat):
        return

    post_text = get_message_text(reply_to)
    limit = extract_slots_limit(post_text)
    if limit is None:
        return

    chat_id = message.chat_id
    root_id = reply_to.message_id
    user_id = message.from_user.id

    qty = extract_quantity(text)
    taken = get_taken_seats(chat_id, root_id)
    free = max(0, limit - taken)

    if free <= 0:
        await message.reply_text("Набор закрыт.")
        return

    reserve_qty = min(qty, free)
    new_user_total = add_user_seats(chat_id, root_id, user_id, reserve_qty)
    total_taken = get_taken_seats(chat_id, root_id)

    reply_text = build_reply_text(post_text)

    await message.reply_text(
        f"Занято мест: {reserve_qty}. Всего у вас под этим постом: {new_user_total}. "
        f"Итого занято: {total_taken}/{limit}.\n\n{reply_text}"
    )

    if reserve_qty < qty:
        await message.reply_text(f"Свободных мест было меньше, чем запрошено. Добавлено только {reserve_qty}.")

    if total_taken >= limit:
        await message.reply_text("Набор закрыт.")

def main():
    token = get_bot_token()
    if not token:
        print("Не найден BOT_TOKEN")
        sys.exit(1)

    init_db()

    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(~filters.COMMAND, handle_comment))

    print("Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
