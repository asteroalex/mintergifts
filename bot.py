import socketio
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramAPIError
from collections import deque
from datetime import datetime, timedelta

# Создаем клиент для подключения к серверу
sio = socketio.AsyncClient()

# Токен вашего бота Telegram
TELEGRAM_TOKEN = '8044348316:AAFLsqU_IVvxZqCqfciNyGH5_48k4rLfKwg'

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

# Список VIP пользователей
vip_users = set()

# Список всех VIP пользователей с доступом (ID и имя пользователя)
all_vip_users = {}

# Очередь для сообщений и замок для управления доступом к очереди
message_queue = deque()
queue_lock = asyncio.Lock()

# Таймеры для остановки уведомлений
stop_timers = {}

# Словарь для отслеживания количества уведомлений
users_notifications_left = {}
users_last_reset_time = {}

# Изначальное количество уведомлений
INITIAL_NOTIFICATIONS = 1000

# Состояния для FSM (Finite State Machine)
class AllAlertStates(StatesGroup):
    waiting_for_message = State()

# Функция для проверки доступа
def has_access(user_id):
    return user_id in allowed_users

# Функция для проверки VIP статуса
def is_vip(user_id):
    return user_id in vip_users

async def restore_notifications():
    while True:
        await asyncio.sleep(60)
        for user_id, last_reset_time in list(users_last_reset_time.items()):
            if not is_vip(user_id):
                if datetime.now() - last_reset_time >= timedelta(hours=24):
                    users_notifications_left[user_id] = INITIAL_NOTIFICATIONS
                    users_last_reset_time[user_id] = datetime.now()

async def deduct_notification(user_id):
    if not is_vip(user_id):
        users_notifications_left[user_id] -= 1
        if users_notifications_left[user_id] <= 0:
            users_status[user_id]['status'] = 'inactive'
            chat_id = users_status[user_id]['chat_id']
            await bot.send_message(chat_id=chat_id, text="""You have exhausted your notifications for today. Please try again later.""")

# Функция для обработки события 'newMint'
@sio.event
async def newMint(data):
    print(f"Получены данные о новом минте: {data}")  # Логирование полученных данных
    # Извлекаем ключевые данные из сообщения
    slug = data.get('slug', 'Неизвестен')
    gift_name = data.get('gift_name', 'Неизвестен')
    number = data.get('number', 'Неизвестен')
    image_preview = data.get('image_preview', None)
    model = data.get('Model', 'Неизвестен')
    backdrop = data.get('backdrop', 'Неизвестен')
    symbol = data.get('Symbol', 'Неизвестен')

    # Форматируем и выводим сообщение
    button_url = f"https://t.me/nft/{slug}-{number}"
    formatted_message = (f"[🎁]({button_url}) New mint - *{slug}* - *{gift_name}* - *{number}*\n\n"
                         f"Model: {model}\n"
                         f"Backdrop: {backdrop}\n"
                         f"Symbol: {symbol}")
    
    print(formatted_message)  # Логирование форматированного сообщения

    async with queue_lock:
        message_queue.append((formatted_message, gift_name))

async def send_message_to_users():
    while True:
        await asyncio.sleep(1)
        async with queue_lock:
            if message_queue:
                message, gift_name = message_queue.popleft()
                for user_id, status in list(users_status.items()):
                    if status['status'] == 'active' and (status.get('filter') is None or status.get('filter') == gift_name):
                        if not is_vip(user_id):
                            remaining_notifications = users_notifications_left.get(user_id, INITIAL_NOTIFICATIONS)
                            if remaining_notifications <= 0:
                                continue
                        chat_id = status['chat_id']
                        print(f"Отправка сообщения пользователю {chat_id}")  # Логирование chat_id
                        try:
                            await bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
                            await deduct_notification(user_id)
                        except TelegramRetryAfter as e:
                            print(f"Ошибка при отправке сообщения: {e}")
                            await asyncio.sleep(e.retry_after)
                        except TelegramForbiddenError:
                            print(f"Пользователь {chat_id} заблокировал бота или удалил чат с ботом")
                            del users_status[user_id]
                        except Exception as e:
                            print(f"Ошибка при отправке сообщения: {e}")

# Функция для остановки уведомлений через 5 минут
async def stop_notifications(user_id):
    await asyncio.sleep(300)  # Ждем 5 минут
    if user_id in users_status and users_status[user_id]['status'] == 'active':
        users_status[user_id]['status'] = 'inactive'
        chat_id = users_status[user_id]['chat_id']
        await bot.send_message(chat_id=chat_id, text="""Notification of new mints has been stopped.

Send the /start command to receive notifications again for the next 5 minutes.""")

