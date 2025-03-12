import socketio
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from collections import deque
from datetime import datetime, timedelta

# Создаем клиент для подключения к серверу
sio = socketio.AsyncClient()

# Токен вашего бота Telegram
TELEGRAM_TOKEN = '8133398219:AAHm9q7rIaNf1ovb6TY4hdpMNuzWPPsumc4'

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

# Количество уведомлений для пробного плана
TRIAL_NOTIFICATIONS = 15

# Функция для проверки доступа
def has_access(user_id):
    return user_id in allowed_users or user_id in vip_users

# Функция для проверки VIP статуса
def is_vip(user_id):
    return user_id in vip_users

# Функция для проверки пробного плана
def is_trial(user_id):
    return user_id not in allowed_users and user_id not in vip_users

async def restore_notifications():
    while True:
        await asyncio.sleep(60)
        for user_id, last_reset_time in list(users_last_reset_time.items()):
            if not is_vip(user_id):
                if datetime.now() - last_reset_time >= timedelta(hours=24):
                    users_notifications_left[user_id] = INITIAL_NOTIFICATIONS if has_access(user_id) else TRIAL_NOTIFICATIONS
                    users_last_reset_time[user_id] = datetime.now()

async def deduct_notification(user_id):
    if not is_vip(user_id):
        if user_id not in users_notifications_left:
            users_notifications_left[user_id] = INITIAL_NOTIFICATIONS if has_access(user_id) else TRIAL_NOTIFICATIONS
        users_notifications_left[user_id] -= 1
        if users_notifications_left[user_id] <= 0:
            users_status[user_id]['status'] = 'inactive'
            chat_id = users_status[user_id]['chat_id']
            if is_trial(user_id):
                await bot.send_message(chat_id=chat_id, text="""Ваш пробный план исчерпан! Вам необходимо приобрести доступ к боту чтобы снова им пользоваться - @BuyGiftsMinterBot""")
            else:
                await bot.send_message(chat_id=chat_id, text="""⭐ Ваш запас уведомлений на сегодня исчерпан!

Возвращайтесь завтра, чтобы получить 1000 уведомлений, или же приобретите VIP статус чтобы получить доступ к безграничному использованию бота

Купить VIP - @BuyVIPMinterBot""")

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
    formatted_message = (f"[🎁]({button_url}) Новый минт - {slug} - {gift_name} - {number}\n\n"
                         f"Модель: {model}\n"
                         f"Фон: {backdrop}\n"
                         f"Символ: {symbol}\n\n"
                         f"🔗 Ссылка на подарок - {button_url}")
    
    print(formatted_message)  # Логирование форматированного сообщения

    async with queue_lock:
        message_queue.append((formatted_message, gift_name, image_preview))

async def send_message_to_users():
    while True:
        await asyncio.sleep(1)
        async with queue_lock:
            if message_queue:
                message, gift_name, image_url = message_queue.popleft()
                for user_id, status in list(users_status.items()):
                    if status['status'] == 'active' and (status.get('filter') is None or status.get('filter') == gift_name):
                        if not is_vip(user_id):
                            remaining_notifications = users_notifications_left.get(user_id, INITIAL_NOTIFICATIONS)
                            if remaining_notifications <= 0:
                                continue
                        chat_id = status['chat_id']
                        print(f"Отправка сообщения пользователю {chat_id}")  # Логирование chat_id
                        try:
                            if image_url:
                                await bot.send_photo(chat_id=chat_id, photo=image_url, caption=message, parse_mode='Markdown')
                            else:
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
        await bot.send_message(chat_id=chat_id, text=f"""❌ Фильтр уведомлений отключен. Включите уведомления еще раз в главном меню, или выберите нужный вам подарок через фильтры""")

# Обработчик для команды /start
@dp.message(Command('start'))
async def start_command(message: types.Message):
    if is_vip(message.from_user.id):
        start_message = """Gifts Minter готов к вашим услугам!

В VIP плане у вас открыт доступ к абсолютно всем функциям бота. Спасибо за оформление VIP статуса!"""
    elif has_access(message.from_user.id):
        start_message = """Gifts Minter готов к вашим услугам!

В базовом тарифе вам доступно получение уведомлений о новых минтах (до 1000 уведомлений в день)

Чтобы получить безлимитное получение уведомлений и доступ к поиску подарков по номеру - перейдите на VIP план за 75 звезд

Купить VIP статус - @BuyVIPMinterBot"""
    else:
        start_message = f"""Добро пожаловать в Gifts Minter!

На данный момент у вас включен пробный план, который дает доступ взглянуть на работу бота

У вас осталось {users_notifications_left.get(message.from_user.id, TRIAL_NOTIFICATIONS)} уведомлений, купите полный доступ к боту здесь - @BuyGiftsMinterBot"""

    notification_button_text = "❌ Отключить уведомления" if users_status.get(message.from_user.id, {}).get('status') == 'active' else "✅ Включить уведомления"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=notification_button_text, callback_data="toggle_notifications")],
        [InlineKeyboardButton(text="🔔 Фильтр уведомлений", callback_data="configure_notifications")],
        [InlineKeyboardButton(text="🔍 Искать подарки", callback_data="search_gifts")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"), InlineKeyboardButton(text="🧑‍💻 Поддержка", callback_data="support")]
    ])
    sent_message = await message.reply(start_message, reply_markup=keyboard)
    users_status[message.from_user.id] = {'chat_id': message.chat.id, 'status': users_status.get(message.from_user.id, {}).get('status', 'inactive'), 'message_id': sent_message.message_id}

