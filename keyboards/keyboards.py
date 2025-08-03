from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_main_menu(role: str = 'user'):
    """Главное меню в зависимости от роли пользователя"""
    keyboard = [
        [KeyboardButton(text="📅 Мероприятия")],
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🏙️ Выбрать город")],
        [KeyboardButton(text="💰 Донат"), KeyboardButton(text="❓ Задать вопрос")],
    ]
    
    if role in ['moderator', 'admin']:
        keyboard.insert(2, [KeyboardButton(text="⚙️ Панель управления")])
    
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_cities_keyboard():
    """Клавиатура выбора города"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏢 Москва", callback_data="city_moscow")],
        [InlineKeyboardButton(text="🕌 Казань", callback_data="city_kazan")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    return keyboard

def get_events_keyboard(user_city: str = None):
    """Клавиатура мероприятий"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои мероприятия", callback_data="my_events")],
        [InlineKeyboardButton(text="🆕 Все мероприятия", callback_data="all_events")],
    ])
    
    if user_city:
        keyboard.inline_keyboard.insert(0, 
            [InlineKeyboardButton(text=f"📍 Мероприятия в городе {user_city}", callback_data=f"events_city_{user_city.lower()}")]
        )
    
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])
    return keyboard

def get_admin_panel_keyboard(role: str):
    """Административная панель"""
    keyboard = [
        [InlineKeyboardButton(text="➕ Создать мероприятие", callback_data="create_event")],
        [InlineKeyboardButton(text="📝 Управление мероприятиями", callback_data="manage_events")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast")],
        [InlineKeyboardButton(text="❓ Вопросы пользователей", callback_data="user_questions")],
    ]
    
    if role == 'admin':
        keyboard.append([InlineKeyboardButton(text="👥 Управление ролями", callback_data="manage_moderators")])  # Изменил текст
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_event_actions_keyboard(event_id: int, is_registered: bool = False, is_creator: bool = False):
    """Клавиатура действий с мероприятием"""
    keyboard = []
    
    if not is_registered:
        keyboard.append([InlineKeyboardButton(text="✅ Записаться", callback_data=f"register_{event_id}")])
    else:
        keyboard.append([InlineKeyboardButton(text="❌ Отписаться", callback_data=f"unregister_{event_id}")])
    
    if is_creator:
        keyboard.extend([
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_event_{event_id}")],
            [InlineKeyboardButton(text="👥 Участники", callback_data=f"event_participants_{event_id}")],
            [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_event_{event_id}")],
        ])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_events")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_event_management_keyboard():
    """Клавиатура управления мероприятиями"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои мероприятия", callback_data="my_created_events")],
        [InlineKeyboardButton(text="📊 Все мероприятия", callback_data="all_events_manage")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    return keyboard

def get_broadcast_keyboard():
    """Клавиатура для рассылки"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Всем пользователям", callback_data="broadcast_all")],
        [InlineKeyboardButton(text="🏢 По Москве", callback_data="broadcast_moscow")],
        [InlineKeyboardButton(text="🕌 По Казани", callback_data="broadcast_kazan")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    return keyboard

def get_schedule_keyboard():
    """Клавиатура выбора времени отправки"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Отправить сейчас", callback_data="schedule_now")],
        [InlineKeyboardButton(text="⏰ Запланировать", callback_data="schedule_later")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="broadcast")]
    ])
    return keyboard

def get_confirmation_keyboard(action: str, item_id: int = None):
    """Клавиатура подтверждения действия"""
    callback_confirm = f"confirm_{action}_{item_id}" if item_id else f"confirm_{action}"
    callback_cancel = f"cancel_{action}_{item_id}" if item_id else f"cancel_{action}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=callback_confirm),
            InlineKeyboardButton(text="❌ Нет", callback_data=callback_cancel)
        ]
    ])
    return keyboard

def get_back_keyboard(callback_data: str = "back_to_menu"):
    """Простая клавиатура "Назад" """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data)]
    ])
    return keyboard

def build_events_list_keyboard(events: list, prefix: str = "event"):
    """Построение клавиатуры со списком мероприятий"""
    builder = InlineKeyboardBuilder()
    
    for event in events:
        builder.add(InlineKeyboardButton(
            text=f"📅 {event.title} - {event.date_time.strftime('%d.%m.%Y')}",
            callback_data=f"{prefix}_{event.id}"
        ))
    
    builder.adjust(1)  # По одной кнопке в ряд
    
    # Разные кнопки "Назад" в зависимости от префикса
    if prefix == "manage_event":
        back_callback = "my_created_events"
    else:
        back_callback = "back_to_events"
    
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data=back_callback))
    
    return builder.as_markup()

def get_cancel_keyboard():
    """Клавиатура отмены"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data="admin_panel")]
    ])
    return keyboard

def get_next_event_keyboard(event_id: int = None, show_all: bool = True):
    """Клавиатура для ближайшего мероприятия"""
    keyboard = []
    
    if event_id:
        keyboard.append([InlineKeyboardButton(text="📝 Подробнее", callback_data=f"event_{event_id}")])
    
    if show_all:
        keyboard.append([InlineKeyboardButton(text="📅 Все мероприятия", callback_data="all_events")])
    
    keyboard.extend([
        [InlineKeyboardButton(text="👤 Профиль", callback_data="show_profile")],
        [InlineKeyboardButton(text="🏙️ Выбрать город", callback_data="select_city_inline")],
        [InlineKeyboardButton(text="📋 Меню", callback_data="show_main_menu")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_no_events_keyboard():
    """Клавиатура когда нет мероприятий"""
    keyboard = [
        [InlineKeyboardButton(text="👤 Профиль", callback_data="show_profile")],
        [InlineKeyboardButton(text="🏙️ Выбрать город", callback_data="select_city_inline")],
        [InlineKeyboardButton(text="📋 Меню", callback_data="show_main_menu")]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)