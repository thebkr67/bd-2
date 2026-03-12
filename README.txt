Telegram бот: автоответ "принято" на "+" в комментариях канала

Что исправлено:
- бот больше не использует встроенный шаблонный токен
- токен читается из переменных окружения
- поддерживаются имена:
  BOT_TOKEN
  TELEGRAM_BOT_TOKEN
  TOKEN
  TG_BOT_TOKEN
- если токен не найден или он битый, бот завершится с понятным сообщением

Почему была ошибка:
В логах видно ошибку telegram.error.InvalidToken: Not Found.
Это значит, что на хостинге у бота нет корректного токена.

Как запустить на Render / Railway:
1. Загрузите файлы
2. Добавьте ENV-переменную:
   BOT_TOKEN = ваш_токен_от_BotFather
3. Команда установки:
   pip install -r requirements.txt
4. Команда запуска:
   python main.py

Как запустить локально:
Windows PowerShell:
$env:BOT_TOKEN="ВАШ_ТОКЕН"
python main.py

Linux/macOS:
export BOT_TOKEN="ВАШ_ТОКЕН"
python main.py

Важно:
- в @BotFather отключите privacy mode: /setprivacy -> Disable
- добавьте бота именно в группу обсуждения канала
- лучше выдать боту права администратора