# Обработчик для кнопки "Включить/Отключить уведомления"
@dp.callback_query(lambda c: c.data == 'toggle_notifications')
async def toggle_notifications_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if users_status.get(user_id, {}).get('status') == 'active':
        users_status[user_id]['status'] = 'inactive'
        await bot.send_message(chat_id=user_id, text="❌ Уведомления отключены\n\nЕсли захотите включить их повторно - вернитесь в Главное меню и запустите их")
    else:
        remaining_notifications = users_notifications_left.get(user_id, TRIAL_NOTIFICATIONS if is_trial(user_id) else INITIAL_NOTIFICATIONS)
        if remaining_notifications <= 0:
            await bot.send_message(chat_id=user_id, text="""Ваш пробный план исчерпан! Вам необходимо приобрести доступ к боту чтобы снова им пользоваться - @BuyGiftsMinterBot""")
        else:
            users_status[user_id]['status'] = 'active'
            await bot.send_message(chat_id=user_id, text="✅ Получение уведомлений о всех новых минтах включено на следующие 5 минут!")
            # Запускаем таймер на остановку уведомлений через 5 минут
            if user_id in stop_timers:
                stop_timers[user_id].cancel()
            stop_timers[user_id] = asyncio.create_task(stop_notifications(user_id))

    # Обновляем главное меню
    await update_main_menu(user_id, callback_query.message.message_id)

# Обработчик для кнопки "Настроить уведомления"
@dp.callback_query(lambda c: c.data == 'configure_notifications')
async def configure_notifications_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if has_access(user_id):
        if is_vip(user_id):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
            ])
            await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
            await bot.send_message(user_id, """🎁 *Все владельцы VIP плана могут присоединиться к частной группе*

В группе рассортированы топики, с каждым NFT подарком, и вы можете выбрать на какой будете получать уведомления, либо просто можете следить за определенными подарками

Напишите в ЛС нашему администратору, чтобы он выдал вам ссылку на данную группу, чтобы отправить сообщение администратору, просто нажмите на ссылку: https://t.me/m/k3V2OgINNDUy""", parse_mode='Markdown', reply_markup=keyboard)
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
            ])
            await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
            await bot.send_message(user_id, """Все владельцы VIP плана могут вступить в нашу частную группу с рассортированными топиками с NFT подарками

Купите VIP план здесь: @BuyVIPMinterBot""", reply_markup=keyboard)
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
        ])
        await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
        await bot.send_message(user_id, """Все владельцы VIP плана могут вступить в нашу частную группу с рассортированными топиками с NFT подарками

Купите VIP план здесь: @BuyVIPMinterBot""", reply_markup=keyboard)

# Обработчик для кнопки "Поддержка"
@dp.callback_query(lambda c: c.data == 'support')
async def support_callback(callback_query: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧑‍💻 Поддержка", url="https://t.me/asteroalex")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
    ])
    await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
    await bot.send_message(callback_query.from_user.id, """🧑‍💻 *Связь с поддержкой*

Если у вас возникли какие-то вопросы или проблемы в использовании бота - можете смело обращаться к @AsteroAlex""", parse_mode='Markdown', reply_markup=keyboard)

# Функция для создания команды для каждого gift_name
def create_gift_command(gift_name):
    @dp.message(Command(gift_name))
    async def gift_command(message: types.Message):
        if has_access(message.from_user.id):
            if not is_vip(message.from_user.id):
                await message.reply("Функция фильтрации уведомлений для минтов доступна только в VIP плане.\n\nКупите VIP план здесь: @BuyVIPMinterBot")
                return
            # Сохраняем chat_id пользователя и устанавливаем статус 'active' с фильтром gift_name
            users_status[message.from_user.id] = {'chat_id': message.chat.id, 'status': 'active', 'filter': gift_name}
            await message.reply(f"""✅ Фильтр уведомлений успешно включен для подарка {gift_name} на следующие 5 минут""")
            # Запускаем таймер на остановку уведомлений через 5 минут
            if message.from_user.id in stop_timers:
                stop_timers[message.from_user.id].cancel()
            stop_timers[message.from_user.id] = asyncio.create_task(stop_notifications(message.from_user.id))
        else:
            await message.reply("У вас нет доступа к этому боту. Пожалуйста, купите доступ у @BuyGiftsMinterBot.")

