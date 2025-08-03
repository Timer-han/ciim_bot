from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from database.database import async_session
from database.models import User, Event, EventRegistration
from keyboards.keyboards import (
    get_admin_panel_keyboard, get_event_management_keyboard,
    get_broadcast_keyboard, get_confirmation_keyboard,
    build_events_list_keyboard, get_back_keyboard, get_cancel_keyboard
)
from datetime import datetime, timedelta
import re
import logging
import asyncio

router = Router()
logger = logging.getLogger(__name__)

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

class BroadcastStates(StatesGroup):
    target = State()
    message_text = State()
    confirm = State()

async def check_admin_or_moderator(telegram_id: int) -> tuple[bool, str]:
    """Проверка прав админа или модератора"""
    try:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.telegram_id == telegram_id))
            user = result.scalar_one_or_none()
            
            if not user or user.role not in ['admin', 'moderator']:
                return False, 'user'
            
            return True, user.role
    except Exception as e:
        logger.error(f"Ошибка проверки прав пользователя {telegram_id}: {e}")
        return False, 'user'

async def check_admin_only(telegram_id: int) -> bool:
    """Проверка прав только для админа"""
    has_access, role = await check_admin_or_moderator(telegram_id)
    return has_access and role == 'admin'

async def get_user_stats() -> dict:
    """Получение статистики пользователей"""
    try:
        async with async_session() as session:
            # Общая статистика пользователей
            total_users = await session.execute(select(func.count(User.id)))
            total_count = total_users.scalar()
            
            # По ролям
            admins = await session.execute(select(func.count(User.id)).where(User.role == 'admin'))
            moderators = await session.execute(select(func.count(User.id)).where(User.role == 'moderator'))
            users = await session.execute(select(func.count(User.id)).where(User.role == 'user'))
            
            # По городам
            moscow = await session.execute(select(func.count(User.id)).where(User.city == 'Москва'))
            kazan = await session.execute(select(func.count(User.id)).where(User.city == 'Казань'))
            no_city = await session.execute(select(func.count(User.id)).where(User.city.is_(None)))
            
            # Активность за последние 7 дней
            week_ago = datetime.now() - timedelta(days=7)
            recent_users = await session.execute(
                select(func.count(User.id)).where(User.created_at >= week_ago)
            )
            
            return {
                'total': total_count,
                'admins': admins.scalar(),
                'moderators': moderators.scalar(),
                'users': users.scalar(),
                'moscow': moscow.scalar(),
                'kazan': kazan.scalar(),
                'no_city': no_city.scalar(),
                'recent': recent_users.scalar()
            }
    except Exception as e:
        logger.error(f"Ошибка получения статистики пользователей: {e}")
        return {}

async def get_events_stats() -> dict:
    """Получение статистики мероприятий"""
    try:
        async with async_session() as session:
            now = datetime.now()
            
            # Общая статистика
            total_events = await session.execute(select(func.count(Event.id)))
            upcoming_events = await session.execute(
                select(func.count(Event.id)).where(and_(Event.date_time > now, Event.is_visible == True))
            )
            past_events = await session.execute(
                select(func.count(Event.id)).where(Event.date_time <= now)
            )
            hidden_events = await session.execute(
                select(func.count(Event.id)).where(Event.is_visible == False)
            )
            
            # По городам
            moscow_events = await session.execute(
                select(func.count(Event.id)).where(and_(Event.city == 'Москва', Event.date_time > now))
            )
            kazan_events = await session.execute(
                select(func.count(Event.id)).where(and_(Event.city == 'Казань', Event.date_time > now))
            )
            
            # Регистрации
            total_registrations = await session.execute(select(func.count(EventRegistration.id)))
            
            return {
                'total': total_events.scalar(),
                'upcoming': upcoming_events.scalar(),
                'past': past_events.scalar(),
                'hidden': hidden_events.scalar(),
                'moscow': moscow_events.scalar(),
                'kazan': kazan_events.scalar(),
                'registrations': total_registrations.scalar()
            }
    except Exception as e:
        logger.error(f"Ошибка получения статистики мероприятий: {e}")
        return {}
    
