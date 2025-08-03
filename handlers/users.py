from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.database import async_session
from database.models import User, Event, EventRegistration
from keyboards.keyboards import (
    get_main_menu, get_cities_keyboard, get_events_keyboard,
    get_event_actions_keyboard, build_events_list_keyboard,
    get_back_keyboard, get_next_event_keyboard,
    get_no_events_keyboard
)
from datetime import datetime
import os

router = Router()

class ProfileStates(StatesGroup):
    """Состояния для редактирования профиля"""
    waiting_for_name = State()

async def get_or_create_user(telegram_id: int, username: str = None, first_name: str = None, last_name: str = None):
    """Получить или создать пользователя"""
    async with async_session() as session:
        # Проверяем, есть ли пользователь в БД
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        
        if not user:
            # Проверяем, является ли пользователь первым админом
            admin_id = os.getenv('ADMIN_ID')
            role = 'admin' if admin_id and str(telegram_id) == admin_id else 'user'
            
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                role=role
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        else:
            # Обновляем информацию о пользователе при каждом обращении
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            await session.commit()
        
        return user

async def safe_edit_message(callback: CallbackQuery, text: str, reply_markup=None, parse_mode="HTML"):
    """Безопасное редактирование сообщения с fallback на удаление и отправку нового"""
    try:
        await callback.message.edit_text(
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        
        await callback.message.answer(
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )

async def get_next_event_for_user(user_id: int, city: str = None):
    """Получить ближайшее мероприятие для пользователя"""
    async with async_session() as session:
        query = select(Event).where(
            Event.is_visible == True,
            Event.date_time > datetime.now()
        )
        
        # Если у пользователя указан город, сначала ищем в его городе
        if city:
            city_query = query.where(Event.city == city).order_by(Event.date_time).limit(1)
            result = await session.execute(city_query)
            event = result.scalar_one_or_none()
            
            if event:
                return event
        
        # Если в городе нет мероприятий или город не указан, берем любое ближайшее
        all_query = query.order_by(Event.date_time).limit(1)
        result = await session.execute(all_query)
        return result.scalar_one_or_none()

async def format_next_event_message(event, user_city: str = None, participants_count: int = 0):
    """Форматирование сообщения с ближайшим мероприятием"""
    if not event:
        return (
            "🎉 <b>Добро пожаловать!</b>\n\n"
            "😔 Пока нет запланированных мероприятий, но они скоро появятся!\n\n"
            "Выберите город, чтобы получать уведомления о новых мероприятиях:"
        )
    
    # Определяем, в городе пользователя это мероприятие или нет
    city_indicator = ""
    if user_city and event.city != user_city:
        city_indicator = f" (в другом городе)"
    elif user_city and event.city == user_city:
        city_indicator = f" 🎯"
    
    # Считаем время до мероприятия
    time_until = event.date_time - datetime.now()
    
    if time_until.days > 0:
        time_text = f"через {time_until.days} дн."
    elif time_until.seconds > 3600:
        hours = time_until.seconds // 3600
        time_text = f"через {hours} ч."
    else:
        minutes = time_until.seconds // 60
        time_text = f"через {minutes} мин."
    
    message = f"🎉 <b>Ближайшее мероприятие{city_indicator}</b>\n\n"
    message += f"📅 <b>{event.title}</b>\n"
    message += f"🏙️ <b>Город:</b> {event.city}\n"
    message += f"🕐 <b>Дата:</b> {event.date_time.strftime('%d.%m.%Y в %H:%M')} ({time_text})\n"
    
    if event.location:
        message += f"📍 <b>Место:</b> {event.location}\n"
    
    if event.max_participants:
        percentage = (participants_count / event.max_participants) * 100
        message += f"👥 <b>Участники:</b> {participants_count}/{event.max_participants} ({percentage:.0f}%)\n"
    else:
        message += f"👥 <b>Участники:</b> {participants_count}\n"
    
    if event.description and len(event.description) <= 100:
        message += f"\n📝 {event.description}\n"
    elif event.description:
        message += f"\n📝 {event.description[:97]}...\n"
    
    return message

async def show_next_event_welcome(message_or_callback, user, is_callback=False):
    """Показать приветствие с ближайшим мероприятием"""
    # Получаем ближайшее мероприятие
    next_event = await get_next_event_for_user(user.telegram_id, user.city)
    
    # Считаем участников если мероприятие есть
    participants_count = 0
    if next_event:
        async with async_session() as session:
            participants_result = await session.execute(
                select(EventRegistration).where(EventRegistration.event_id == next_event.id)
            )
            participants_count = len(participants_result.scalars().all())
    
    # Формируем сообщение
    welcome_text = f"Добро пожаловать, {user.first_name}! 👋\n\n"
    
    if user.role == 'admin':
        welcome_text += "🔱 Вы администратор бота\n\n"
    elif user.role == 'moderator':
        welcome_text += "🛡 Вы модератор бота\n\n"
    
    event_message = await format_next_event_message(next_event, user.city, participants_count)
    full_message = welcome_text + event_message
    
    # Клавиатура
    if next_event:
        keyboard = get_next_event_keyboard(next_event.id, True)
    else:
        keyboard = get_no_events_keyboard()
    
    # Отправляем сообщение
    if is_callback:
        await safe_edit_message(
            message_or_callback,
            full_message,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        # Если есть фото/видео у мероприятия, отправляем с медиа
        if next_event and next_event.photo_file_id:
            await message_or_callback.answer_photo(
                photo=next_event.photo_file_id,
                caption=full_message,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        elif next_event and next_event.video_file_id:
            await message_or_callback.answer_video(
                video=next_event.video_file_id,
                caption=full_message,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        else:
            await message_or_callback.answer(
                full_message,
                parse_mode="HTML",
                reply_markup=keyboard
            )

@router.message(Command("start"))
async def start_command(message: Message):
    """Команда /start - показ ближайшего мероприятия"""
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )
    
    await show_next_event_welcome(message, user, is_callback=False)

@router.message(F.text == "🏙️ Выбрать город")
async def select_city(message: Message):
    """Выбор города"""
    await message.answer(
        "Выберите ваш город:",
        reply_markup=get_cities_keyboard()
    )

@router.callback_query(F.data.startswith("city_"))
async def handle_city_selection(callback: CallbackQuery):
    """Обработка выбора города"""
    city_code = callback.data.split("_")[1]
    city_name = "Москва" if city_code == "moscow" else "Казань"
    
    # Обновляем город пользователя в БД
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        
        if user:
            user.city = city_name
            await session.commit()
    
    # Возвращаемся к приветствию с обновленным городом
    await show_next_event_welcome(callback, user, is_callback=True)
    await callback.answer(f"Ваш город: {city_name} ✅")

@router.message(F.text == "📅 Мероприятия")
async def show_events_menu(message: Message):
    """Показать меню мероприятий"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
        
        user_city = user.city if user else None
    
    await message.answer(
        "Выберите категорию мероприятий:",
        reply_markup=get_events_keyboard(user_city)
    )

@router.callback_query(F.data == "all_events")
async def show_all_events(callback: CallbackQuery):
    """Показать все мероприятия"""
    async with async_session() as session:
        result = await session.execute(
            select(Event)
            .where(Event.is_visible == True, Event.date_time > datetime.now())
            .order_by(Event.date_time)
        )
        events = result.scalars().all()
    
    if not events:
        await safe_edit_message(
            callback,
            "Пока нет запланированных мероприятий 😔",
            reply_markup=get_events_keyboard()
        )
        return
    
    await safe_edit_message(
        callback,
        "Выберите мероприятие:",
        reply_markup=build_events_list_keyboard(events)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("events_city_"))
async def show_city_events(callback: CallbackQuery):
    """Показать мероприятия по городу"""
    city_parts = callback.data.split("_")[2:]  # Получаем все части после "events_city_"
    city = "_".join(city_parts).lower()  # Соединяем обратно, если в названии города есть пробелы
    
    # Определяем название города
    if city == "москва":
        city_name = "Москва"
    elif city == "казань":
        city_name = "Казань"
    else:
        # Fallback для старого формата
        city_name = "Москва" if city == "moscow" else "Казань"
    
    async with async_session() as session:
        result = await session.execute(
            select(Event)
            .where(
                Event.is_visible == True,
                Event.city == city_name,
                Event.date_time > datetime.now()
            )
            .order_by(Event.date_time)
        )
        events = result.scalars().all()
    
    if not events:
        await safe_edit_message(
            callback,
            f"В городе {city_name} пока нет запланированных мероприятий 😔",
            reply_markup=get_events_keyboard(city_name)
        )
        return
    
    await safe_edit_message(
        callback,
        f"Мероприятия в городе {city_name}:",
        reply_markup=build_events_list_keyboard(events)
    )
    await callback.answer()

@router.callback_query(F.data == "my_events")
async def show_my_events(callback: CallbackQuery):
    """Показать мои мероприятия (на которые зарегистрирован)"""
    async with async_session() as session:
        result = await session.execute(
            select(Event)
            .join(EventRegistration)
            .join(User)
            .where(
                User.telegram_id == callback.from_user.id,
                Event.date_time > datetime.now()
            )
            .order_by(Event.date_time)
        )
        events = result.scalars().all()
    
    if not events:
        await safe_edit_message(
            callback,
            "Вы пока не записаны ни на одно мероприятие 😔",
            reply_markup=get_events_keyboard()
        )
        return
    
    await safe_edit_message(
        callback,
        "Ваши мероприятия:",
        reply_markup=build_events_list_keyboard(events)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("event_"))
async def show_event_details(callback: CallbackQuery):
    """Показать детали мероприятия"""
    event_id = int(callback.data.split("_")[1])
    
    async with async_session() as session:
        # Получаем мероприятие
        result = await session.execute(select(Event).where(Event.id == event_id))
        event = result.scalar_one_or_none()
        
        if not event:
            await callback.answer("Мероприятие не найдено", show_alert=True)
            return
        
        # Проверяем, зарегистрирован ли пользователь
        reg_result = await session.execute(
            select(EventRegistration)
            .join(User)
            .where(
                User.telegram_id == callback.from_user.id,
                EventRegistration.event_id == event_id
            )
        )
        is_registered = reg_result.scalar_one_or_none() is not None
        
        # Получаем пользователя и проверяем роль
        user_result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user_result.scalar_one_or_none()
        
        # Проверяем, является ли пользователь создателем или имеет права администратора
        is_creator = user and user.id == event.creator_id
        is_admin_or_moderator = user and user.role in ['admin', 'moderator']
        
        # Считаем количество участников
        participants_result = await session.execute(
            select(EventRegistration).where(EventRegistration.event_id == event_id)
        )
        participants_count = len(participants_result.scalars().all())
    
    # Формируем текст
    event_text = f"📅 <b>{event.title}</b>\n\n"
    event_text += f"📝 <b>Описание:</b> {event.description or 'Не указано'}\n"
    event_text += f"📍 <b>Место:</b> {event.location or 'Не указано'}\n"
    event_text += f"🏙️ <b>Город:</b> {event.city}\n"
    event_text += f"🕐 <b>Дата и время:</b> {event.date_time.strftime('%d.%m.%Y в %H:%M')}\n"
    
    if event.max_participants:
        event_text += f"👥 <b>Участники:</b> {participants_count}/{event.max_participants}\n"
    else:
        event_text += f"👥 <b>Участники:</b> {participants_count}\n"
    
    if event.registration_required:
        if event.registration_open:
            event_text += "✅ <b>Регистрация открыта</b>\n"
        else:
            event_text += "❌ <b>Регистрация закрыта</b>\n"
    else:
        event_text += "🆓 <b>Регистрация не требуется</b>\n"
    
    # Отправляем с медиа если есть
    keyboard = get_event_actions_keyboard(event_id, is_registered, is_creator or is_admin_or_moderator)
    
    try:
        if event.photo_file_id:
            await callback.message.answer_photo(
                photo=event.photo_file_id,
                caption=event_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            await callback.message.delete()
        elif event.video_file_id:
            await callback.message.answer_video(
                video=event.video_file_id,
                caption=event_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            await callback.message.delete()
        else:
            await safe_edit_message(
                callback,
                event_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
    except Exception as e:
        # Если не удалось отправить медиа, отправляем текст
        await safe_edit_message(
            callback,
            event_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("register_"))
async def register_for_event(callback: CallbackQuery):
    """Записаться на мероприятие"""
    event_id = int(callback.data.split("_")[1])
    
    async with async_session() as session:
        # Получаем пользователя
        user_result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user_result.scalar_one_or_none()
        
        # Получаем мероприятие
        event_result = await session.execute(select(Event).where(Event.id == event_id))
        event = event_result.scalar_one_or_none()
        
        if not event or not user:
            await callback.answer("Ошибка при регистрации", show_alert=True)
            return
        
        # Проверяем, открыта ли регистрация
        if not event.registration_open:
            await callback.answer("Регистрация на это мероприятие закрыта", show_alert=True)
            return
        
        # Проверяем, не прошло ли мероприятие
        if event.date_time <= datetime.now():
            await callback.answer("Мероприятие уже прошло", show_alert=True)
            return
        
        # Проверяем, не зарегистрирован ли уже
        existing_reg = await session.execute(
            select(EventRegistration).where(
                EventRegistration.user_id == user.id,
                EventRegistration.event_id == event_id
            )
        )
        
        if existing_reg.scalar_one_or_none():
            await callback.answer("Вы уже зарегистрированы на это мероприятие", show_alert=True)
            return
        
        # Проверяем лимит участников
        if event.max_participants:
            current_count = await session.execute(
                select(EventRegistration).where(EventRegistration.event_id == event_id)
            )
            if len(current_count.scalars().all()) >= event.max_participants:
                await callback.answer("Достигнут лимит участников", show_alert=True)
                return
        
        # Создаем регистрацию
        registration = EventRegistration(user_id=user.id, event_id=event_id)
        session.add(registration)
        await session.commit()
    
    await callback.answer("Вы успешно записались на мероприятие! ✅")
    # Обновляем информацию о мероприятии
    await show_event_details(callback)

@router.callback_query(F.data.startswith("unregister_"))
async def unregister_from_event(callback: CallbackQuery):
    """Отписаться от мероприятия"""
    event_id = int(callback.data.split("_")[1])
    
    async with async_session() as session:
        # Получаем пользователя
        user_result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user_result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Находим и удаляем регистрацию
        reg_result = await session.execute(
            select(EventRegistration).where(
                EventRegistration.user_id == user.id,
                EventRegistration.event_id == event_id
            )
        )
        registration = reg_result.scalar_one_or_none()
        
        if not registration:
            await callback.answer("Вы не зарегистрированы на это мероприятие", show_alert=True)
            return
        
        await session.delete(registration)
        await session.commit()
    
    await callback.answer("Вы успешно отписались от мероприятия")
    # Обновляем информацию о мероприятии
    await show_event_details(callback)

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    """Возврат в главное меню"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        role = user.role if user else 'user'
    
    try:
        await callback.message.delete()
    except:
        pass
    
    await callback.message.answer(
        "Главное меню:",
        reply_markup=get_main_menu(role)
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_events")
async def back_to_events(callback: CallbackQuery):
    """Возврат к меню мероприятий"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        user_city = user.city if user else None
    
    await safe_edit_message(
        callback,
        "Выберите категорию мероприятий:",
        reply_markup=get_events_keyboard(user_city)
    )
    await callback.answer()

@router.message(F.text == "💰 Донат")
async def donate_handler(message: Message):
    """Обработка доната (заглушка)"""
    await message.answer(
        "💰 Функция доната будет реализована позже.\n\n"
        "Спасибо за желание поддержать наш проект! ❤️"
    )

@router.message(F.text == "👤 Профиль")
async def show_user_profile(message: Message):
    """Показать профиль пользователя"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
        
        if not user:
            await message.answer("Пользователь не найден")
            return
        
        # Считаем статистику
        events_created_result = await session.execute(
            select(Event).where(Event.creator_id == user.id)
        )
        events_created = len(events_created_result.scalars().all())
        
        events_registered_result = await session.execute(
            select(EventRegistration)
            .join(User)
            .where(User.telegram_id == message.from_user.id)
        )
        events_registered = len(events_registered_result.scalars().all())
        
        # Предстоящие мероприятия
        upcoming_events_result = await session.execute(
            select(Event)
            .join(EventRegistration)
            .join(User)
            .where(
                User.telegram_id == message.from_user.id,
                Event.date_time > datetime.now()
            )
        )
        upcoming_events = len(upcoming_events_result.scalars().all())
    
    role_names = {
        'user': 'Пользователь',
        'moderator': 'Модератор', 
        'admin': 'Администратор'
    }
    
    profile_text = f"👤 <b>Ваш профиль</b>\n\n"
    profile_text += f"🔹 <b>Имя:</b> {user.first_name or 'Не указано'}"
    if user.last_name:
        profile_text += f" {user.last_name}"
    profile_text += "\n"
    
    if user.username:
        profile_text += f"🔹 <b>Username:</b> @{user.username}\n"
    
    profile_text += f"🔹 <b>Роль:</b> {role_names.get(user.role, 'Неизвестно')}\n"
    profile_text += f"🔹 <b>Город:</b> {user.city or 'Не выбран'}\n"
    profile_text += f"🔹 <b>Дата регистрации:</b> {user.created_at.strftime('%d.%m.%Y')}\n\n"
    
    profile_text += f"📊 <b>Статистика:</b>\n"
    if user.role in ['moderator', 'admin']:
        profile_text += f"• Создано мероприятий: {events_created}\n"
    profile_text += f"• Записей на мероприятия: {events_registered}\n"
    profile_text += f"• Предстоящих мероприятий: {upcoming_events}\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить имя", callback_data="edit_profile_name")],
        [InlineKeyboardButton(text="🏙️ Изменить город", callback_data="edit_profile_city")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    
    await message.answer(
        profile_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.message(F.text == "❓ Задать вопрос")
async def ask_question_handler(message: Message):
    """Задать вопрос (заглушка)"""
    await message.answer(
        "❓ Функция вопросов будет реализована позже.\n\n"
        "Пока что вы можете написать администратору напрямую."
    )

@router.callback_query(F.data == "edit_profile_name")
async def edit_profile_name(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование имени"""
    await safe_edit_message(
        callback,
        "✏️ Введите новое имя:",
        reply_markup=get_back_keyboard("back_to_menu")
    )
    await state.set_state(ProfileStates.waiting_for_name)
    await callback.answer()

@router.message(ProfileStates.waiting_for_name)
async def process_name_edit(message: Message, state: FSMContext):
    """Обработка нового имени"""
    new_name = message.text.strip()
    
    if len(new_name) > 100:
        await message.answer(
            "❌ Имя слишком длинное. Максимум 100 символов.\n\n"
            "Попробуйте еще раз или нажмите 'Назад':",
            reply_markup=get_back_keyboard("back_to_menu")
        )
        return
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
        
        if user:
            user.first_name = new_name
            await session.commit()
    
    await state.clear()
    await message.answer(
        f"✅ Имя успешно изменено на: {new_name}",
        reply_markup=get_main_menu(user.role if user else 'user')
    )

@router.callback_query(F.data == "edit_profile_city")
async def edit_profile_city(callback: CallbackQuery):
    """Редактирование города"""
    await safe_edit_message(
        callback,
        "🏙️ Выберите ваш город:",
        reply_markup=get_cities_keyboard()
    )
    await callback.answer()

# Дополнительные обработчики для улучшения UX

@router.callback_query(F.data.startswith("event_participants_"))
async def show_event_participants(callback: CallbackQuery):
    """Показать участников мероприятия (только для создателей и администраторов)"""
    event_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        # Проверяем права доступа
        user_result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user_result.scalar_one_or_none()
        
        event_result = await session.execute(select(Event).where(Event.id == event_id))
        event = event_result.scalar_one_or_none()
        
        if not user or not event:
            await callback.answer("Ошибка доступа", show_alert=True)
            return
        
        # Проверяем, есть ли права на просмотр участников
        if user.id != event.creator_id and user.role not in ['admin', 'moderator']:
            await callback.answer("У вас нет прав для просмотра участников", show_alert=True)
            return
        
        # Получаем участников
        participants_result = await session.execute(
            select(User)
            .join(EventRegistration)
            .where(EventRegistration.event_id == event_id)
            .order_by(EventRegistration.registered_at)
        )
        participants = participants_result.scalars().all()
    
    if not participants:
        participants_text = f"👥 Участники мероприятия: <b>{event.title}</b>\n\n"
        participants_text += "Пока никто не записался на мероприятие."
    else:
        participants_text = f"👥 Участники мероприятия: <b>{event.title}</b>\n\n"
        participants_text += f"Всего участников: {len(participants)}\n\n"
        
        for i, participant in enumerate(participants, 1):
            name = participant.first_name or "Имя не указано"
            if participant.last_name:
                name += f" {participant.last_name}"
            
            username = f"@{participant.username}" if participant.username else "нет username"
            participants_text += f"{i}. {name} ({username})\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к мероприятию", callback_data=f"event_{event_id}")]
    ])
    
    await safe_edit_message(
        callback,
        participants_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "show_main_menu")
async def show_main_menu_callback(callback: CallbackQuery):
    """Показать главное меню через callback"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        role = user.role if user else 'user'
    
    try:
        await callback.message.delete()
    except:
        pass
    
    await callback.message.answer(
        "📋 <b>Главное меню:</b>",
        parse_mode="HTML",
        reply_markup=get_main_menu(role)
    )
    await callback.answer()

@router.callback_query(F.data == "select_city_inline")
async def select_city_inline(callback: CallbackQuery):
    """Выбор города через inline кнопку"""
    await safe_edit_message(
        callback,
        "🏙️ <b>Выберите ваш город:</b>",
        parse_mode="HTML",
        reply_markup=get_cities_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "show_profile")
async def show_profile_callback(callback: CallbackQuery):
    """Показать профиль через callback"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Считаем статистику
        events_created_result = await session.execute(
            select(Event).where(Event.creator_id == user.id)
        )
        events_created = len(events_created_result.scalars().all())
        
        events_registered_result = await session.execute(
            select(EventRegistration)
            .join(User)
            .where(User.telegram_id == callback.from_user.id)
        )
        events_registered = len(events_registered_result.scalars().all())
        
        # Предстоящие мероприятия
        upcoming_events_result = await session.execute(
            select(Event)
            .join(EventRegistration)
            .join(User)
            .where(
                User.telegram_id == callback.from_user.id,
                Event.date_time > datetime.now()
            )
        )
        upcoming_events = len(upcoming_events_result.scalars().all())
    
    role_names = {
        'user': 'Пользователь',
        'moderator': 'Модератор', 
        'admin': 'Администратор'
    }
    
    profile_text = f"👤 <b>Ваш профиль</b>\n\n"
    profile_text += f"🔹 <b>Имя:</b> {user.first_name or 'Не указано'}"
    if user.last_name:
        profile_text += f" {user.last_name}"
    profile_text += "\n"
    
    if user.username:
        profile_text += f"🔹 <b>Username:</b> @{user.username}\n"
    
    profile_text += f"🔹 <b>Роль:</b> {role_names.get(user.role, 'Неизвестно')}\n"
    profile_text += f"🔹 <b>Город:</b> {user.city or 'Не выбран'}\n"
    profile_text += f"🔹 <b>Дата регистрации:</b> {user.created_at.strftime('%d.%m.%Y')}\n\n"
    
    profile_text += f"📊 <b>Статистика:</b>\n"
    if user.role in ['moderator', 'admin']:
        profile_text += f"• Создано мероприятий: {events_created}\n"
    profile_text += f"• Записей на мероприятия: {events_registered}\n"
    profile_text += f"• Предстоящих мероприятий: {upcoming_events}\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить имя", callback_data="edit_profile_name")],
        [InlineKeyboardButton(text="🏙️ Изменить город", callback_data="edit_profile_city")],
        [InlineKeyboardButton(text="🏠 На главную", callback_data="back_to_welcome")]
    ])
    
    await safe_edit_message(
        callback,
        profile_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_welcome")
async def back_to_welcome(callback: CallbackQuery):
    """Возврат к приветствию с ближайшим мероприятием"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
    
    await show_next_event_welcome(callback, user, is_callback=True)
    await callback.answer()

@router.message()
async def handle_unknown_message(message: Message):
    """Обработка неизвестных сообщений"""
    await message.answer(
        "🤔 Я не понимаю эту команду.\n\n"
        "Используйте кнопки меню для навигации или отправьте /start для перезапуска.",
        reply_markup=get_main_menu('user')
    )