# Список всех gift_name и создание соответствующих команд
gift_names = [
    "SantaHat", "SignetRing", "PreciousPeach", "PlushPepe", "SpicedWine", "JellyBunny", "DurovsCap", "PerfumeBottle",
    "EternalRose", "BerryBox", "VintageCigar", "MagicPotion", "KissedFrog", "HexPot", "EvilEye", "SharpTongue",
    "TrappedHeart", "SkullFlower", "ScaredCat", "SpyAgaric", "HomemadeCake", "GenieLamp", "LunarSnake", "PartySparkler",
    "JesterHat", "WitchHat", "HangingStar", "LoveCandle", "CookieHeart", "DeskCalendar", "JingleBells", "SnowMittens",
    "VoodooDoll", "MadPumpkin", "HypnoLollipop", "BDayCandle", "BunnyMuffin", "AstralShard", "FlyingBroom", "CrystalBall",
    "EternalCandle", "SwissWatch", "GingerCookie", "MiniOscar", "LolPop", "IonGem", "StarNotepad", "LootBag", "LovePotion",
    "ToyBear", "DiamondRing", "TopHat", "SleighBell", "RecordPlayer", "SakuraFlower", "SnowGlobe", "WinterWreath",
    "TamaGadget", "CandyCane", "ElectricSkull", "NekoHelmet"
]

for gift_name in gift_names:
    create_gift_command(gift_name)

# Обработчик для кнопки "Искать подарки"
@dp.callback_query(lambda c: c.data == 'search_gifts')
async def search_gifts_callback(callback_query: types.CallbackQuery):
    await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
    await bot.send_message(chat_id=callback_query.from_user.id, text="""🔍 Функция поиска подарков находится в разработке

Данная функция будет доступна только владельцам со статусом VIP""", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
    ]))

async def update_main_menu(user_id, message_id):
    if is_vip(user_id):
        start_message = """Gifts Minter готов к вашим услугам!

В VIP плане у вас открыт доступ к абсолютно всем функциям бота. Спасибо за оформление VIP статуса!"""
    elif has_access(user_id):
        start_message = """Gifts Minter готов к вашим услугам!

В базовом тарифе вам доступно получение уведомлений о новых минтах (до 1000 уведомлений в день)

Чтобы получить безлимитное получение уведомлений и доступ к поиску подарков по номеру - перейдите на VIP план за 75 звезд

Купить VIP статус - @BuyVIPMinterBot"""
    else:
        start_message = f"""Добро пожаловать в Gifts Minter!

На данный момент у вас включен пробный план, который дает доступ взглянуть на работу бота

У вас осталось {users_notifications_left.get(user_id, TRIAL_NOTIFICATIONS)} уведомлений, купите полный доступ к боту здесь - @BuyGiftsMinterBot"""

    notification_button_text = "❌ Отключить уведомления" if users_status[user_id]['status'] == 'active' else "✅ Включить уведомления"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=notification_button_text, callback_data="toggle_notifications")],
        [InlineKeyboardButton(text="🔔 Фильтр уведомлений", callback_data="configure_notifications")],
        [InlineKeyboardButton(text="🔍 Искать подарки", callback_data="search_gifts")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"), InlineKeyboardButton(text="🧑‍💻 Поддержка", callback_data="support")]
    ])
    await bot.edit_message_text(chat_id=user_id, message_id=message_id, text=start_message, reply_markup=keyboard)

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
                # Сброс баланса уведомлений
                users_notifications_left[new_user_id] = INITIAL_NOTIFICATIONS
                users_last_reset_time[new_user_id] = datetime.now()
                # Получаем username нового пользователя
                new_user = await bot.get_chat(new_user_id)
                all_users[new_user_id] = new_user.username
                added_users.append(f"{new_user_id} (@{new_user.username})")
            await message.reply(f"Пользователям с ID {', '.join(added_users)} предоставлен доступ.")
        except (IndexError, ValueError):
            await message.reply("Пожалуйста, укажите корректные Telegram user ID.")
        except Exception as e:
            await message.reply(f"Произошла ошибка: {e}")
    else:
        await message.reply("У вас нет прав для добавления пользователей.")

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
                # Сброс баланса уведомлений
                users_notifications_left[new_vip_id] = float('inf')  # Бесконечное количество уведомлений
                # Получаем username нового пользователя
                new_vip_user = await bot.get_chat(new_vip_id)
                all_vip_users[new_vip_id] = new_vip_user.username
                added_vips.append(f"{new_vip_id} (@{new_vip_user.username})")
            await message.reply(f"Пользователям с ID {', '.join(added_vips)} предоставлен VIP статус.")
        except (IndexError, ValueError):
            await message.reply("Пожалуйста, укажите корректные Telegram user ID.")
        except Exception as e:
            await message.reply(f"Произошла ошибка: {e}")
    else:
        await message.reply("У вас нет прав для добавления VIP пользователей.")

