import socketio
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InputFile
from aiogram.filters import Command

# Создаем клиент для подключения к серверу
sio = socketio.AsyncClient()

# Токен вашего бота Telegram
TELEGRAM_TOKEN = '8044348316:AAF_JCqYm1bZ35xDXHanoOLDTflqiqfaPyA'

# Инициализируем бота
bot = Bot(token=TELEGRAM_TOKEN)

# Создаем экземпляр диспетчера
dp = Dispatcher()

# Словарь для хранения chat_id пользователей и их состояния (получают ли они обновления)
users_status = {}

# Функция для обработки события 'newMint'
@sio.event
async def newMint(data):
    # Извлекаем ключевые данные из сообщения
    slug = data.get('slug', 'Неизвестен')
    gift_name = data.get('gift_name', 'Неизвестен')
    number = data.get('number', 'Неизвестен')
    image_preview = data.get('image_preview', None)

    # Форматируем и выводим сообщение
    formatted_message = f"Новый минт - *{slug}* - *{gift_name}* - *{number}*"
    print(formatted_message)

    # Если есть изображение, отправляем по URL
    if image_preview:
        try:
            # Отправляем изображение только тем пользователям, кто не выключил обновления
            for user_id, status in users_status.items():
                if status['status'] == 'active':  # Отправляем только активным пользователям
                    chat_id = status['chat_id']
                    await bot.send_photo(chat_id=chat_id, photo=image_preview, caption=formatted_message)
        except Exception as e:
            print(f"Ошибка при отправке изображения: {e}")
    else:
        # Если изображения нет, отправляем только текст
        for user_id, status in users_status.items():
            if status['status'] == 'active':  # Отправляем только активным пользователям
                chat_id = status['chat_id']
                await bot.send_message(chat_id=chat_id, text=formatted_message)

# Обработчик для команды /start
@dp.message(Command('start'))
async def start_command(message: types.Message):
    # Сохраняем chat_id пользователя и устанавливаем статус 'active' (получает сообщения)
    users_status[message.from_user.id] = {'chat_id': message.chat.id, 'status': 'active'}
    await message.reply("""Hello! I’m a bot that helps you stay updated on new gift mints. You will now receive a notification about each new gift mint.

To pause notifications about mints, send the command - /stop

Subscribe to our news channel so you don’t miss the latest bot update - @GiftsMinter

Our channel with notifications about new gift releases - @TGGiftsNews""")

# Обработчик для команды /stop
@dp.message(Command('stop'))
async def stop_command(message: types.Message):
    # Проверяем, подписан ли пользователь
    if message.from_user.id in users_status:
        # Устанавливаем статус 'inactive' (не получает сообщения)
        users_status[message.from_user.id]['status'] = 'inactive'
        await message.reply("""You will no longer receive notifications about new gift mints.

To resume receiving notifications, send the command /start""")
    else:
        await message.reply("You will no longer receive notifications about new gift mints")

# Обработчик для общего события
@sio.event
async def connect():
    print("Подключение установлено!")

# Обработчик для получения сообщений
@sio.event
async def message(data):
    # Пример обработки входящего сообщения
    if isinstance(data, dict) and 'gift_name' in data and 'number' in data:
        # Извлекаем данные и форматируем их
        gift_name = data.get('gift_name', 'Неизвестен')
        number = data.get('number', 'Неизвестен')
        image_preview = data.get('image_preview', None)
        formatted_message = f"New mint - {gift_name} - #{number}"

        # Если есть изображение, отправляем его по URL
        if image_preview:
            try:
                for user_id, status in users_status.items():
                    if status['status'] == 'active':  # Отправляем только активным пользователям
                        chat_id = status['chat_id']
                        await bot.send_photo(chat_id=chat_id, photo=image_preview, caption=formatted_message)
            except Exception as e:
                print(f"Ошибка при отправке изображения: {e}")
        else:
            for user_id, status in users_status.items():
                if status['status'] == 'active':  # Отправляем только активным пользователям
                    chat_id = status['chat_id']
                    await bot.send_message(chat_id=chat_id, text=formatted_message)

# Обработчик для ошибки подключения
@sio.event
async def connect_error(data):
    print("Ошибка подключения:", data)

# Обработчик для отключения
@sio.event
async def disconnect():
    print("Отключено от сервера")

# Функция для подключения к серверу
async def connect_to_server():
    try:
        # Подключаемся к серверу
        await sio.connect('https://gsocket.trump.tg')
        print("Подключение успешно!")
    except Exception as e:
        print(f"Ошибка при подключении: {e}")

# Основной блок программы
async def main():
    await connect_to_server()
    # Запускаем поллинг (проверку новых сообщений)
    await dp.start_polling(bot)

# Запуск программы
if __name__ == '__main__':
    asyncio.run(main())
