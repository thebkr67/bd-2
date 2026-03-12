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
3. Прикрепите скриншот заказа с датой доставки и ПВЗ, а также скриншот поиска по ключевому запросу в комментарии к посту, если сложно найти применяйте фильтр - по цене
4. Забрать товар необходимо в день прихода на ПВЗ, после получения товара, пишите отзыв: 3-5 фото, видеообзор и текст пару предложений (спустя 1-3 дня), перед публикацией отправляйте на согласование: @anastasia1732
5. Присылайте скрин отзыва, скрин из раздела покупок, скрин одобрения, фото разрезанного штрихкода, ссылку на пост с товаром и номер карты в директ @helena_nev1
6. Выплата кэшбэка в течение 7 дней, не включая выходные, до 18:00, в порядке очереди."""

DB_PATH = Path("bot_state.sqlite3")
SLOTS_RE = re.compile(r"МЕСТ\s*[:\-]?\s*(\d+)", re.IGNORECASE)
IGNORE_PHRASE = "в личку"

def get_bot_token() -> str:
    for name in ("BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "TOKEN", "TG_BOT_TOKEN"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""

def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS approved_users (
                chat_id INTEGER NOT NULL,
                root_message_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, root_message_id, user_id)
            )
            """
        )
        conn.commit()

def extract_slots_limit(post_text: str):
    if not post_text:
        return None
    match = SLOTS_RE.search(post_text)
    if not match:
        return None
    return int(match.group(1))

def get_post_text(reply_to_message) -> str:
    parts = []
    if getattr(reply_to_message, "text", None):
        parts.append(reply_to_message.text)
    if getattr(reply_to_message, "caption", None):
        parts.append(reply_to_message.caption)
    return "\n".join(parts).strip()

def is_valid_comment(text: str) -> bool:
    if not text:
        return False
    return IGNORE_PHRASE not in text.lower()

def get_approved_count(chat_id: int, root_message_id: int) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM approved_users
            WHERE chat_id = ? AND root_message_id = ?
            """,
            (chat_id, root_message_id),
        ).fetchone()
    return int(row[0]) if row else 0

def is_user_already_approved(chat_id: int, root_message_id: int, user_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM approved_users
            WHERE chat_id = ? AND root_message_id = ? AND user_id = ?
            LIMIT 1
            """,
            (chat_id, root_message_id, user_id),
        ).fetchone()
    return row is not None

def add_approved_user(chat_id: int, root_message_id: int, user_id: int, username: str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO approved_users (chat_id, root_message_id, user_id, username)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, root_message_id, user_id, username),
        )
        conn.commit()

    return get_approved_count(chat_id, root_message_id)

async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message

    if not message or not message.text or not message.from_user:
        return

    if not is_valid_comment(message.text):
        return

    reply_to = message.reply_to_message

    # Только комментарии к постам канала
    if not (reply_to and reply_to.sender_chat):
        return

    post_text = get_post_text(reply_to)
    limit = extract_slots_limit(post_text)

    # Если в посте нет "МЕСТ N", не отвечаем
    if limit is None:
        return

    chat_id = message.chat_id
    root_message_id = reply_to.message_id
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.full_name

    # Одному пользователю только одно место под одним постом
    if is_user_already_approved(chat_id, root_message_id, user_id):
        await message.reply_text("Вы уже заняли место под этим постом.")
        return

    approved_count = get_approved_count(chat_id, root_message_id)
    if approved_count >= limit:
        await message.reply_text("Набор закрыт.")
        return

    place_number = add_approved_user(chat_id, root_message_id, user_id, username)

    await message.reply_text(
        f"Место {place_number}/{limit} занято.\n\n{REPLY_TEXT}"
    )

    # Если это было последнее место — доп. сообщение о закрытии набора
    if place_number >= limit:
        await message.reply_text("Набор закрыт.")

    logging.info(
        "Одобрен пользователь: chat_id=%s root_message_id=%s user_id=%s place=%s/%s",
        chat_id,
        root_message_id,
        user_id,
        place_number,
        limit,
    )

def main() -> None:
    token = get_bot_token()

    if not token:
        print(
            "ОШИБКА: токен бота не найден.\n"
            "Добавьте переменную окружения BOT_TOKEN "
            "(или TELEGRAM_BOT_TOKEN / TOKEN / TG_BOT_TOKEN)."
        )
        sys.exit(1)

    if ":" not in token:
        print("ОШИБКА: токен выглядит некорректно.")
        sys.exit(1)

    init_db()

    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment))

    print("Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
