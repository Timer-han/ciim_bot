from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.database import async_session
from database.models import User, Event, EventRegistration
from keyboards.keyboards import (
    get_admin_panel_keyboard, get_event_management_keyboard,
    get_broadcast_keyboard, get_confirmation_keyboard,
    build_events_list_keyboard, get_back_keyboard, get_cancel_keyboard
)
from datetime import datetime, timedelta
import re

router = Router()

class CreateEventStates(StatesGroup):
    title = State()
    description = State()
    location = State()
    city = State()
    date_time = State()
    max_participants = State()
    registration_required = State()
    media = State()

class EditEventStates(StatesGroup):
    event_id = State()
    field = State()
    value = State()

class ManageAdminStates(StatesGroup):
    action = State()
    user_id = State()

async def check_admin_or_moderator(telegram_id: int) -> tuple[bool, str]:
    """Проверка прав админа или модератора"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        
        if not user or user.role not in ['admin', 'moderator']:
            return False, 'user'
        
        return True, user.role

@router.message(F.text == "⚙️ Панель управления")
async def show_admin_panel(message: Message):
    """Показать административную панель"""
    has_access, role = await check_admin_or_moderator(message.from_user.id)
    
    if not has_access:
        await message.answer("У вас нет доступа к панели управления")
        return
    
    await message.answer(
        f"Панель управления ({'Администратор' if role == 'admin' else 'Модератор'}):",
        reply_markup=get_admin_panel_keyboard(role)
    )

@router.callback_query(F.data == "admin_panel")
async def show_admin_panel_callback(callback: CallbackQuery):
    """Показать административную панель через callback"""
    has_access, role = await check_admin_or_moderator(callback.from_user.id)
    
    if not has_access:
        await callback.answer("У вас нет доступа к панели управления", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"Панель управления ({'Администратор' if role == 'admin' else 'Модератор'}):",
        reply_markup=get_admin_panel_keyboard(role)
    )

@router.callback_query(F.data == "create_event")
async def start_create_event(callback: CallbackQuery, state: FSMContext):
    """Начать создание мероприятия"""
    has_access, role = await check_admin_or_moderator(callback.from_user.id)
    
    if not has_access:
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    await state.set_state(CreateEventStates.title)
    await callback.message.edit_text(
        "📝 Создание нового мероприятия\n\n"
        "Введите название мероприятия:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(CreateEventStates.title)
async def process_event_title(message: Message, state: FSMContext):
    """Обработка названия мероприятия"""
    await state.update_data(title=message.text)
    await state.set_state(CreateEventStates.description)
    
    await message.answer(
        "📄 Введите описание мероприятия\n"
        "(или отправьте '-' чтобы пропустить):",
        reply_markup=get_cancel_keyboard()
    )

@router.message(CreateEventStates.description)
async def process_event_description(message: Message, state: FSMContext):
    """Обработка описания мероприятия"""
    description = None if message.text == '-' else message.text
    await state.update_data(description=description)
    await state.set_state(CreateEventStates.location)
    
    await message.answer(
        "📍 Введите место проведения мероприятия\n"
        "(или отправьте '-' чтобы пропустить):",
        reply_markup=get_cancel_keyboard()
    )

@router.message(CreateEventStates.location)
async def process_event_location(message: Message, state: FSMContext):
    """Обработка места проведения"""
    location = None if message.text == '-' else message.text
    await state.update_data(location=location)
    await state.set_state(CreateEventStates.city)
    
    await message.answer(
        "🏙️ Выберите город:\n"
        "1 - Москва\n"
        "2 - Казань",
        reply_markup=get_cancel_keyboard()
    )

@router.message(CreateEventStates.city)
async def process_event_city(message: Message, state: FSMContext):
    """Обработка выбора города"""
    if message.text == "1":
        city = "Москва"
    elif message.text == "2":
        city = "Казань"
    else:
        await message.answer(
            "Пожалуйста, выберите 1 (Москва) или 2 (Казань)",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    await state.update_data(city=city)
    await state.set_state(CreateEventStates.date_time)
    
    await message.answer(
        "📅 Введите дату и время мероприятия\n"
        "Формат: ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Например: 25.12.2024 18:30",
        reply_markup=get_cancel_keyboard()
    )

@router.message(CreateEventStates.date_time)
async def process_event_datetime(message: Message, state: FSMContext):
    """Обработка даты и времени"""
    try:
        # Парсим дату и время
        datetime_obj = datetime.strptime(message.text, "%d.%m.%Y %H:%M")
        
        # Проверяем, что дата в будущем
        if datetime_obj <= datetime.now():
            await message.answer(
                "Дата должна быть в будущем. Попробуйте еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        await state.update_data(date_time=datetime_obj)
        await state.set_state(CreateEventStates.max_participants)
        
        await message.answer(
            "👥 Введите максимальное количество участников\n"
            "(или отправьте '-' для неограниченного количества):",
            reply_markup=get_cancel_keyboard()
        )
        
    except ValueError:
        await message.answer(
            "Неверный формат даты. Используйте: ДД.ММ.ГГГГ ЧЧ:ММ\n"
            "Например: 25.12.2024 18:30",
            reply_markup=get_cancel_keyboard()
        )

@router.message(CreateEventStates.max_participants)
async def process_event_max_participants(message: Message, state: FSMContext):
    """Обработка максимального количества участников"""
    max_participants = None
    
    if message.text != '-':
        try:
            max_participants = int(message.text)
            if max_participants <= 0:
                await message.answer(
                    "Количество участников должно быть положительным числом:",
                    reply_markup=get_cancel_keyboard()
                )
                return
        except ValueError:
            await message.answer(
                "Введите число или '-' для неограниченного количества:",
                reply_markup=get_cancel_keyboard()
            )
            return
    
    await state.update_data(max_participants=max_participants)
    await state.set_state(CreateEventStates.registration_required)
    
    await message.answer(
        "✅ Требуется ли регистрация на мероприятие?\n"
        "1 - Да, требуется регистрация\n"
        "2 - Нет, регистрация не нужна",
        reply_markup=get_cancel_keyboard()
    )

@router.message(CreateEventStates.registration_required)
async def process_event_registration_required(message: Message, state: FSMContext):
    """Обработка необходимости регистрации"""
    if message.text == "1":
        registration_required = True
    elif message.text == "2":
        registration_required = False
    else:
        await message.answer(
            "Пожалуйста, выберите 1 (Да) или 2 (Нет)",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    await state.update_data(registration_required=registration_required)
    await state.set_state(CreateEventStates.media)
    
    await message.answer(
        "📸 Прикрепите фото или видео к мероприятию\n"
        "(или отправьте '-' чтобы пропустить):",
        reply_markup=get_cancel_keyboard()
    )

@router.message(CreateEventStates.media)
async def process_event_media(message: Message, state: FSMContext):
    """Обработка медиафайлов мероприятия"""
    photo_file_id = None
    video_file_id = None
    media_type = None
    
    if message.text and message.text == '-':
        # Пропускаем медиа
        pass
    elif message.photo:
        # Получаем наибольшее фото
        photo_file_id = message.photo[-1].file_id
        media_type = 'photo'
    elif message.video:
        video_file_id = message.video.file_id
        media_type = 'video'
    elif message.text != '-':
        await message.answer(
            "Пожалуйста, отправьте фото, видео или '-' чтобы пропустить:",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    # Получаем все данные
    data = await state.get_data()
    
    # Создаем мероприятие
    async with async_session() as session:
        # Получаем создателя
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        creator = result.scalar_one_or_none()
        
        if not creator:
            await message.answer("Ошибка: пользователь не найден")
            await state.clear()
            return
        
        # Создаем мероприятие
        event = Event(
            title=data['title'],
            description=data['description'],
            location=data['location'],
            city=data['city'],
            date_time=data['date_time'],
            creator_id=creator.id,
            max_participants=data['max_participants'],
            registration_required=data['registration_required'],
            photo_file_id=photo_file_id,
            video_file_id=video_file_id,
            media_type=media_type
        )
        
        session.add(event)
        await session.commit()
        await session.refresh(event)
    
    # Формируем итоговое сообщение
    summary = f"✅ Мероприятие создано!\n\n"
    summary += f"📅 <b>{event.title}</b>\n"
    summary += f"📝 <b>Описание:</b> {event.description or 'Не указано'}\n"
    summary += f"📍 <b>Место:</b> {event.location or 'Не указано'}\n"
    summary += f"🏙️ <b>Город:</b> {event.city}\n"
    summary += f"🕐 <b>Дата:</b> {event.date_time.strftime('%d.%m.%Y в %H:%M')}\n"
    summary += f"👥 <b>Участники:</b> {'Неограниченно' if not event.max_participants else event.max_participants}\n"
    summary += f"✅ <b>Регистрация:</b> {'Требуется' if event.registration_required else 'Не требуется'}\n"
    summary += f"📸 <b>Медиа:</b> {'Прикреплено' if media_type else 'Нет'}\n"
    
    # Отправляем сообщение с медиа если есть
    if photo_file_id:
        await message.answer_photo(
            photo=photo_file_id,
            caption=summary,
            parse_mode="HTML",
            reply_markup=get_back_keyboard("admin_panel")
        )
    elif video_file_id:
        await message.answer_video(
            video=video_file_id,
            caption=summary,
            parse_mode="HTML",
            reply_markup=get_back_keyboard("admin_panel")
        )
    else:
        await message.answer(
            summary,
            parse_mode="HTML",
            reply_markup=get_back_keyboard("admin_panel")
        )
    
    await state.clear()

@router.callback_query(F.data == "manage_events")
async def show_event_management(callback: CallbackQuery):
    """Показать управление мероприятиями"""
    has_access, role = await check_admin_or_moderator(callback.from_user.id)
    
    if not has_access:
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📝 Управление мероприятиями:",
        reply_markup=get_event_management_keyboard()
    )

@router.callback_query(F.data == "my_created_events")
async def show_my_created_events(callback: CallbackQuery):
    """Показать мои созданные мероприятия"""
    async with async_session() as session:
        # Получаем пользователя
        user_result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user_result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Получаем созданные мероприятия
        events_result = await session.execute(
            select(Event)
            .where(Event.creator_id == user.id)
            .order_by(Event.date_time)
        )
        events = events_result.scalars().all()
    
    if not events:
        await callback.message.edit_text(
            "У вас пока нет созданных мероприятий",
            reply_markup=get_back_keyboard("manage_events")
        )
        return
    
    await callback.message.edit_text(
        "Ваши мероприятия:",
        reply_markup=build_events_list_keyboard(events, "manage_event")
    )

@router.callback_query(F.data == "broadcast")
async def show_broadcast_menu(callback: CallbackQuery):
    """Показать меню рассылки"""
    has_access, role = await check_admin_or_moderator(callback.from_user.id)
    
    if not has_access:
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📢 Рассылка сообщений:\n\n"
        "Выберите целевую аудиторию:",
        reply_markup=get_broadcast_keyboard()
    )

@router.callback_query(F.data.startswith("broadcast_"))
async def handle_broadcast_selection(callback: CallbackQuery):
    """Обработка выбора типа рассылки (заглушка)"""
    broadcast_type = callback.data.split("_")[1]
    
    type_names = {
        "all": "всем пользователям",
        "moscow": "пользователям из Москвы",
        "kazan": "пользователям из Казани",
        "event": "зарегистрированным на мероприятие"
    }
    
    await callback.message.edit_text(
        f"📢 Рассылка {type_names.get(broadcast_type, 'выбранной группе')} будет реализована позже",
        reply_markup=get_back_keyboard("broadcast")
    )

@router.callback_query(F.data == "user_questions")
async def show_user_questions(callback: CallbackQuery):
    """Показать вопросы пользователей (заглушка)"""
    has_access, role = await check_admin_or_moderator(callback.from_user.id)
    
    if not has_access:
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "❓ Функция вопросов пользователей будет реализована позже",
        reply_markup=get_back_keyboard("admin_panel")
    )

@router.callback_query(F.data.startswith("manage_event_"))
async def show_event_management_details(callback: CallbackQuery):
    """Показать детали управления мероприятием"""
    event_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        result = await session.execute(select(Event).where(Event.id == event_id))
        event = result.scalar_one_or_none()
        
        if not event:
            await callback.answer("Мероприятие не найдено", show_alert=True)
            return
        
        # Проверяем права доступа
        user_result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = user_result.scalar_one_or_none()
        
        if not user or (user.role not in ['admin', 'moderator'] and user.id != event.creator_id):
            await callback.answer("У вас нет прав для управления этим мероприятием", show_alert=True)
            return
        
        # Считаем участников
        participants_result = await session.execute(
            select(EventRegistration).where(EventRegistration.event_id == event_id)
        )
        participants_count = len(participants_result.scalars().all())
    
    # Формируем текст
    event_text = f"📅 <b>{event.title}</b>\n\n"
    event_text += f"📝 <b>Описание:</b> {event.description or 'Не указано'}\n"
    event_text += f"📍 <b>Место:</b> {event.location or 'Не указано'}\n"
    event_text += f"🏙️ <b>Город:</b> {event.city}\n"
    event_text += f"🕐 <b>Дата:</b> {event.date_time.strftime('%d.%m.%Y в %H:%M')}\n"
    event_text += f"👥 <b>Участники:</b> {participants_count}"
    if event.max_participants:
        event_text += f"/{event.max_participants}"
    event_text += "\n"
    event_text += f"✅ <b>Регистрация:</b> {'Требуется' if event.registration_required else 'Не требуется'}\n"
    event_text += f"👁 <b>Видимость:</b> {'Видимо' if event.is_visible else 'Скрыто'}\n"
    event_text += f"🔓 <b>Регистрация:</b> {'Открыта' if event.registration_open else 'Закрыта'}\n"
    
    # Клавиатура управления
    keyboard = [
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_event_{event_id}")],
        [InlineKeyboardButton(text="👥 Участники", callback_data=f"event_participants_{event_id}")],
        [
            InlineKeyboardButton(
                text="👁 Скрыть" if event.is_visible else "👁 Показать", 
                callback_data=f"toggle_visibility_{event_id}"
            ),
            InlineKeyboardButton(
                text="🔒 Закрыть рег." if event.registration_open else "🔓 Открыть рег.", 
                callback_data=f"toggle_registration_{event_id}"
            )
        ],
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_event_{event_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="my_created_events")]
    ]
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    # Отправляем с медиа если есть
    if event.photo_file_id:
        await callback.message.answer_photo(
            photo=event.photo_file_id,
            caption=event_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.message.delete()
    elif event.video_file_id:
        await callback.message.answer_video(
            video=event.video_file_id,
            caption=event_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.message.delete()
    else:
        await callback.message.edit_text(
            event_text,
            parse_mode="HTML",
            reply_markup=markup
        )

@router.callback_query(F.data.startswith("delete_event_"))
async def confirm_delete_event(callback: CallbackQuery):
    """Подтверждение удаления мероприятия"""
    event_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        result = await session.execute(select(Event).where(Event.id == event_id))
        event = result.scalar_one_or_none()
        
        if not event:
            await callback.answer("Мероприятие не найдено", show_alert=True)
            return
    
    await callback.message.edit_text(
        f"⚠️ Вы уверены, что хотите удалить мероприятие?\n\n"
        f"📅 <b>{event.title}</b>\n"
        f"🕐 {event.date_time.strftime('%d.%m.%Y в %H:%M')}\n\n"
        f"❗️ Это действие нельзя отменить!",
        parse_mode="HTML",
        reply_markup=get_confirmation_keyboard("delete_event", event_id)
    )

@router.callback_query(F.data.startswith("confirm_delete_event_"))
async def delete_event_confirmed(callback: CallbackQuery):
    """Удаление мероприятия"""
    event_id = int(callback.data.split("_")[3])
    
    async with async_session() as session:
        # Удаляем все регистрации
        await session.execute(
            select(EventRegistration).where(EventRegistration.event_id == event_id)
        )
        registrations = await session.execute(
            select(EventRegistration).where(EventRegistration.event_id == event_id)
        )
        for reg in registrations.scalars().all():
            await session.delete(reg)
        
        # Удаляем мероприятие
        event_result = await session.execute(select(Event).where(Event.id == event_id))
        event = event_result.scalar_one_or_none()
        
        if event:
            await session.delete(event)
            await session.commit()
    
    await callback.message.edit_text(
        "✅ Мероприятие успешно удалено",
        reply_markup=get_back_keyboard("my_created_events")
    )

@router.callback_query(F.data.startswith("cancel_delete_event_"))
async def cancel_delete_event(callback: CallbackQuery):
    """Отмена удаления мероприятия"""
    event_id = int(callback.data.split("_")[3])
    await show_event_management_details(callback)

@router.callback_query(F.data.startswith("toggle_visibility_"))
async def toggle_event_visibility(callback: CallbackQuery):
    """Переключение видимости мероприятия"""
    event_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        result = await session.execute(select(Event).where(Event.id == event_id))
        event = result.scalar_one_or_none()
        
        if not event:
            await callback.answer("Мероприятие не найдено", show_alert=True)
            return
        
        event.is_visible = not event.is_visible
        await session.commit()
    
    status = "показано" if event.is_visible else "скрыто"
    await callback.answer(f"Мероприятие {status}")
    await show_event_management_details(callback)

@router.callback_query(F.data.startswith("toggle_registration_"))
async def toggle_event_registration(callback: CallbackQuery):
    """Переключение регистрации на мероприятие"""
    event_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        result = await session.execute(select(Event).where(Event.id == event_id))
        event = result.scalar_one_or_none()
        
        if not event:
            await callback.answer("Мероприятие не найдено", show_alert=True)
            return
        
        event.registration_open = not event.registration_open
        await session.commit()
    
    status = "открыта" if event.registration_open else "закрыта"
    await callback.answer(f"Регистрация {status}")
    await show_event_management_details(callback)

@router.callback_query(F.data.startswith("event_participants_"))
async def show_event_participants(callback: CallbackQuery):
    """Показать участников мероприятия"""
    event_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        # Получаем мероприятие
        event_result = await session.execute(select(Event).where(Event.id == event_id))
        event = event_result.scalar_one_or_none()
        
        if not event:
            await callback.answer("Мероприятие не найдено", show_alert=True)
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
        text = f"👥 Участники мероприятия <b>{event.title}</b>\n\n"
        text += "Пока никто не записался 😔"
    else:
        text = f"👥 Участники мероприятия <b>{event.title}</b>\n\n"
        for i, participant in enumerate(participants, 1):
            name = participant.first_name or "Неизвестно"
            if participant.last_name:
                name += f" {participant.last_name}"
            if participant.username:
                name += f" (@{participant.username})"
            text += f"{i}. {name}\n"
        
        text += f"\n📊 Всего участников: {len(participants)}"
        if event.max_participants:
            text += f"/{event.max_participants}"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_back_keyboard(f"manage_event_{event_id}")
    )

@router.callback_query(F.data == "manage_moderators")
async def show_moderator_management(callback: CallbackQuery):
    """Управление модераторами (только для админов)"""
    has_access, role = await check_admin_or_moderator(callback.from_user.id)
    
    if not has_access or role != 'admin':
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    # Получаем список модераторов
    async with async_session() as session:
        result = await session.execute(select(User).where(User.role == 'moderator'))
        moderators = result.scalars().all()
        
        admin_result = await session.execute(select(User).where(User.role == 'admin'))
        admins = admin_result.scalars().all()
    
    text = "👥 <b>Управление ролями</b>\n\n"
    
    text += f"👑 <b>Администраторы ({len(admins)}):</b>\n"
    for admin in admins:
        name = admin.first_name or "Неизвестно"
        if admin.username:
            name += f" (@{admin.username})"
        text += f"• {name}\n"
    
    text += f"\n🛡 <b>Модераторы ({len(moderators)}):</b>\n"
    if moderators:
        for mod in moderators:
            name = mod.first_name or "Неизвестно"
            if mod.username:
                name += f" (@{mod.username})"
            text += f"• {name}\n"
    else:
        text += "Нет модераторов\n"
    
    keyboard = [
        [InlineKeyboardButton(text="➕ Добавить администратора", callback_data="add_admin")],
        [InlineKeyboardButton(text="➕ Добавить модератора", callback_data="add_moderator")],
        [InlineKeyboardButton(text="➖ Удалить модератора", callback_data="remove_moderator")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ]
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@router.callback_query(F.data.in_(["add_admin", "add_moderator", "remove_moderator"]))
async def start_manage_admin_action(callback: CallbackQuery, state: FSMContext):
    """Начать действие с администраторами/модераторами"""
    action = callback.data
    
    await state.set_state(ManageAdminStates.action)
    await state.update_data(action=action)
    await state.set_state(ManageAdminStates.user_id)
    
    action_text = {
        "add_admin": "добавления администратора",
        "add_moderator": "добавления модератора", 
        "remove_moderator": "удаления модератора"
    }
    
    await callback.message.edit_text(
        f"🆔 Для {action_text[action]} введите Telegram ID пользователя:\n\n"
        f"💡 Чтобы узнать ID, пользователь может написать @userinfobot",
        reply_markup=get_back_keyboard("manage_moderators")
    )

@router.message(ManageAdminStates.user_id)
async def process_admin_user_id(message: Message, state: FSMContext):
    """Обработка ID пользователя для управления ролями"""
    try:
        user_id = int(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введите корректный числовой ID")
        return
    
    data = await state.get_data()
    action = data['action']
    
    async with async_session() as session:
        # Находим пользователя по telegram_id
        result = await session.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            await message.answer(
                "❌ Пользователь не найден в системе.\n"
                "Пользователь должен сначала запустить бота командой /start"
            )
            return
        
        # Выполняем действие
        if action == "add_admin":
            if user.role == 'admin':
                await message.answer("❌ Пользователь уже является администратором")
                return
            user.role = 'admin'
            role_name = "администратором"
        elif action == "add_moderator":
            if user.role in ['admin', 'moderator']:
                await message.answer(f"❌ Пользователь уже является {user.role}")
                return
            user.role = 'moderator'
            role_name = "модератором"
        elif action == "remove_moderator":
            if user.role != 'moderator':
                await message.answer("❌ Пользователь не является модератором")
                return
            user.role = 'user'
            role_name = "обычным пользователем"
        
        await session.commit()
    
    user_name = user.first_name or "Неизвестно"
    if user.username:
        user_name += f" (@{user.username})"
    
    await message.answer(
        f"✅ Пользователь {user_name} теперь является {role_name}",
        reply_markup=get_back_keyboard("manage_moderators")
    )
    
    await state.clear()

# Добавляем обработчик отмены для всех состояний
@router.callback_query(F.data == "admin_panel")
async def cancel_any_state(callback: CallbackQuery, state: FSMContext):
    """Отмена любого состояния и возврат в админ панель"""
    await state.clear()
    await show_admin_panel_callback(callback)