# Обработчик для команды /start
@dp.message(Command('start'))
async def start_command(message: types.Message):
    if has_access(message.from_user.id):
        # Сохраняем chat_id пользователя и устанавливаем статус 'active' (получает сообщения)
        users_status[message.from_user.id] = {'chat_id': message.chat.id, 'status': 'active'}
        remaining_notifications = users_notifications_left.get(message.from_user.id, INITIAL_NOTIFICATIONS)
        if is_vip(message.from_user.id):
            remaining_notifications_text = "You have unlimited notifications, thank you for purchasing VIP status."
        else:
            remaining_notifications_text = f"Your remaining notifications for mints today: {remaining_notifications}\n\nNotifications will be restored after 24 hours."
        await message.reply(f"""Receiving notifications of new mints is enabled for the next 5 minutes.

{remaining_notifications_text}

Subscribe to our news channel @TGGiftsNews to receive notifications of new gifts.

Bot news channel: @GiftsMinter""")
        # Запускаем таймер на остановку уведомлений через 5 минут
        if message.from_user.id in stop_timers:
            stop_timers[message.from_user.id].cancel()
        stop_timers[message.from_user.id] = asyncio.create_task(stop_notifications(message.from_user.id))
        # Инициализируем счетчик уведомлений
        if message.from_user.id not in users_notifications_left:
            users_notifications_left[message.from_user.id] = INITIAL_NOTIFICATIONS
        if message.from_user.id not in users_last_reset_time:
            users_last_reset_time[message.from_user.id] = datetime.now()
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
            if message.from_user.id in stop_timers:
                stop_timers[message.from_user.id].cancel()
                del stop_timers[message.from_user.id]
        else:
            await message.reply("You will no longer receive notifications about new gift mints")
    else:
        await message.reply("You do not have access to this bot. Please purchase access from @BuyGiftsMinterBot.")

# Функция для создания команды для каждого gift_name
def create_gift_command(gift_name):
    @dp.message(Command(gift_name))
    async def gift_command(message: types.Message):
        if has_access(message.from_user.id):
            if not is_vip(message.from_user.id):
                await message.reply("The notification filtering feature for mints is only available in the VIP plan.\n\nPurchase the VIP plan here: @BuyVIPMinterBot")
                return
            # Сохраняем chat_id пользователя и устанавливаем статус 'active' с фильтром gift_name
            users_status[message.from_user.id] = {'chat_id': message.chat.id, 'status': 'active', 'filter': gift_name}
            await message.reply(f"""Receiving notifications of new mints with gift name '{gift_name}' is enabled for the next 5 minutes.

Subscribe to our news channel @TGGiftsNews to receive notifications of new gifts.

Bot news channel: @GiftsMinter""")
            # Запускаем таймер на остановку уведомлений через 5 минут
            if message.from_user.id in stop_timers:
                stop_timers[message.from_user.id].cancel()
            stop_timers[message.from_user.id] = asyncio.create_task(stop_notifications(message.from_user.id))
        else:
            await message.reply("You do not have access to this bot. Please purchase access from @BuyGiftsMinterBot.")

# Список всех gift_name и создание соответствующих команд
gift_names = [
    "SantaHat", "SignetRing", "PreciousPeach", "PlushPepe", "SpicedWine", "JellyBunny", "DurovsCap", "PerfumeBottle",
    "EternalRose", "BerryBox", "VintageCigar", "MagicPotion", "KissedFrog", "HexPot", "EvilEye", "SharpTongue",
    "TrappedHeart", "SkullFlower", "ScaredCat", "SpyAgaric", "HomemadeCake", "GenieLamp", "LunarSnake", "PartySparkler",
    "JesterHat", "WitchHat", "HangingStar", "LoveCandle", "CookieHeart", "DeskCalendar", "JingleBells", "SnowMittens",
    "VoodooDoll", "MadPumpkin", "HypnoLollipop", "BDayCandle", "BunnyMuffin", "AstralShard", "FlyingBroom", "CrystalBall",
    "EternalCandle", "SwissWatch", "GingerCookie", "MiniOscar", "LolPop", "IonGem", "StarNotepad", "LootBag", "LovePotion",
    "ToyBear", "DiamondRing"
]

for gift_name in gift_names:
    create_gift_command(gift_name)

# Обработчик для команды /addtgid
@dp.message(Command('addtgid'))
async def addtgid_command(message: types.Message):
    # Проверяем, является ли пользователь администратором (замените на свой ID)
    if message.from_user.id == 1267171169:  # Замените на ваш Telegram ID
        try:
            user_ids = message.text.split()[1:]
            added_users = []
            for user_id in user_ids:
                new_user_id = int(user_id)
                allowed_users.add(new_user_id)
                # Получаем username нового пользователя
                new_user = await bot.get_chat(new_user_id)
                all_users[new_user_id] = new_user.username
                added_users.append(f"{new_user_id} (@{new_user.username})")
            await message.reply(f"Users with IDs {', '.join(added_users)} have been granted access.")
        except (IndexError, ValueError):
            await message.reply("Please provide valid Telegram user IDs.")
        except Exception as e:
            await message.reply(f"An error occurred: {e}")
    else:
        await message.reply("You do not have permission to add users.")

