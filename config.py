import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Токен бота
BOT_TOKEN = os.getenv('BOT_TOKEN')

# ID первого администратора
ADMIN_ID = os.getenv('ADMIN_ID')

# Настройки базы данных
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///data/bot.db')

# Проверяем обязательные переменные
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения")

if not ADMIN_ID:
    print("WARNING: ADMIN_ID не найден в переменных окружения. Первый пользователь станет обычным пользователем.")

# Настройки городов
CITIES = {
    'moscow': 'Москва',
    'kazan': 'Казань'
}

# Роли пользователей
USER_ROLES = {
    'user': 'Пользователь',
    'moderator': 'Модератор',
    'admin': 'Администратор'
}