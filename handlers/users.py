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
    get_back_keyboard
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


@router.message(Command("start"))
async def start_command(message: Message):
    """Команда /start"""
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )
    
    welcome_text = f"Добро пожаловать, {user.first_name}! 🎉\n\n"
    
    if user.role == 'admin':
        welcome_text += "Вы являетесь администратором бота.\n"
    elif user.role == 'moderator':
        welcome_text += "Вы являетесь модератором бота.\n"
    
    welcome_text += "Выберите действие из меню ниже:"
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_menu(user.role)
    )

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
    
    await safe_edit_message(
        callback,
        f"Ваш город: {city_name} ✅\n\nТеперь вы будете видеть мероприятия в вашем городе.",
        reply_markup=get_cities_keyboard()
    )
    await callback.answer()

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

@router.message()
async def handle_unknown_message(message: Message):
    """Обработка неизвестных сообщений"""
    await message.answer(
        "🤔 Я не понимаю эту команду.\n\n"
        "Используйте кнопки меню для навигации или отправьте /start для перезапуска.",
        reply_markup=get_main_menu('user')
    )