async def safe_edit_message(callback: CallbackQuery, text: str, reply_markup=None, parse_mode="HTML"):
    """Безопасное редактирование сообщения с fallback на удаление и отправку нового"""
    try:
        await callback.message.edit_text(
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
    except Exception:
        # Если не получается отредактировать, удаляем и отправляем новое
        try:
            await callback.message.delete()
        except Exception:
            pass
        
        await callback.message.answer(
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )


@router.message(F.text == "⚙️ Панель управления")
async def show_admin_panel(message: Message):
    """Показать административную панель"""
    has_access, role = await check_admin_or_moderator(message.from_user.id)
    
    if not has_access:
        await message.answer("❌ У вас нет доступа к панели управления")
        return
    
    # Получаем статистику
    user_stats = await get_user_stats()
    event_stats = await get_events_stats()
    
    stats_text = f"📊 <b>Статистика бота</b>\n\n"
    
    if user_stats:
        stats_text += f"👥 <b>Пользователи:</b>\n"
        stats_text += f"• Всего: {user_stats.get('total', 0)}\n"
        stats_text += f"• Админы: {user_stats.get('admins', 0)}\n"
        stats_text += f"• Модераторы: {user_stats.get('moderators', 0)}\n"
        stats_text += f"• Пользователи: {user_stats.get('users', 0)}\n"
        stats_text += f"• Новых за неделю: {user_stats.get('recent', 0)}\n\n"
        
        stats_text += f"🏙️ <b>По городам:</b>\n"
        stats_text += f"• Москва: {user_stats.get('moscow', 0)}\n"
        stats_text += f"• Казань: {user_stats.get('kazan', 0)}\n"
        stats_text += f"• Без города: {user_stats.get('no_city', 0)}\n\n"
    
    if event_stats:
        stats_text += f"📅 <b>Мероприятия:</b>\n"
        stats_text += f"• Всего: {event_stats.get('total', 0)}\n"
        stats_text += f"• Предстоящих: {event_stats.get('upcoming', 0)}\n"
        stats_text += f"• Прошедших: {event_stats.get('past', 0)}\n"
        stats_text += f"• Скрытых: {event_stats.get('hidden', 0)}\n"
        stats_text += f"• Регистраций: {event_stats.get('registrations', 0)}\n"
    
    await message.answer(
        stats_text,
        parse_mode="HTML",
        reply_markup=get_admin_panel_keyboard(role)
    )

@router.callback_query(F.data == "admin_panel")
async def show_admin_panel_callback(callback: CallbackQuery):
    """Показать административную панель через callback"""
    has_access, role = await check_admin_or_moderator(callback.from_user.id)
    
    if not has_access:
        await callback.answer("❌ У вас нет доступа к панели управления", show_alert=True)
        return
    
    # Получаем статистику
    user_stats = await get_user_stats()
    event_stats = await get_events_stats()
    
    stats_text = f"📊 <b>Панель управления</b>\n"
    stats_text += f"Роль: {'Администратор' if role == 'admin' else 'Модератор'}\n\n"
    
    if user_stats and event_stats:
        stats_text += f"👥 Пользователей: {user_stats.get('total', 0)}\n"
        stats_text += f"📅 Мероприятий: {event_stats.get('upcoming', 0)} предстоящих\n"
        stats_text += f"✅ Регистраций: {event_stats.get('registrations', 0)}\n"
    
    await safe_edit_message(
        callback,
        stats_text,
        parse_mode="HTML",
        reply_markup=get_admin_panel_keyboard(role)
    )

@router.callback_query(F.data == "create_event")
async def start_create_event(callback: CallbackQuery, state: FSMContext):
    """Начать создание мероприятия"""
    has_access, role = await check_admin_or_moderator(callback.from_user.id)
    
    if not has_access:
        await callback.answer("❌ У вас нет доступа", show_alert=True)
        return
    
    await state.set_state(CreateEventStates.title)
    await safe_edit_message(
        callback,
        "📝 <b>Создание нового мероприятия</b>\n\n"
        "Шаг 1/7: Введите название мероприятия:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )

@router.message(CreateEventStates.title)
async def process_event_title(message: Message, state: FSMContext):
    """Обработка названия мероприятия"""
    if len(message.text) > 255:
        await message.answer(
            "❌ Название слишком длинное (максимум 255 символов). Попробуйте короче:",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    await state.update_data(title=message.text.strip())
    await state.set_state(CreateEventStates.description)
    
    await message.answer(
        "📄 <b>Шаг 2/7:</b> Введите описание мероприятия\n"
        "(или отправьте <code>-</code> чтобы пропустить):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )

@router.message(CreateEventStates.description)
async def process_event_description(message: Message, state: FSMContext):
    """Обработка описания мероприятия"""
    description = None if message.text.strip() == '-' else message.text.strip()
    await state.update_data(description=description)
    await state.set_state(CreateEventStates.location)
    
    await message.answer(
        "📍 <b>Шаг 3/7:</b> Введите место проведения мероприятия\n"
        "(или отправьте <code>-</code> чтобы пропустить):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )

@router.message(CreateEventStates.location)
async def process_event_location(message: Message, state: FSMContext):
    """Обработка места проведения"""
    location = None if message.text.strip() == '-' else message.text.strip()
    await state.update_data(location=location)
    await state.set_state(CreateEventStates.city)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏢 Москва", callback_data="city_select_moscow")],
        [InlineKeyboardButton(text="🕌 Казань", callback_data="city_select_kazan")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="admin_panel")]
    ])
    
    await message.answer(
        "🏙️ <b>Шаг 4/7:</b> Выберите город:",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("city_select_"))
async def process_event_city_callback(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора города через callback"""
    city_code = callback.data.split("_")[2]
    city = "Москва" if city_code == "moscow" else "Казань"
    
    await state.update_data(city=city)
    await state.set_state(CreateEventStates.date_time)
    
    await safe_edit_message(
        callback,
        f"✅ Выбран город: <b>{city}</b>\n\n"
        "📅 <b>Шаг 5/7:</b> Введите дату и время мероприятия\n\n"
        "Формат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
        "Например: <code>25.12.2024 18:30</code>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )

@router.message(CreateEventStates.date_time)
async def process_event_datetime(message: Message, state: FSMContext):
    """Обработка даты и времени"""
    try:
        # Парсим дату и время
        datetime_obj = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        
        # Проверяем, что дата в будущем (минимум через час)
        min_time = datetime.now() + timedelta(hours=1)
        if datetime_obj <= min_time:
            await message.answer(
                "❌ Дата должна быть минимум через час от текущего времени.\n"
                f"Текущее время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                "Попробуйте еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        # Проверяем, что дата не слишком далеко в будущем (максимум год)
        max_time = datetime.now() + timedelta(days=365)
        if datetime_obj > max_time:
            await message.answer(
                "❌ Дата не может быть более чем через год.\n"
                "Попробуйте еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        await state.update_data(date_time=datetime_obj)
        await state.set_state(CreateEventStates.max_participants)
        
        await message.answer(
            f"✅ Дата установлена: <b>{datetime_obj.strftime('%d.%m.%Y в %H:%M')}</b>\n\n"
            "👥 <b>Шаг 6/7:</b> Введите максимальное количество участников\n"
            "(или отправьте <code>-</code> для неограниченного количества):",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты. Используйте: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
            "Например: <code>25.12.2024 18:30</code>",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )

@router.message(CreateEventStates.max_participants)
async def process_event_max_participants(message: Message, state: FSMContext):
    """Обработка максимального количества участников"""
    max_participants = None
    
    if message.text.strip() != '-':
        try:
            max_participants = int(message.text.strip())
            if max_participants <= 0:
                await message.answer(
                    "❌ Количество участников должно быть положительным числом:",
                    reply_markup=get_cancel_keyboard()
                )
                return
            if max_participants > 10000:
                await message.answer(
                    "❌ Слишком большое количество участников (максимум 10000):",
                    reply_markup=get_cancel_keyboard()
                )
                return
        except ValueError:
            await message.answer(
                "❌ Введите число или <code>-</code> для неограниченного количества:",
                parse_mode="HTML",
                reply_markup=get_cancel_keyboard()
            )
            return
    
    await state.update_data(max_participants=max_participants)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, требуется", callback_data="registration_required_yes")],
        [InlineKeyboardButton(text="❌ Нет, не нужна", callback_data="registration_required_no")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="admin_panel")]
    ])
    
    limit_text = f"{max_participants} участников" if max_participants else "неограниченно"
    await message.answer(
        f"✅ Лимит участников: <b>{limit_text}</b>\n\n"
        "📝 <b>Шаг 7/7:</b> Требуется ли регистрация на мероприятие?",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("registration_required_"))
async def process_registration_required(callback: CallbackQuery, state: FSMContext):
    """Обработка необходимости регистрации"""
    registration_required = callback.data.split("_")[2] == "yes"
    await state.update_data(registration_required=registration_required)
    await state.set_state(CreateEventStates.media)
    
    reg_text = "требуется" if registration_required else "не требуется"
    await safe_edit_message(
        callback,
        f"✅ Регистрация: <b>{reg_text}</b>\n\n"
        "📸 <b>Финальный шаг:</b> Прикрепите фото или видео к мероприятию\n"
        "(или отправьте <code>-</code> чтобы пропустить):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )

@router.message(CreateEventStates.media)
async def process_event_media(message: Message, state: FSMContext):
    """Обработка медиафайлов мероприятия"""
    photo_file_id = None
    video_file_id = None
    media_type = None
    
    if message.text and message.text.strip() == '-':
        # Пропускаем медиа
        pass
    elif message.photo:
        # Получаем наибольшее фото
        photo_file_id = message.photo[-1].file_id
        media_type = 'photo'
    elif message.video:
        # Проверяем размер видео
        if message.video.file_size and message.video.file_size > 50 * 1024 * 1024:  # 50MB
            await message.answer(
                "❌ Размер видео слишком большой (максимум 50MB).\n"
                "Попробуйте другое видео или отправьте <code>-</code> чтобы пропустить:",
                parse_mode="HTML",
                reply_markup=get_cancel_keyboard()
            )
            return
        video_file_id = message.video.file_id
        media_type = 'video'
    elif message.text != '-':
        await message.answer(
            "❌ Пожалуйста, отправьте фото, видео или <code>-</code> чтобы пропустить:",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    # Получаем все данные
    data = await state.get_data()
    
    try:
        # Создаем мероприятие
        async with async_session() as session:
            # Получаем создателя
            result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
            creator = result.scalar_one_or_none()
            
            if not creator:
                await message.answer("❌ Ошибка: пользователь не найден")
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
        summary = f"🎉 <b>Мероприятие успешно создано!</b>\n\n"
        summary += f"📅 <b>{event.title}</b>\n"
        summary += f"📝 <b>Описание:</b> {event.description or 'Не указано'}\n"
        summary += f"📍 <b>Место:</b> {event.location or 'Не указано'}\n"
        summary += f"🏙️ <b>Город:</b> {event.city}\n"
        summary += f"🕐 <b>Дата:</b> {event.date_time.strftime('%d.%m.%Y в %H:%M')}\n"
        summary += f"👥 <b>Участники:</b> {'Неограниченно' if not event.max_participants else event.max_participants}\n"
        summary += f"✅ <b>Регистрация:</b> {'Требуется' if event.registration_required else 'Не требуется'}\n"
        summary += f"📸 <b>Медиа:</b> {'Прикреплено' if media_type else 'Нет'}\n"
        summary += f"\n🆔 <b>ID мероприятия:</b> {event.id}"
        
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
        
        logger.info(f"Создано мероприятие {event.id} пользователем {creator.telegram_id}")
        
    except Exception as e:
        logger.error(f"Ошибка создания мероприятия: {e}")
        await message.answer(
            "❌ Произошла ошибка при создании мероприятия. Попробуйте позже.",
            reply_markup=get_back_keyboard("admin_panel")
        )
    finally:
        await state.clear()


@router.callback_query(F.data == "my_created_events")
async def show_my_created_events(callback: CallbackQuery):
    """Показать мои созданные мероприятия"""
    try:
        async with async_session() as session:
            # Получаем пользователя
            user_result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
            user = user_result.scalar_one_or_none()
            
            if not user:
                await callback.answer("❌ Пользователь не найден", show_alert=True)
                return
            
            # Получаем созданные мероприятия
            events_result = await session.execute(
                select(Event)
                .where(Event.creator_id == user.id)
                .order_by(Event.date_time.desc())
            )
            events = events_result.scalars().all()
        
        if not events:
            await safe_edit_message(
                callback,
                "📝 У вас пока нет созданных мероприятий\n\n"
                "Используйте кнопку 'Создать мероприятие' для создания первого мероприятия.",
                reply_markup=get_back_keyboard("manage_events")
            )
            return
        
        await safe_edit_message(
            callback,
            f"📋 <b>Ваши мероприятия</b> ({len(events)}):",
            parse_mode="HTML",
            reply_markup=build_events_list_keyboard(events, "manage_event")
        )
        
    except Exception as e:
        logger.error(f"Ошибка получения мероприятий пользователя {callback.from_user.id}: {e}")
        await callback.answer("❌ Ошибка загрузки мероприятий", show_alert=True)

@router.callback_query(F.data == "broadcast")
async def show_broadcast_menu(callback: CallbackQuery):
    """Показать меню рассылки"""
    has_access, role = await check_admin_or_moderator(callback.from_user.id)
    
    if not has_access:
        await callback.answer("❌ У вас нет доступа", show_alert=True)
        return
    
    # Получаем статистику для рассылки
    user_stats = await get_user_stats()
    
    text = "📢 <b>Рассылка сообщений</b>\n\n"
    if user_stats:
        text += f"👥 Всего пользователей: {user_stats.get('total', 0)}\n"
        text += f"🏢 В Москве: {user_stats.get('moscow', 0)}\n"
        text += f"🕌 В Казани: {user_stats.get('kazan', 0)}\n\n"
    
    text += "Выберите целевую аудиторию:"
    
    await safe_edit_message(
        callback,
        text,
        parse_mode="HTML",
        reply_markup=get_broadcast_keyboard()
    )

# Остальные обработчики остаются без изменений, но с добавлением обработки ошибок...

@router.callback_query(F.data.startswith("manage_event_"))
async def show_event_management_details(callback: CallbackQuery):
    """Показать детали управления мероприятием"""
    try:
        event_id = int(callback.data.split("_")[2])
        
        async with async_session() as session:
            result = await session.execute(select(Event).where(Event.id == event_id))
            event = result.scalar_one_or_none()
            
            if not event:
                await callback.answer("❌ Мероприятие не найдено", show_alert=True)
                return
            
            # Проверяем права доступа
            user_result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
            user = user_result.scalar_one_or_none()
            
            if not user or (user.role not in ['admin', 'moderator'] and user.id != event.creator_id):
                await callback.answer("❌ У вас нет прав для управления этим мероприятием", show_alert=True)
                return
            
            # Считаем участников
            participants_result = await session.execute(
                select(EventRegistration).where(EventRegistration.event_id == event_id)
            )
            participants_count = len(participants_result.scalars().all())
        
        # Формируем текст с улучшенным форматированием
        now = datetime.now()
        is_past = event.date_time <= now
        
        event_text = f"📅 <b>{event.title}</b>\n"
        event_text += f"🆔 ID: {event.id}\n\n"
        
        event_text += f"📝 <b>Описание:</b> {event.description or 'Не указано'}\n"
        event_text += f"📍 <b>Место:</b> {event.location or 'Не указано'}\n"
        event_text += f"🏙️ <b>Город:</b> {event.city}\n"
        
        # Статус мероприятия
        if is_past:
            event_text += f"🕐 <b>Дата:</b> {event.date_time.strftime('%d.%m.%Y в %H:%M')} ⏰ <i>Прошло</i>\n"
        else:
            time_until = event.date_time - now
            if time_until.days > 0:
                event_text += f"🕐 <b>Дата:</b> {event.date_time.strftime('%d.%m.%Y в %H:%M')} (через {time_until.days} дн.)\n"
            elif time_until.seconds > 3600:
                hours = time_until.seconds // 3600
                event_text += f"🕐 <b>Дата:</b> {event.date_time.strftime('%d.%m.%Y в %H:%M')} (через {hours} ч.)\n"
            else:
                event_text += f"🕐 <b>Дата:</b> {event.date_time.strftime('%d.%m.%Y в %H:%M')} ⚡ <i>Скоро!</i>\n"
        
        # Участники
        if event.max_participants:
            percentage = (participants_count / event.max_participants) * 100
            event_text += f"👥 <b>Участники:</b> {participants_count}/{event.max_participants} ({percentage:.0f}%)\n"
        else:
            event_text += f"👥 <b>Участники:</b> {participants_count}\n"
        
        # Статусы
        if event.registration_required:
            status_icon = "🔓" if event.registration_open else "🔒"
            status_text = "открыта" if event.registration_open else "закрыта"
            event_text += f"{status_icon} <b>Регистрация:</b> {status_text}\n"
        else:
            event_text += "🆓 <b>Регистрация не требуется</b>\n"
        
        visibility_icon = "👁" if event.is_visible else "🙈"
        visibility_text = "видимо" if event.is_visible else "скрыто"
        event_text += f"{visibility_icon} <b>Видимость:</b> {visibility_text}\n"
        
        # Даты создания/обновления
        event_text += f"\n📅 <b>Создано:</b> {event.created_at.strftime('%d.%m.%Y в %H:%M')}\n"
        if event.updated_at and event.updated_at != event.created_at:
            event_text += f"✏️ <b>Обновлено:</b> {event.updated_at.strftime('%d.%m.%Y в %H:%M')}\n"
        
        # Клавиатура управления
        keyboard = []
        
        if not is_past:
            keyboard.extend([
                [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_event_{event_id}")],
                [
                    InlineKeyboardButton(
                        text="🙈 Скрыть" if event.is_visible else "👁 Показать", 
                        callback_data=f"toggle_visibility_{event_id}"
                    ),
                    InlineKeyboardButton(
                        text="🔒 Закрыть рег." if event.registration_open else "🔓 Открыть рег.", 
                        callback_data=f"toggle_registration_{event_id}"
                    )
                ]
            ])
        
        keyboard.extend([
            [InlineKeyboardButton(text="👥 Участники", callback_data=f"event_participants_{event_id}")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data=f"event_stats_{event_id}")],
            [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_event_{event_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="my_created_events")]
        ])
        
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
            await safe_edit_message(
                callback,
                event_text,
                parse_mode="HTML",
                reply_markup=markup
            )
            
    except Exception as e:
        logger.error(f"Ошибка отображения деталей мероприятия {callback.data}: {e}")
        await callback.answer("❌ Ошибка загрузки мероприятия", show_alert=True)

@router.callback_query(F.data.startswith("event_stats_"))
async def show_event_statistics(callback: CallbackQuery):
    """Показать статистику мероприятия"""
    try:
        event_id = int(callback.data.split("_")[2])
        
        async with async_session() as session:
            # Получаем мероприятие
            event_result = await session.execute(select(Event).where(Event.id == event_id))
            event = event_result.scalar_one_or_none()
            
            if not event:
                await callback.answer("❌ Мероприятие не найдено", show_alert=True)
                return
            
            # Получаем участников с деталями
            participants_result = await session.execute(
                select(User, EventRegistration)
                .join(EventRegistration)
                .where(EventRegistration.event_id == event_id)
                .order_by(EventRegistration.registered_at)
            )
            participants_data = participants_result.all()
            
            # Статистика по городам участников
            cities_stats = {}
            registration_dates = []
            
            for user, registration in participants_data:
                # По городам
                city = user.city or "Не указан"
                cities_stats[city] = cities_stats.get(city, 0) + 1
                
                # Даты регистрации
                registration_dates.append(registration.registered_at)
        
        # Формируем статистику
        stats_text = f"📊 <b>Статистика мероприятия</b>\n"
        stats_text += f"📅 <b>{event.title}</b>\n\n"
        
        total_participants = len(participants_data)
        stats_text += f"👥 <b>Всего участников:</b> {total_participants}\n"
        
        if event.max_participants:
            percentage = (total_participants / event.max_participants) * 100
            stats_text += f"📈 <b>Заполненность:</b> {percentage:.1f}%\n"
        
        # Статистика по городам
        if cities_stats:
            stats_text += f"\n🏙️ <b>По городам:</b>\n"
            for city, count in sorted(cities_stats.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / total_participants) * 100 if total_participants > 0 else 0
                stats_text += f"• {city}: {count} ({percentage:.1f}%)\n"
        
        # Динамика регистраций
        if registration_dates:
            first_reg = min(registration_dates)
            last_reg = max(registration_dates)
            stats_text += f"\n📅 <b>Регистрации:</b>\n"
            stats_text += f"• Первая: {first_reg.strftime('%d.%m.%Y в %H:%M')}\n"
            stats_text += f"• Последняя: {last_reg.strftime('%d.%m.%Y в %H:%M')}\n"
            
            # Регистрации за последние дни
            now = datetime.now()
            recent_24h = sum(1 for date in registration_dates if (now - date).days == 0)
            recent_7d = sum(1 for date in registration_dates if (now - date).days <= 7)
            
            if recent_24h > 0 or recent_7d > 0:
                stats_text += f"• За 24 часа: {recent_24h}\n"
                stats_text += f"• За 7 дней: {recent_7d}\n"
        
        # Прогноз до мероприятия
        if event.date_time > datetime.now() and total_participants > 0:
            days_until = (event.date_time - datetime.now()).days
            if days_until > 0:
                reg_days = (datetime.now() - min(registration_dates)).days if registration_dates else 1
                avg_per_day = total_participants / max(reg_days, 1)
                projected = total_participants + (avg_per_day * days_until)
                
                if event.max_participants:
                    projected = min(projected, event.max_participants)
                
                stats_text += f"\n🔮 <b>Прогноз участников:</b> ~{int(projected)}\n"
        
        keyboard = [
            [InlineKeyboardButton(text="👥 Список участников", callback_data=f"event_participants_{event_id}")],
            [InlineKeyboardButton(text="🔙 Назад к мероприятию", callback_data=f"manage_event_{event_id}")]
        ]
        
        await safe_edit_message(
            callback,
            stats_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка получения статистики мероприятия {callback.data}: {e}")
        await callback.answer("❌ Ошибка загрузки статистики", show_alert=True)

@router.callback_query(F.data.startswith("delete_event_"))
async def confirm_delete_event(callback: CallbackQuery):
    """Подтверждение удаления мероприятия"""
    try:
        event_id = int(callback.data.split("_")[2])
        
        async with async_session() as session:
            result = await session.execute(select(Event).where(Event.id == event_id))
            event = result.scalar_one_or_none()
            
            if not event:
                await callback.answer("❌ Мероприятие не найдено", show_alert=True)
                return
            
            # Считаем участников
            participants_result = await session.execute(
                select(func.count(EventRegistration.id)).where(EventRegistration.event_id == event_id)
            )
            participants_count = participants_result.scalar()
        
        warning_text = f"⚠️ <b>Подтверждение удаления</b>\n\n"
        warning_text += f"Вы действительно хотите удалить мероприятие?\n\n"
        warning_text += f"📅 <b>{event.title}</b>\n"
        warning_text += f"🕐 {event.date_time.strftime('%d.%m.%Y в %H:%M')}\n"
        warning_text += f"👥 Участников: {participants_count}\n\n"
        warning_text += f"❗️ <b>Это действие нельзя отменить!</b>\n"
        warning_text += f"Все регистрации будут удалены."
        
        await safe_edit_message(
            callback,
            warning_text,
            parse_mode="HTML",
            reply_markup=get_confirmation_keyboard("delete_event", event_id)
        )
        
    except Exception as e:
        logger.error(f"Ошибка подтверждения удаления мероприятия {callback.data}: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data.startswith("confirm_delete_event_"))
async def delete_event_confirmed(callback: CallbackQuery):
    """Удаление мероприятия"""
    try:
        event_id = int(callback.data.split("_")[3])
        
        async with async_session() as session:
            # Получаем мероприятие
            event_result = await session.execute(select(Event).where(Event.id == event_id))
            event = event_result.scalar_one_or_none()
            
            if not event:
                await callback.answer("❌ Мероприятие не найдено", show_alert=True)
                return
            
            event_title = event.title
            
            # Удаляем все регистрации
            registrations_result = await session.execute(
                select(EventRegistration).where(EventRegistration.event_id == event_id)
            )
            registrations = registrations_result.scalars().all()
            
            for reg in registrations:
                await session.delete(reg)
            
            # Удаляем мероприятие
            await session.delete(event)
            await session.commit()
        
        logger.info(f"Удалено мероприятие {event_id} '{event_title}' пользователем {callback.from_user.id}")
        
        await safe_edit_message(
            callback,
            f"✅ <b>Мероприятие удалено</b>\n\n"
            f"📅 {event_title}\n"
            f"🗑️ Удалено {len(registrations)} регистраций",
            parse_mode="HTML",
            reply_markup=get_back_keyboard("my_created_events")
        )
        
    except Exception as e:
        logger.error(f"Ошибка удаления мероприятия {callback.data}: {e}")
        await safe_edit_message(
            callback,
            "❌ Произошла ошибка при удалении мероприятия",
            reply_markup=get_back_keyboard("my_created_events")
        )

@router.callback_query(F.data.startswith("cancel_delete_event_"))
async def cancel_delete_event(callback: CallbackQuery):
    """Отмена удаления мероприятия"""
    event_id = int(callback.data.split("_")[3])
    # Создаем новый callback для возврата к мероприятию
    callback.data = f"manage_event_{event_id}"
    await show_event_management_details(callback)

@router.callback_query(F.data.startswith("toggle_visibility_"))
async def toggle_event_visibility(callback: CallbackQuery):
    """Переключение видимости мероприятия"""
    try:
        event_id = int(callback.data.split("_")[2])
        
        async with async_session() as session:
            result = await session.execute(select(Event).where(Event.id == event_id))
            event = result.scalar_one_or_none()
            
            if not event:
                await callback.answer("❌ Мероприятие не найдено", show_alert=True)
                return
            
            event.is_visible = not event.is_visible
            event.updated_at = datetime.now()
            await session.commit()
        
        status = "показано" if event.is_visible else "скрыто"
        icon = "👁" if event.is_visible else "🙈"
        await callback.answer(f"{icon} Мероприятие {status}")
        
        # Обновляем детали мероприятия
        callback.data = f"manage_event_{event_id}"
        await show_event_management_details(callback)
        
    except Exception as e:
        logger.error(f"Ошибка переключения видимости мероприятия {callback.data}: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data.startswith("toggle_registration_"))
async def toggle_event_registration(callback: CallbackQuery):
    """Переключение регистрации на мероприятие"""
    try:
        event_id = int(callback.data.split("_")[2])
        
        async with async_session() as session:
            result = await session.execute(select(Event).where(Event.id == event_id))
            event = result.scalar_one_or_none()
            
            if not event:
                await callback.answer("❌ Мероприятие не найдено", show_alert=True)
                return
            
            event.registration_open = not event.registration_open
            event.updated_at = datetime.now()
            await session.commit()
        
        status = "открыта" if event.registration_open else "закрыта"
        icon = "🔓" if event.registration_open else "🔒"
        await callback.answer(f"{icon} Регистрация {status}")
        
        # Обновляем детали мероприятия
        callback.data = f"manage_event_{event_id}"
        await show_event_management_details(callback)
        
    except Exception as e:
        logger.error(f"Ошибка переключения регистрации мероприятия {callback.data}: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data.startswith("event_participants_"))
async def show_event_participants(callback: CallbackQuery):
    """Показать участников мероприятия"""
    try:
        event_id = int(callback.data.split("_")[2])
        
        async with async_session() as session:
            # Получаем мероприятие
            event_result = await session.execute(select(Event).where(Event.id == event_id))
            event = event_result.scalar_one_or_none()
            
            if not event:
                await callback.answer("❌ Мероприятие не найдено", show_alert=True)
                return
            
            # Получаем участников с деталями регистрации
            participants_result = await session.execute(
                select(User, EventRegistration)
                .join(EventRegistration)
                .where(EventRegistration.event_id == event_id)
                .order_by(EventRegistration.registered_at)
            )
            participants_data = participants_result.all()
        
        if not participants_data:
            text = f"👥 <b>Участники мероприятия</b>\n"
            text += f"📅 <b>{event.title}</b>\n\n"
            text += "😔 Пока никто не записался"
        else:
            text = f"👥 <b>Участники мероприятия</b>\n"
            text += f"📅 <b>{event.title}</b>\n\n"
            
            for i, (participant, registration) in enumerate(participants_data, 1):
                name = participant.first_name or "Неизвестно"
                if participant.last_name:
                    name += f" {participant.last_name}"
                
                text += f"{i}. <b>{name}</b>"
                
                if participant.username:
                    text += f" (@{participant.username})"
                
                # Город участника
                if participant.city:
                    city_icon = "🏢" if participant.city == "Москва" else "🕌"
                    text += f" {city_icon}"
                
                # Дата регистрации
                reg_date = registration.registered_at.strftime('%d.%m')
                text += f" • {reg_date}"
                
                text += "\n"
            
            text += f"\n📊 <b>Всего участников:</b> {len(participants_data)}"
            if event.max_participants:
                percentage = (len(participants_data) / event.max_participants) * 100
                text += f"/{event.max_participants} ({percentage:.0f}%)"
        
        keyboard = [
            [InlineKeyboardButton(text="📊 Статистика", callback_data=f"event_stats_{event_id}")],
            [InlineKeyboardButton(text="🔙 Назад к мероприятию", callback_data=f"manage_event_{event_id}")]
        ]
        
        await safe_edit_message(
            callback,
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка получения участников мероприятия {callback.data}: {e}")
        await callback.answer("❌ Ошибка загрузки участников", show_alert=True)

@router.callback_query(F.data == "manage_moderators")
async def show_moderator_management(callback: CallbackQuery):
    """Управление модераторами (только для админов)"""
    if not await check_admin_only(callback.from_user.id):
        await callback.answer("❌ Доступно только администраторам", show_alert=True)
        return
    
    try:
        # Получаем список пользователей по ролям
        async with async_session() as session:
            admins_result = await session.execute(
                select(User).where(User.role == 'admin').order_by(User.first_name)
            )
            admins = admins_result.scalars().all()
            
            moderators_result = await session.execute(
                select(User).where(User.role == 'moderator').order_by(User.first_name)
            )
            moderators = moderators_result.scalars().all()
        
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
            [InlineKeyboardButton(text="📋 Список всех пользователей", callback_data="list_all_users")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
        ]
        
        await safe_edit_message(
            callback,
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка управления модераторами: {e}")
        await callback.answer("❌ Ошибка загрузки", show_alert=True)

@router.callback_query(F.data.in_(["add_admin", "add_moderator", "remove_moderator"]))
async def start_manage_admin_action(callback: CallbackQuery, state: FSMContext):
    """Начать действие с администраторами/модераторами"""
    if not await check_admin_only(callback.from_user.id):
        await callback.answer("❌ Доступно только администраторам", show_alert=True)
        return
    
    action = callback.data
    
    await state.set_state(ManageAdminStates.action)
    await state.update_data(action=action)
    await state.set_state(ManageAdminStates.user_id)
    
    action_text = {
        "add_admin": "добавления администратора",
        "add_moderator": "добавления модератора", 
        "remove_moderator": "удаления модератора"
    }
    
    await safe_edit_message(
        callback,
        f"🆔 <b>Управление ролями</b>\n\n"
        f"Для {action_text[action]} введите Telegram ID пользователя:\n\n"
        f"💡 <i>Чтобы узнать ID, пользователь может написать @userinfobot</i>\n"
        f"💡 <i>Или используйте кнопку 'Список пользователей' для поиска</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список пользователей", callback_data="list_all_users")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="manage_moderators")]
        ])
    )

@router.message(ManageAdminStates.user_id)
async def process_admin_user_id(message: Message, state: FSMContext):
    """Обработка ID пользователя для управления ролями"""
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите корректный числовой ID",
            reply_markup=get_back_keyboard("manage_moderators")
        )
        return
    
    data = await state.get_data()
    action = data['action']
    
    try:
        async with async_session() as session:
            # Находим пользователя по telegram_id
            result = await session.execute(select(User).where(User.telegram_id == user_id))
            user = result.scalar_one_or_none()
            
            if not user:
                await message.answer(
                    "❌ <b>Пользователь не найден</b>\n\n"
                    "Пользователь должен сначала запустить бота командой /start",
                    parse_mode="HTML",
                    reply_markup=get_back_keyboard("manage_moderators")
                )
                return
            
            # Проверяем, что не пытаемся изменить роль самого себя
            if user.telegram_id == message.from_user.id and action == "remove_moderator":
                await message.answer(
                    "❌ Нельзя удалить роль у самого себя",
                    reply_markup=get_back_keyboard("manage_moderators")
                )
                return
            
            # Выполняем действие
            old_role = user.role
            
            if action == "add_admin":
                if user.role == 'admin':
                    await message.answer(
                        f"❌ Пользователь <b>{user.first_name}</b> уже является администратором",
                        parse_mode="HTML",
                        reply_markup=get_back_keyboard("manage_moderators")
                    )
                    return
                user.role = 'admin'
                role_name = "администратором"
                role_icon = "👑"
            elif action == "add_moderator":
                if user.role in ['admin', 'moderator']:
                    await message.answer(
                        f"❌ Пользователь <b>{user.first_name}</b> уже является {user.role}",
                        parse_mode="HTML",
                        reply_markup=get_back_keyboard("manage_moderators")
                    )
                    return
                user.role = 'moderator'
                role_name = "модератором"
                role_icon = "🛡"
            elif action == "remove_moderator":
                if user.role != 'moderator':
                    await message.answer(
                        f"❌ Пользователь <b>{user.first_name}</b> не является модератором",
                        parse_mode="HTML",
                        reply_markup=get_back_keyboard("manage_moderators")
                    )
                    return
                user.role = 'user'
                role_name = "обычным пользователем"
                role_icon = "👤"
            
            await session.commit()
        
        user_name = user.first_name or "Неизвестно"
        if user.username:
            user_name += f" (@{user.username})"
        
        success_text = f"✅ <b>Роль изменена</b>\n\n"
        success_text += f"👤 <b>Пользователь:</b> {user_name}\n"
        success_text += f"🔄 <b>Было:</b> {old_role}\n"
        success_text += f"{role_icon} <b>Стало:</b> {user.role}\n"
        
        await message.answer(
            success_text,
            parse_mode="HTML",
            reply_markup=get_back_keyboard("manage_moderators")
        )
        
        logger.info(f"Роль пользователя {user.telegram_id} изменена с {old_role} на {user.role} администратором {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка изменения роли пользователя {user_id}: {e}")
        await message.answer(
            "❌ Произошла ошибка при изменении роли",
            reply_markup=get_back_keyboard("manage_moderators")
        )
    finally:
        await state.clear()

@router.callback_query(F.data == "list_all_users")
async def show_all_users_list(callback: CallbackQuery):
    """Показать список всех пользователей"""
    if not await check_admin_only(callback.from_user.id):
        await callback.answer("❌ Доступно только администраторам", show_alert=True)
        return
    
    try:
        async with async_session() as session:
            # Получаем всех пользователей
            result = await session.execute(
                select(User).order_by(User.role.desc(), User.first_name)
            )
            users = result.scalars().all()
        
        if not users:
            await safe_edit_message(
                callback,
                "📋 Список пользователей пуст",
                reply_markup=get_back_keyboard("manage_moderators")
            )
            return
        
        # Разбиваем на страницы (по 20 пользователей)
        page_size = 20
        total_pages = (len(users) + page_size - 1) // page_size
        
        # Показываем первую страницу
        await show_users_page(callback.message, users, 0, total_pages)
        
    except Exception as e:
        logger.error(f"Ошибка получения списка пользователей: {e}")
        await callback.answer("❌ Ошибка загрузки", show_alert=True)

async def show_users_page(message, users: list, page: int, total_pages: int):
    """Показать страницу пользователей"""
    page_size = 20
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(users))
    page_users = users[start_idx:end_idx]
    
    text = f"📋 <b>Список пользователей</b>\n"
    text += f"Страница {page + 1} из {total_pages} (всего: {len(users)})\n\n"
    
    role_icons = {
        'admin': '👑',
        'moderator': '🛡',
        'user': '👤'
    }
    
    for i, user in enumerate(page_users, start_idx + 1):
        name = user.first_name or "Неизвестно"
        if user.last_name:
            name += f" {user.last_name}"
        
        role_icon = role_icons.get(user.role, '👤')
        
        text += f"{i}. {role_icon} <b>{name}</b>"
        
        if user.username:
            text += f" (@{user.username})"
        
        text += f"\n   ID: <code>{user.telegram_id}</code>"
        
        if user.city:
            city_icon = "🏢" if user.city == "Москва" else "🕌"
            text += f" {city_icon} {user.city}"
        
        text += f" • {user.created_at.strftime('%d.%m.%Y')}\n"
    
    # Клавиатура навигации
    keyboard = []
    
    # Навигация по страницам
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"users_page_{page-1}"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"users_page_{page+1}"))
        if nav_row:
            keyboard.append(nav_row)
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад к управлению", callback_data="manage_moderators")])
    
    await message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@router.callback_query(F.data.startswith("users_page_"))
async def navigate_users_page(callback: CallbackQuery):
    """Навигация по страницам пользователей"""
    if not await check_admin_only(callback.from_user.id):
        await callback.answer("❌ Доступно только администраторам", show_alert=True)
        return
    
    try:
        page = int(callback.data.split("_")[2])
        
        async with async_session() as session:
            result = await session.execute(
                select(User).order_by(User.role.desc(), User.first_name)
            )
            users = result.scalars().all()
        
        page_size = 20
        total_pages = (len(users) + page_size - 1) // page_size
        
        await show_users_page(callback.message, users, page, total_pages)
        
    except Exception as e:
        logger.error(f"Ошибка навигации по пользователям: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data.startswith("broadcast_"))
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    """Начать процесс рассылки"""
    has_access, role = await check_admin_or_moderator(callback.from_user.id)
    
    if not has_access:
        await callback.answer("❌ У вас нет доступа", show_alert=True)
        return
    
    target = callback.data.split("_")[1]
    
    target_names = {
        "all": "всем пользователям",
        "moscow": "пользователям из Москвы",
        "kazan": "пользователям из Казани",
        "event": "участникам мероприятия"
    }
    
    await state.set_state(BroadcastStates.target)
    await state.update_data(target=target)
    await state.set_state(BroadcastStates.message_text)
    
    await safe_edit_message(
        callback,
        f"📢 <b>Рассылка {target_names.get(target, 'выбранной группе')}</b>\n\n"
        f"Введите текст сообщения для рассылки:\n\n"
        f"💡 <i>Поддерживается HTML разметка</i>\n"
        f"💡 <i>Максимум 4000 символов</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="broadcast")]
        ])
    )

@router.message(BroadcastStates.message_text)
async def process_broadcast_message(message: Message, state: FSMContext):
    """Обработка текста рассылки"""
    if len(message.text) > 4000:
        await message.answer(
            "❌ Текст слишком длинный (максимум 4000 символов)",
            reply_markup=get_back_keyboard("broadcast")
        )
        return
    
    data = await state.get_data()
    target = data['target']
    
    await state.update_data(message_text=message.text)
    
    # Получаем количество получателей
    try:
        async with async_session() as session:
            if target == "all":
                result = await session.execute(select(func.count(User.id)))
            elif target == "moscow":
                result = await session.execute(
                    select(func.count(User.id)).where(User.city == "Москва")
                )
            elif target == "kazan":
                result = await session.execute(
                    select(func.count(User.id)).where(User.city == "Казань")
                )
            else:
                result = await session.execute(select(func.count(User.id)))
            
            recipients_count = result.scalar()
    except Exception as e:
        logger.error(f"Ошибка подсчета получателей рассылки: {e}")
        recipients_count = "неизвестно"
    
    target_names = {
        "all": "всем пользователям",
        "moscow": "пользователям из Москвы",
        "kazan": "пользователям из Казани",
        "event": "участникам мероприятия"
    }
    
    preview_text = message.text[:200] + "..." if len(message.text) > 200 else message.text
    
    confirmation_text = f"📢 <b>Подтверждение рассылки</b>\n\n"
    confirmation_text += f"🎯 <b>Получатели:</b> {target_names.get(target)}\n"
    confirmation_text += f"👥 <b>Количество:</b> {recipients_count}\n\n"
    confirmation_text += f"📝 <b>Предварительный просмотр:</b>\n"
    confirmation_text += f"<i>{preview_text}</i>\n\n"
    confirmation_text += f"❓ Отправить рассылку?"
    
    keyboard = [
        [InlineKeyboardButton(text="✅ Отправить", callback_data="confirm_broadcast")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="broadcast")]
    ]
    
    await message.answer(
        confirmation_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@router.callback_query(F.data == "confirm_broadcast")
async def execute_broadcast(callback: CallbackQuery, state: FSMContext):
    """Выполнить рассылку"""
    has_access, role = await check_admin_or_moderator(callback.from_user.id)
    
    if not has_access:
        await callback.answer("❌ У вас нет доступа", show_alert=True)
        return
    
    data = await state.get_data()
    target = data['target']
    message_text = data['message_text']
    
    await safe_edit_message(
        callback,
        "📤 <b>Рассылка запущена...</b>\n\n"
        "Подождите, это может занять некоторое время.",
        parse_mode="HTML"
    )
    
    try:
        async with async_session() as session:
            # Получаем получателей
            if target == "all":
                result = await session.execute(select(User))
            elif target == "moscow":
                result = await session.execute(select(User).where(User.city == "Москва"))
            elif target == "kazan":
                result = await session.execute(select(User).where(User.city == "Казань"))
            else:
                result = await session.execute(select(User))
            
            recipients = result.scalars().all()
        
        # Выполняем рассылку
        success_count = 0
        error_count = 0
        
        for user in recipients:
            try:
                await callback.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"📢 <b>Рассылка от администрации</b>\n\n{message_text}",
                    parse_mode="HTML"
                )
                success_count += 1
                
                # Небольшая задержка для избежания лимитов
                if success_count % 30 == 0:
                    await asyncio.sleep(1)
                    
            except Exception as e:
                error_count += 1
                logger.warning(f"Не удалось отправить сообщение пользователю {user.telegram_id}: {e}")
        
        result_text = f"✅ <b>Рассылка завершена</b>\n\n"
        result_text += f"📤 Отправлено: {success_count}\n"
        if error_count > 0:
            result_text += f"❌ Ошибок: {error_count}\n"
        result_text += f"👥 Всего получателей: {len(recipients)}"
        
        await safe_edit_message(
            callback,
            result_text,
            parse_mode="HTML",
            reply_markup=get_back_keyboard("broadcast")
        )
        
        logger.info(f"Рассылка выполнена пользователем {callback.from_user.id}: {success_count} успешно, {error_count} ошибок")
        
    except Exception as e:
        logger.error(f"Ошибка выполнения рассылки: {e}")
        await safe_edit_message(
            callback,
            "❌ Произошла ошибка при выполнении рассылки",
            reply_markup=get_back_keyboard("broadcast")
        )
    finally:
        await state.clear()

@router.callback_query(F.data == "user_questions")
async def show_user_questions(callback: CallbackQuery):
    """Показать вопросы пользователей"""
    has_access, role = await check_admin_or_moderator(callback.from_user.id)
    
    if not has_access:
        await callback.answer("❌ У вас нет доступа", show_alert=True)
        return
    
    # TODO: Реализовать работу с вопросами когда будет готова таблица questions
    await safe_edit_message(
        callback,
        "❓ <b>Вопросы пользователей</b>\n\n"
        "🚧 Функция вопросов пользователей будет реализована в следующих версиях.\n\n"
        "Планируемые возможности:\n"
        "• Просмотр всех вопросов\n"
        "• Ответы на вопросы\n"
        "• Уведомления о новых вопросах\n"
        "• Статистика по вопросам",
        parse_mode="HTML",
        reply_markup=get_back_keyboard("admin_panel")
    )
    
    try:
        field_names = {
            'title': 'Название',
            'description': 'Описание',
            'location': 'Место',
            'city': 'Город',
            'datetime': 'Дата и время',
            'limit': 'Лимит участников'
        }
        
        new_display_value = new_value
        if field == 'description' and new_value == '-':
            new_display_value = "Удалено"
        elif field == 'location' and new_value == '-':
            new_display_value = "Удалено"
        elif field == 'limit' and new_value == '-':
            new_display_value = "Неограниченно"
        elif field == 'datetime':
            new_display_value = datetime_obj.strftime('%d.%m.%Y в %H:%M')
        
        success_text = f"✅ <b>Поле обновлено</b>\n\n"
        success_text += f"📅 <b>Мероприятие:</b> {event.title}\n"
        success_text += f"🔧 <b>Поле:</b> {field_names.get(field)}\n"
        success_text += f"📝 <b>Было:</b> {old_value}\n"
        success_text += f"✨ <b>Стало:</b> {new_display_value}"
        
        await message.answer(
            success_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Продолжить редактирование", callback_data=f"edit_event_{event_id}")],
                [InlineKeyboardButton(text="📋 К мероприятию", callback_data=f"manage_event_{event_id}")]
            ])
        )
        
        logger.info(f"Мероприятие {event_id} отредактировано пользователем {message.from_user.id}: {field} = {new_value}")
        
    except Exception as e:
        logger.error(f"Ошибка редактирования мероприятия: {e}")
        await message.answer(
            "❌ Произошла ошибка при редактировании",
            reply_markup=get_back_keyboard(f"manage_event_{event_id}")
        )
    finally:
        await state.clear()

# Добавляем обработчик просмотра всех мероприятий для админов
@router.callback_query(F.data == "all_events_manage")
async def show_all_events_for_management(callback: CallbackQuery):
    """Показать все мероприятия для управления (админы/модераторы)"""
    has_access, role = await check_admin_or_moderator(callback.from_user.id)
    
    if not has_access:
        await callback.answer("❌ У вас нет доступа", show_alert=True)
        return
    
    try:
        async with async_session() as session:
            # Получаем все мероприятия
            result = await session.execute(
                select(Event).order_by(Event.date_time.desc())
            )
            events = result.scalars().all()
        
        if not events:
            await safe_edit_message(
                callback,
                "📅 <b>Все мероприятия</b>\n\n"
                "Пока нет созданных мероприятий",
                parse_mode="HTML",
                reply_markup=get_back_keyboard("manage_events")
            )
            return
        
        # Разделяем на предстоящие и прошедшие
        now = datetime.now()
        upcoming = [e for e in events if e.date_time > now]
        past = [e for e in events if e.date_time <= now]
        
        text = f"📅 <b>Все мероприятия</b>\n\n"
        text += f"🔜 Предстоящих: {len(upcoming)}\n"
        text += f"✅ Прошедших: {len(past)}\n"
        text += f"📊 Всего: {len(events)}\n\n"
        text += "Выберите мероприятие:"
        
        await safe_edit_message(
            callback,
            text,
            parse_mode="HTML",
            reply_markup=build_events_list_keyboard(events, "manage_event")
        )
        
    except Exception as e:
        logger.error(f"Ошибка загрузки всех мероприятий: {e}")
        await callback.answer("❌ Ошибка загрузки", show_alert=True)

# Обработчик для экспорта данных (дополнительная функция)
@router.callback_query(F.data == "export_data")
async def export_data_menu(callback: CallbackQuery):
    """Меню экспорта данных"""
    if not await check_admin_only(callback.from_user.id):
        await callback.answer("❌ Доступно только администраторам", show_alert=True)
        return
    
    keyboard = [
        [InlineKeyboardButton(text="📊 Статистика участников", callback_data="export_participants")],
        [InlineKeyboardButton(text="📅 Отчет по мероприятиям", callback_data="export_events")],
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="export_users")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ]
    
    await safe_edit_message(
        callback,
        "📋 <b>Экспорт данных</b>\n\n"
        "Выберите тип отчета:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@router.callback_query(F.data.startswith("export_"))
async def generate_export(callback: CallbackQuery):
    """Генерация экспорта данных"""
    if not await check_admin_only(callback.from_user.id):
        await callback.answer("❌ Доступно только администраторам", show_alert=True)
        return
    
    export_type = callback.data.split("_")[1]
    
    await safe_edit_message(
        callback,
        "📊 <b>Генерация отчета...</b>\n\n"
        "Подождите, это может занять некоторое время.",
        parse_mode="HTML"
    )
    
    try:
        async with async_session() as session:
            if export_type == "participants":
                # Статистика участников
                result = await session.execute(
                    select(Event, func.count(EventRegistration.id).label('participants_count'))
                    .outerjoin(EventRegistration)
                    .group_by(Event.id)
                    .order_by(Event.date_time.desc())
                )
                events_data = result.all()
                
                report = "📊 <b>Статистика участников по мероприятиям</b>\n\n"
                
                total_events = len(events_data)
                total_registrations = sum(data.participants_count for data in events_data)
                
                report += f"📈 <b>Общая статистика:</b>\n"
                report += f"• Всего мероприятий: {total_events}\n"
                report += f"• Всего регистраций: {total_registrations}\n"
                report += f"• Среднее на мероприятие: {total_registrations/total_events:.1f}\n\n"
                
                report += f"📅 <b>По мероприятиям:</b>\n"
                for event, count in events_data[:10]:  # Показываем топ 10
                    status = "🔜" if event.date_time > datetime.now() else "✅"
                    report += f"{status} {event.title[:30]}...\n"
                    report += f"   👥 {count} участников • {event.date_time.strftime('%d.%m.%Y')}\n"
                
                if len(events_data) > 10:
                    report += f"\n... и еще {len(events_data) - 10} мероприятий"
                
            elif export_type == "events":
                # Отчет по мероприятиям
                events_result = await session.execute(select(Event).order_by(Event.date_time.desc()))
                events = events_result.scalars().all()
                
                now = datetime.now()
                upcoming = [e for e in events if e.date_time > now and e.is_visible]
                past = [e for e in events if e.date_time <= now]
                hidden = [e for e in events if not e.is_visible]
                
                report = "📅 <b>Отчет по мероприятиям</b>\n\n"
                report += f"📊 <b>Общая статистика:</b>\n"
                report += f"• Всего мероприятий: {len(events)}\n"
                report += f"• Предстоящих: {len(upcoming)}\n"
                report += f"• Прошедших: {len(past)}\n"
                report += f"• Скрытых: {len(hidden)}\n\n"
                
                # Статистика по городам
                moscow_events = [e for e in events if e.city == "Москва"]
                kazan_events = [e for e in events if e.city == "Казань"]
                
                report += f"🏙️ <b>По городам:</b>\n"
                report += f"• Москва: {len(moscow_events)}\n"
                report += f"• Казань: {len(kazan_events)}\n\n"
                
                # Ближайшие мероприятия
                if upcoming:
                    report += f"🔜 <b>Ближайшие мероприятия:</b>\n"
                    for event in upcoming[:5]:
                        days_until = (event.date_time - now).days
                        report += f"• {event.title[:25]}...\n"
                        report += f"  📅 {event.date_time.strftime('%d.%m.%Y')} (через {days_until} дн.)\n"
                
            elif export_type == "users":
                # Список пользователей
                users_result = await session.execute(
                    select(User).order_by(User.created_at.desc())
                )
                users = users_result.scalars().all()
                
                admins = [u for u in users if u.role == 'admin']
                moderators = [u for u in users if u.role == 'moderator']
                regular_users = [u for u in users if u.role == 'user']
                
                moscow_users = [u for u in users if u.city == "Москва"]
                kazan_users = [u for u in users if u.city == "Казань"]
                no_city_users = [u for u in users if not u.city]
                
                report = "👥 <b>Отчет по пользователям</b>\n\n"
                report += f"📊 <b>Общая статистика:</b>\n"
                report += f"• Всего пользователей: {len(users)}\n"
                report += f"• Администраторов: {len(admins)}\n"
                report += f"• Модераторов: {len(moderators)}\n"
                report += f"• Пользователей: {len(regular_users)}\n\n"
                
                report += f"🏙️ <b>По городам:</b>\n"
                report += f"• Москва: {len(moscow_users)}\n"
                report += f"• Казань: {len(kazan_users)}\n"
                report += f"• Без города: {len(no_city_users)}\n\n"
                
                # Последние регистрации
                recent_users = users[:10]
                report += f"🆕 <b>Последние регистрации:</b>\n"
                for user in recent_users:
                    name = user.first_name or "Неизвестно"
                    date = user.created_at.strftime('%d.%m.%Y')
                    report += f"• {name} • {date}\n"
        
        await safe_edit_message(
            callback,
            report,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"export_{export_type}")],
                [InlineKeyboardButton(text="🔙 Назад к экспорту", callback_data="export_data")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка генерации экспорта {export_type}: {e}")
        await safe_edit_message(
            callback,
            "❌ Произошла ошибка при генерации отчета",
            reply_markup=get_back_keyboard("export_data")
        )

# Обработчики отмены для всех состояний
@router.callback_query(F.data == "admin_panel")
async def cancel_any_state(callback: CallbackQuery, state: FSMContext):
    """Отмена любого состояния и возврат в админ панель"""
    await state.clear()
    await show_admin_panel_callback(callback)

@router.message(F.text == "❌ Отменить")
async def cancel_state_message(message: Message, state: FSMContext):
    """Отмена состояния через сообщение"""
    await state.clear()
    await message.answer(
        "❌ Операция отменена",
        reply_markup=get_back_keyboard("admin_panel")
    )

# Обработчик ошибок для всех admin функций
@router.callback_query(F.data.startswith("error_"))
async def handle_admin_error(callback: CallbackQuery):
    """Обработчик ошибок в админ панели"""
    await callback.answer("❌ Произошла ошибка. Попробуйте позже.", show_alert=True)
    await show_admin_panel_callback(callback)