# Обработчик для команды /seepeople
@dp.message(Command('seepeople'))
async def seepeople_command(message: types.Message):
    if all_users:
        users_list = "\n\n".join([f"{user_id} (@{username})" for user_id, username in all_users.items()])
        await message.reply(f"Пользователи с доступом:\n\n{users_list}")
    else:
        await message.reply("Пока что никому не предоставлен доступ.")

# Обработчик для команды /seevips
@dp.message(Command('seevips'))
async def seevips_command(message: types.Message):
    # Проверяем, является ли пользователь администратором (замените на свои ID)
    if message.from_user.id in [1267171169, 6695944947]:
        if all_vip_users:
            vip_list = "\n\n".join([f"{user_id} (@{username})" for user_id, username in all_vip_users.items()])
            await message.reply(f"VIP пользователи:\n\n{vip_list}")
        else:
            await message.reply("Пока что никому не предоставлен VIP статус.")
    else:
        await message.reply("У вас нет прав для просмотра VIP пользователей.")

@dp.callback_query(lambda c: c.data == 'referral_system')
async def referral_system_callback(callback_query: types.CallbackQuery):
    referral_text = """🔗 Реферальная система

Пригласите ваших друзей приобрести базовый тариф или VIP статус и получите до 25% за их покупку!

Перейдите на профиль бота @BuyGiftsMinterBot или @BuyVIPMinterBot и выберите "Партнерская программа"."""

    referral_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад 🔙", callback_data="back_to_start")]
    ])
    # Удаляем предыдущее сообщение бота
    await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
    await bot.send_message(callback_query.from_user.id, referral_text, reply_markup=referral_keyboard)

@dp.callback_query(lambda c: c.data == 'profile')
async def profile_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    user = await bot.get_chat(user_id)
    if is_vip(user_id):
        status = "VIP"
        notifications_info = "У вас безлимитное количество уведомлений"
    elif has_access(user_id):
        status = "Базовый"
        notifications_info = f"Осталось уведомлений: {users_notifications_left.get(user_id, INITIAL_NOTIFICATIONS)}"
    else:
        status = "Пробный план"
        notifications_info = f"Осталось уведомлений: {users_notifications_left.get(user_id, TRIAL_NOTIFICATIONS)}"

    username = f"@{user.username}" if user.username else "отсутствует"
    profile_text = f"""👤 Профиль

Имя: {user.full_name}
Имя пользователя: {username}
Telegram ID: {user_id}
Статус: {status}
{notifications_info}"""

    profile_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад 🔙", callback_data="back_to_start")]
    ])
    # Удаляем предыдущее сообщение бота
    await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
    await bot.send_message(callback_query.from_user.id, profile_text, reply_markup=profile_keyboard)

@dp.callback_query(lambda c: c.data == 'back_to_start')
async def back_to_start_callback(callback_query: types.CallbackQuery):
    await update_main_menu(callback_query.from_user.id, callback_query.message.message_id)

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
            f"[🎁]({button_url}) Новый минт - {gift_name} - #{number}\n\n"
            f"Модель: {model}\n"
            f"Фон: {backdrop}\n"
            f"Символ: {symbol}\n\n"
            f"🔗 Ссылка на подарок - {button_url}"
        )

        async with queue_lock:
            message_queue.append((formatted_message, gift_name, image_preview))

# Команда для перезапуска подключения к серверу Socket.IO
@dp.message(Command('updateserver'))
async def updateserver_command(message: types.Message):
    # Проверяем, является ли пользователь администратором (замените на свой ID)
    if message.from_user.id == 1267171169:  # Замените на ваш Telegram ID
        await disconnect_from_server()
        await connect_to_server()
        await message.reply("Подключение к серверу обновлено.")
    else:
        await message.reply("У вас нет прав для выполнения этой команды.")

# Команда для отключения от сервера Socket.IO
@dp.message(Command('downserver'))
async def downserver_command(message: types.Message):
    # Проверяем, является ли пользователь администратором (замените на свой ID)
    if message.from_user.id == 1267171169:  # Замените на ваш Telegram ID
        await disconnect_from_server()
        await message.reply("Отключено от сервера.")
    else:
        await message.reply("У вас нет прав для выполнения этой команды.")

@sio.event
async def connect_error(data):
    print("Ошибка подключения:", data)

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