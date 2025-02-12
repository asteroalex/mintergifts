import socketio
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramForbiddenError

# Создаем клиент для подключения к серверу
sio = socketio.AsyncClient()

# Токен вашего бота Telegram
TELEGRAM_TOKEN = '8044348316:AAF_JCqYm1bZ35xDXHanoOLDTflqiqfaPyA'

# Инициализируем бота
bot = Bot(token=TELEGRAM_TOKEN)

# Создаем экземпляр диспетчера
dp = Dispatcher(storage=MemoryStorage())

# Словарь для хранения chat_id пользователей и их состояния (получают ли они обновления)
users_status = {}

# Список разрешенных пользователей
allowed_users = set()

# Список всех пользователей с доступом (ID и имя пользователя)
all_users = {}

# Состояния для FSM (Finite State Machine)
class AlertStates(StatesGroup):
    waiting_for_message = State()

class AllAlertStates(StatesGroup):
    waiting_for_message = State()

# Функция для проверки доступа
def has_access(user_id):
    return user_id in allowed_users

# Функция для обработки события 'newMint'
@sio.event
async def newMint(data):
    print(f"Получены данные о новом минте: {data}")  # Логирование полученных данных
    # Извлекаем ключевые данные из сообщения
    slug = data.get('slug', 'Неизвестен')
    gift_name = data.get('gift_name', 'Неизвестен')
    number = data.get('number', 'Неизвестен')
    image_preview = data.get('image_preview', None)

    # Форматируем и выводим сообщение
    formatted_message = f"Новый минт - *{slug}* - *{gift_name}* - *{number}*"
    print(formatted_message)  # Логирование форматированного сообщения

    # Если есть изображение, отправляем по URL
    if image_preview:
        try:
            # Отправляем изображение только тем пользователям, кто не выключил обновления
            for user_id, status in list(users_status.items()):
                if status['status'] == 'active':  # Отправляем только активным пользователям
                    chat_id = status['chat_id']
                    print(f"Отправка фото пользователю {chat_id}")  # Логирование chat_id
                    try:
                        await bot.send_photo(chat_id=chat_id, photo=image_preview, caption=formatted_message)
                    except TelegramForbiddenError:
                        print(f"Пользователь {chat_id} заблокировал бота или удалил чат с ботом")
                        del users_status[user_id]
        except Exception as e:
            print(f"Ошибка при отправке изображения: {e}")
    else:
        # Если изображения нет, отправляем только текст
        for user_id, status in list(users_status.items()):
            if status['status'] == 'active':  # Отправляем только активным пользователям
                chat_id = status['chat_id']
                print(f"Отправка сообщения пользователю {chat_id}")  # Логирование chat_id
                try:
                    await bot.send_message(chat_id=chat_id, text=formatted_message)
                except TelegramForbiddenError:
                    print(f"Пользователь {chat_id} заблокировал бота или удалил чат с ботом")
                    del users_status[user_id]

# Обработчик для команды /start
@dp.message(Command('start'))
async def start_command(message: types.Message):
    if has_access(message.from_user.id):
        # Сохраняем chat_id пользователя и устанавливаем статус 'active' (получает сообщения)
        users_status[message.from_user.id] = {'chat_id': message.chat.id, 'status': 'active'}
        await message.reply("""Hello! I’m a bot that helps you stay updated on new gift mints. You will now receive a notification about each new gift mint.

To pause notifications about mints, send the command - /stop

Subscribe to our news channel so you don’t miss the latest bot update - @GiftsMinter

Our channel with notifications about new gift releases - @TGGiftsNews""")
    else:
        await message.reply("You do not have access to this bot. Please purchase access from @BuyGiftsMinterBot.")

# Обработчик для команды /stop
@dp.message(Command('stop'))
async def stop_command(message: types.Message):
    if has_access(message.from_user.id):
        # Проверяем, подписан ли пользователь
        if message.from_user.id in users_status:
            # Устанавливаем статус 'inactive' (не получает сообщения)
            users_status[message.from_user.id]['status'] = 'inactive'
            await message.reply("""You will no longer receive notifications about new gift mints.

To resume receiving notifications, send the command /start""")
        else:
            await message.reply("You will no longer receive notifications about new gift mints")
    else:
        await message.reply("You do not have access to this bot. Please purchase access from @BuyGiftsMinterBot.")