# Обработчик для команды /addvip
@dp.message(Command('addvip'))
async def addvip_command(message: types.Message):
    # Проверяем, является ли пользователь администратором (замените на свой ID)
    if message.from_user.id == 1267171169:  # Замените на ваш Telegram ID
        try:
            user_ids = message.text.split()[1:]
            added_vips = []
            for user_id in user_ids:
                new_vip_id = int(user_id)
                vip_users.add(new_vip_id)
                # Получаем username нового пользователя
                new_vip_user = await bot.get_chat(new_vip_id)
                all_vip_users[new_vip_id] = new_vip_user.username
                added_vips.append(f"{new_vip_id} (@{new_vip_user.username})")
            await message.reply(f"Users with IDs {', '.join(added_vips)} have been granted VIP status.")
        except (IndexError, ValueError):
            await message.reply("Please provide valid Telegram user IDs.")
        except Exception as e:
            await message.reply(f"An error occurred: {e}")
    else:
        await message.reply("You do not have permission to add VIP users.")

# Обработчик для команды /seepeople
@dp.message(Command('seepeople'))
async def seepeople_command(message: types.Message):
    if all_users:
        users_list = "\n\n".join([f"{user_id} (@{username})" for user_id, username in all_users.items()])
        await message.reply(f"Users with access:\n\n{users_list}")
    else:
        await message.reply("No users have been granted access yet.")

# Обработчик для команды /seevips
@dp.message(Command('seevips'))
async def seevips_command(message: types.Message):
    # Проверяем, является ли пользователь администратором (замените на свои ID)
    if message.from_user.id in [1267171169, 6695944947]:
        if all_vip_users:
            vip_list = "\n\n".join([f"{user_id} (@{username})" for user_id, username in all_vip_users.items()])
            await message.reply(f"VIP users:\n\n{vip_list}")
        else:
            await message.reply("No VIP users have been granted access yet.")
    else:
        await message.reply("You do not have permission to see VIP users.")

# Обработчик для команды /updateserver
@dp.message(Command('updateserver'))
async def updateserver_command(message: types.Message):
    # Проверяем, является ли пользователь администратором (замените на свои ID)
    if message.from_user.id in [1267171169, 6695944947]:
        print("Попытка переподключения к серверу по запросу администратора...")
        await message.reply("Попытка переподключения к серверу...")
        await reconnect_to_server()
        await message.reply("Переподключение выполнено.")
    else:
        await message.reply("You do not have permission to update the server connection.")

# Обработчик для команды /downserver
@dp.message(Command('downserver'))
async def downserver_command(message: types.Message):
    # Проверяем, является ли пользователь администратором (замените на свои ID)
    if message.from_user.id in [1267171169, 6695944947]:
        print("Попытка отключения от сервера по запросу администратора...")
        await message.reply("Попытка отключения от сервера...")
        await disconnect_from_server()
        await message.reply("Отключение выполнено.")
    else:
        await message.reply("You do not have permission to disconnect the server.")

# Обработчик для команды /filters
@dp.message(Command('filters'))
async def filters_command(message: types.Message):
    await message.reply("""All the list of commands for filtering notifications can be read here: https://telegra.ph/All-filters-for-Gifts-Minter-02-16""", disable_web_page_preview=True)

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
        model = data.get('Model', 'Неизвестен')
        backdrop = data.get('backdrop', 'Неизвестен')
        symbol = data.get('Symbol', 'Неизвестен')
        image_preview = data.get('image_preview', None)
        button_url = f"https://t.me/nft/{gift_name}-{number}"
        formatted_message = (
            f"[🎁]({button_url}) New mint - {gift_name} - #{number}\n\n"
            f"Model: {model}\n"
            f"Backdrop: {backdrop}\n"
            f"Symbol: {symbol}"
        )

        async with queue_lock:
            message_queue.append((formatted_message, gift_name))

@sio.event
async def connect_error(data):
    print("Ошибка подключения:", data)

@sio.event
async def disconnect():
    print("Отключено от сервера")
    await reconnect_to_server()

async def reconnect_to_server():
    while not sio.connected:
        print("Попытка переподключения через 30 секунд...")
        await asyncio.sleep(30)
        try:
            await sio.connect('https://gsocket.trump.tg')
            print("Подключение успешно!")
        except Exception as e:
            print(f"Ошибка при переподключении: {e}")

async def disconnect_from_server():
    if sio.connected:
        await sio.disconnect()
        print("Отключение от сервера выполнено.")

async def connect_to_server():
    try:
        # Подключение к серверу
        await sio.connect('https://gsocket.trump.tg')
        print("Подключение успешно!")
    except Exception as e:
        print(f"Ошибка при подключении: {e}")

async def main():
    await connect_to_server()
    asyncio.create_task(send_message_to_users())
    asyncio.create_task(restore_notifications())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())