import os
import logging
import asyncio
from threading import Thread

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from openai import AsyncOpenAI
from flask import Flask

# --- НАСТРОЙКИ С КЛЮЧАМИ (ВСТАВЛЕНЫ ВАШИ ДАННЫЕ) ---
# В реальном проекте используйте os.getenv() для безопасности!
TELEGRAM_TOKEN = "8642116706:AAHrj8uLsTtUQ0LLX21yEl53T12tb9IZPM8"
QWEN_API_KEY = "sk-a2bf4093237a4ca08378a8d9622d3c28"

# URL для Qwen (DashScope Alibaba Cloud)
QWEN_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
# Модель: qwen-turbo, qwen-plus, или qwen-max
QWEN_MODEL = "qwen-turbo" 

# Инициализация логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация клиентов
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Клиент для LLM
client = AsyncOpenAI(
    api_key=QWEN_API_KEY,
    base_url=QWEN_BASE_URL
)

# Хранилище контекста: { user_id: [ {"role": "user", "content": "..."}, ... ] }
user_contexts = {}

# Хранилище стилей: { user_id: "строка_стиля" }
user_styles = {}

# Стандартный системный промпт
DEFAULT_SYSTEM_PROMPT = "Ты полезный ассистент."

# --- ФУНКЦИИ ПОМОЩНИКИ ---

def get_system_prompt(user_id):
    """Формирует системный промпт с учетом выбранного стиля."""
    style = user_styles.get(user_id, "")
    base_prompt = DEFAULT_SYSTEM_PROMPT
    if style:
        return f"{base_prompt} Отвечай в следующей манере: {style}"
    return base_prompt

async def ask_qwen(user_id, user_message):
    """Отправляет запрос к Qwen API с сохранением контекста."""
    
    # Инициализируем контекст, если его нет
    if user_id not in user_contexts:
        user_contexts[user_id] = []

    # Добавляем сообщение пользователя в историю
    user_contexts[user_id].append({"role": "user", "content": user_message})

    # Формируем messages для отправки
    messages = [
        {"role": "system", "content": get_system_prompt(user_id)}
    ] + user_contexts[user_id]

    try:
        response = await client.chat.completions.create(
            model=QWEN_MODEL,
            messages=messages,
            temperature=0.7
        )
        
        assistant_message = response.choices[0].message.content
        
        # Сохраняем ответ ассистента в контекст
        user_contexts[user_id].append({"role": "assistant", "content": assistant_message})
        
        return assistant_message

    except Exception as e:
        logger.error(f"Ошибка при запросе к Qwen: {e}")
        return f"Извините, произошла ошибка: {str(e)}"

# --- ОБРАБОТЧИКИ TELEGRAM ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я бот на базе Qwen.\n\n"
        "Я могу отвечать на вопросы, сохраняя контекст беседы.\n\n"
        "Доступные команды:\n"
        "/style <описание> - задать манеру общения (например: /style как пират)\n"
        "/clear - очистить историю переписки и контекст\n"
        "/help - показать это сообщение"
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await cmd_start(message)

@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    user_id = message.from_user.id
    if user_id in user_contexts:
        del user_contexts[user_id]
    if user_id in user_styles:
        del user_styles[user_id]
    await message.answer("🗑️ Контекст и стиль общения сброшены.")

@dp.message(Command("style"))
async def cmd_style(message: Message):
    user_id = message.from_user.id
    style_description = message.text.split(maxsplit=1)
    
    if len(style_description) < 2:
        await message.answer("Пожалуйста, укажите стиль. Пример: /style отвечай кратко")
        return
        
    style_text = style_description[1]
    user_styles[user_id] = style_text
    
    await message.answer(f"✅ Принято! Стиль изменен на: \"{style_text}\"")

@dp.message(F.text)
async def handle_message(message: Message):
    user_id = message.from_user.id
    await bot.send_chat_action(chat_id=user_id, action="typing")
    response_text = await ask_qwen(user_id, message.text)
    await message.answer(response_text)

# --- WEB SERVER ДЛЯ RENDER.COM ---

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

@app.route('/health')
def health_check():
    return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- ЗАПУСК ---

async def main():
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    logger.info("Web server started.")
    
    logger.info("Starting bot polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