# Обработчик для команды /addtgid
@dp.message(Command('addtgid'))
async def addtgid_command(message: types.Message):
    # Проверяем, является ли пользователь администратором (замените на свой ID)
    if message.from_user.id == 1267171169:  # Замените на ваш Telegram ID
        try:
            new_user_id = int(message.text.split()[1])
            allowed_users.add(new_user_id)
            # Получаем username нового пользователя
            new_user = await bot.get_chat(new_user_id)
            all_users[new_user_id] = new_user.username
            await message.reply(f"User with ID {new_user_id} has been granted access.")
        except (IndexError, ValueError):
            await message.reply("Please provide a valid Telegram user ID.")
        except Exception as e:
            await message.reply(f"An error occurred: {e}")
    else:
        await message.reply("You do not have permission to add users.")

# Обработчик для команды /seepeople
@dp.message(Command('seepeople'))
async def seepeople_command(message: types.Message):
    if all_users:
        users_list = "\n\n".join([f"{user_id} (@{username})" for user_id, username in all_users.items()])
        await message.reply(f"Users with access:\n\n{users_list}")
    else:
        await message.reply("No users have been granted access yet.")

# Обработчик для команды /newalert
@dp.message(Command('newalert'))
async def newalert_command(message: types.Message, state: FSMContext):
    # Проверяем, является ли пользователь администратором (замените на свой ID)
    if message.from_user.id == 1267171169:  # Замените на ваш Telegram ID
        await message.reply("Please send the message you want to broadcast.")
        await state.set_state(AlertStates.waiting_for_message)
    else:
        await message.reply("You do not have permission to send alerts.")

# Обработчик для получения сообщения для рассылки
@dp.message(AlertStates.waiting_for_message)
async def alert_message_received(message: types.Message, state: FSMContext):
    alert_message = message.text
    # Отправляем сообщение всем пользователям с доступом
    for user_id in allowed_users:
        chat_id = users_status.get(user_id, {}).get('chat_id')
        if chat_id:
            try:
                await bot.send_message(chat_id=chat_id, text=alert_message)
            except TelegramForbiddenError:
                print(f"Пользователь {chat_id} заблокировал бота или удалил чат с ботом")
    await state.clear()

# Обработчик для команды /newallalert
@dp.message(Command('newallalert'))
async def newallalert_command(message: types.Message, state: FSMContext):
    # Проверяем, является ли пользователь администратором (замените на свой ID)
    if message.from_user.id == 1267171169:  # Замените на ваш Telegram ID
        await message.reply("Please send the message you want to broadcast to all users.")
        await state.set_state(AllAlertStates.waiting_for_message)
    else:
        await message.reply("You do not have permission to send alerts to all users.")

# Обработчик для получения сообщения для рассылки всем пользователям
@dp.message(AllAlertStates.waiting_for_message)
async def allalert_message_received(message: types.Message, state: FSMContext):
    alert_message = message.text
    # Отправляем сообщение всем пользователям
    for user_id, status in list(users_status.items()):
        chat_id = status.get('chat_id')
        if chat_id:
            try:
                await bot.send_message(chat_id=chat_id, text=alert_message)
            except TelegramForbiddenError:
                print(f"Пользователь {chat_id} заблокировал бота или удалил чат с ботом")
    await state.clear()

# Обработчик для общего события
@sio.event
async def connect():
    print("Подключение установлено!")

# Обработчик для получения сообщений
@sio.event
async def message(data):
    print(f"Получено сообщение: {data}")  # Логирование полученного сообщения
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
                for user_id, status in list(users_status.items()):
                    if status['status'] == 'active':  # Отправляем только активным пользователям
                        chat_id = status['chat_id']
                        try:
                            await bot.send_photo(chat_id=chat_id, photo=image_preview, caption=formatted_message)
                        except TelegramForbiddenError:
                            print(f"Пользователь {chat_id} заблокировал бота или удалил чат с ботом")
                            del users_status[user_id]
            except Exception as e:
                print(f"Ошибка при отправке изображения: {e}")
        else:
            for user_id, status in list(users_status.items()):
                if status['status'] == 'active':
                    chat_id = status['chat_id']
                    try:
                        await bot.send_message(chat_id=chat_id, text=formatted_message)
                    except TelegramForbiddenError:
                        print(f"Пользователь {chat_id} заблокировал бота или удалил чат с ботом")
                        del users_status[user_id]

@sio.event
async def connect_error(data):
    print("Ошибка подключения:", data)

@sio.event
async def disconnect():
    print("Отключено от сервера")

async def connect_to_server():
    try:
        # Подключение к серверу
        await sio.connect('https://gsocket.trump.tg')
        print("Подключение успешно!")
    except Exception as e:
        print(f"Ошибка при подключении: {e}")

async def main():
    await connect_to_server()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())