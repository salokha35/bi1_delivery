from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from api import authenticate_user, get_order_by_id, create_otp, verify_otp, APIError
from storage import save_token, get_token, delete_token
import re
from typing import Dict, Any
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Conversation states
ASK_EMAIL, ASK_PASSWORD, ASK_ORDER_ID, WAITING_FOR_OTP = range(4)

def escape_markdown(text: str) -> str:
    """Escape special characters for Telegram markdown."""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    return ''.join('\\' + char if char in special_chars else char for char in str(text))

def format_order_details(order_data: Dict[str, Any]) -> str:
    """Format order details into a readable message with graceful handling of missing fields."""
    try:
        data = order_data.get('data', {})
        items = data.get('items', [])
        
        # Format items list with safe field access
        items_text = ""
        for item in items:
            quantity = item.get('additional', {}).get('quantity', 0)
            name = item.get('name', 'Unknown Item')
            formatted_price = item.get('formatted_price', 'N/A')
            formatted_total = item.get('formatted_total', 'N/A')
            
            items_text += (
                f"\n  • {escape_markdown(name)}\n"
                f"    Quantity: {escape_markdown(str(quantity))}\n"
                f"    Price: {escape_markdown(formatted_price)}\n"
                f"    Total: {escape_markdown(formatted_total)}"
            )

        # Safe access to all fields with default values
        order_id = data.get('id', 'N/A')
        state = data.get('status', 'Unknown')
        created_at = data.get('created_at', 'N/A')
        currency = data.get('order_currency_code', 'N/A')
        sub_total = data.get('formatted_sub_total', '0.00')
        shipping = data.get('formatted_shipping_amount', '0.00')
        tax = data.get('formatted_tax_amount', '0.00')
        discount = data.get('formatted_discount_amount', '0.00')
        grand_total = data.get('formatted_grand_total', '0.00')
        total_qty = data.get('total_qty', 0)
        email_sent = 'Yes' if data.get('email_sent') == 1 else 'No'

        return (
            f"📦 *Order \\#{escape_markdown(str(order_id))}*\n\n"
            f"*Status:* `{escape_markdown(state)}`\n"
            f"*Date:* `{escape_markdown(created_at)}`\n"
            f"*Currency:* {escape_markdown(currency)}\n\n"
            f"💰 *Order Summary*\n"
            f"Subtotal: `{escape_markdown(sub_total)}`\n"
            f"Shipping: `{escape_markdown(shipping)}`\n"
            f"Tax: `{escape_markdown(tax)}`\n"
            f"Discount: `{escape_markdown(discount)}`\n"
            f"*Total: `{escape_markdown(grand_total)}`*\n\n"
            f"🛍️ *Items:*{items_text}\n\n"
            f"📊 *Additional Info*\n"
            f"Total Items: {escape_markdown(str(total_qty))}\n"
            f"Email Sent: {email_sent}"
        )
    except Exception as e:
        logger.error(f"Ошибка форматирования деталей заказа: {e}")
        logger.debug(f"Полученные данные заказа: {order_data}")  # Log the received data for debugging
        return f"Ошибка форматирования заказа {order_data.get('data', {}).get('id', 'N/A')}: {str(e)}"

def is_valid_email(email: str) -> bool:
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    is_valid = bool(re.match(pattern, email))
    logger.debug(f"Валидация электронной почты для {email}: {'действительная' if is_valid else 'недействительная'}")
    return is_valid

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask for email."""
    user = update.effective_user
    logger.info(f"Новая беседа начата пользователем {user.id} (@{user.username})")
    
    # Check if user already has a valid token
    token = await get_token(user.id)
    if token:
        logger.info(f"User {user.id} already has a valid token")
        await update.message.reply_text(
            "✅ Вы уже авторизованы!\n\n"
            "Вы можете:\n"
            "1. Отправить мне номер заказа для получения деталей заказа\n"
            "2. Использовать /logout для завершения сессии\n"
            "3. Использовать /cancel для отмены текущей операции\n\n"
            "Пожалуйста, введите номер заказа:"
        )
        return ASK_ORDER_ID
    
    # Clear any existing user data if not logged in
    context.user_data.clear()
    
    await update.message.reply_text(
        "👋 Добро пожаловать в бот управления заказами!\n\n"
        "Пожалуйста, введите ваш адрес электронной почты для начала:"
    )
    return ASK_EMAIL

async def ask_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle email input and ask for password."""
    user = update.effective_user
    email = update.message.text.strip()
    logger.info(f"Email введен пользователем {user.id}: {email}")
    
    if not is_valid_email(email):
        logger.warning(f"Неверный формат электронной почты от пользователя {user.id}: {email}")
        await update.message.reply_text(
            "❌ Неверный формат электронной почты. Пожалуйста, введите действительный адрес электронной почты:"
        )
        return ASK_EMAIL
    
    context.user_data['email'] = email
    logger.info(f"Действительный адрес электронной почты сохранен для пользователя {user.id}")
    await update.message.reply_text(
        "📧 Email принят!\n"
        "Пожалуйста, введите ваш пароль:"
    )
    return ASK_PASSWORD

async def ask_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle password input and attempt authentication."""
    user = update.effective_user
    logger.info(f"Пароль введен пользователем {user.id}")
    
    # Delete password message for security
    await update.message.delete()
    
    try:
        email = context.user_data['email']
        logger.debug(f"Попытка аутентификации для пользователя {user.id} с электронной почтой {email}")
        
        token = await authenticate_user(email, update.message.text)
        await save_token(user.id, token)
        context.user_data['authenticated'] = True  # Mark user as authenticated
        logger.info(f"Пользователь {user.id} успешно аутентифицирован")
        
        await update.message.reply_text(
            "✅ Успешная аутентификация!\n\n"
            "Вы можете теперь:\n"
            "1. Отправить мне номер заказа для получения деталей заказа\n"
            "2. Использовать /logout для завершения сессии\n"
            "3. Использовать /cancel для отмены текущей операции\n\n"
            "Пожалуйста, введите номер заказа:"
        )
        return ASK_ORDER_ID
        
    except APIError as e:
        logger.error(f"Authentication failed for user {user.id}: {e.message}")
        context.user_data.clear()  # Clear data on authentication failure
        await update.message.reply_text(
            f"❌ Не удалось пройти аутентификацию: {e.message}\n"
            "Пожалуйста, попробуйте снова с помощью /start"
        )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Unexpected error during authentication for user {user.id}: {str(e)}")
        context.user_data.clear()  # Clear data on error
        await update.message.reply_text(
            "❌ Произошла непредвиденная ошибка. Пожалуйста, попробуйте снова с помощью /start"
        )
        return ConversationHandler.END

async def ask_order_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle order ID input and return order details."""
    user = update.effective_user
    order_id = update.message.text.strip()
    logger.info(f"Запрос номера заказа от пользователя {user.id}: {order_id}")
    
    try:
        # Verify authentication
        token = await get_token(user.id)
        if not token:
            logger.warning(f"Не удалось найти токен для пользователя {user.id}")
            context.user_data.clear()
            await update.message.reply_text(
                "⚠️ Ваша сессия истекла. Пожалуйста, авторизуйтесь снова с помощью /start"
            )
            return ConversationHandler.END

        logger.debug(f"Получение заказа {order_id} для пользователя {user.id}")
        order_data = await get_order_by_id(order_id, token)
        
        # Extract customer phone from order data
        customer_phone = order_data.get('data', {}).get('customer', {}).get('phone')
        if not customer_phone:
            logger.error(f"Не удалось найти номер телефона клиента в деталях заказа {order_id}")
            await update.message.reply_text(
                "❌ Не удалось найти номер телефона клиента в деталях заказа."
            )
            return ASK_ORDER_ID

        # Store order details and phone in context for OTP verification
        context.user_data['current_order'] = order_data
        context.user_data['customer_phone'] = customer_phone
        
        # Send formatted order details
        formatted_message = format_order_details(order_data)
        await update.message.reply_text(
            formatted_message,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
        # Create OTP
        try:
            await create_otp(customer_phone)
            await update.message.reply_text(
                f"📱 На номер телефона клиента отправлен одноразовый код (OTP).\n"
                f"Пожалуйста, введите одноразовый код:"
            )
            return WAITING_FOR_OTP
            
        except APIError as e:
            logger.error(f"Не удалось сгенерировать одноразовый код (OTP) для номера телефона {customer_phone}: {e.message}")
            await update.message.reply_text(
                f"❌ Не удалось отправить одноразовый код: {e.message}\n"
                "Пожалуйста, попробуйте другой номер заказа:"
            )
            return ASK_ORDER_ID
            
    except APIError as e:
        if e.status in [401, 403]:
            logger.warning(f"Токен истек для пользователя {user.id}")
            context.user_data.clear()
            await update.message.reply_text(
                "⚠️ Ваша сессия истекла. Пожалуйста, авторизуйтесь снова с помощью /start"
            )
            return ConversationHandler.END
        else:
            logger.error(f"Ошибка API при получении заказа {order_id} для пользователя {user.id}: {e.message}")
            await update.message.reply_text(
                f"❌ Ошибка при получении заказа: {e.message}\n"
                "Пожалуйста, попробуйте другой номер заказа:"
            )
            return ASK_ORDER_ID
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при получении заказа {order_id} для пользователя {user.id}: {str(e)}")
        await update.message.reply_text(
            "❌ Произошла непредвиденная ошибка. Пожалуйста, попробуйте другой номер заказа:"
        )
        return ASK_ORDER_ID

async def handle_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle OTP verification."""
    user = update.effective_user
    otp = update.message.text.strip()
    
    # Delete OTP message for security
    await update.message.delete()
    
    try:
        customer_phone = context.user_data.get('customer_phone')
        if not customer_phone:
            logger.error(f"Номер телефона пользователя не найден. {user.id}")
            await update.message.reply_text(
                "❌ Ошибка сессии. Пожалуйста, попробуйте снова с новым номером заказа:"
            )
            return ASK_ORDER_ID

        # Verify OTP
        try:
            await verify_otp(customer_phone, otp)
            await update.message.reply_text(
                "✅Подтверждение кода прошло успешно!\n\n"
                "Введите другой номер заказа:"
            )
            return ASK_ORDER_ID
            
        except APIError as e:
            logger.error(f"Не удалось проверить одноразовый код (OTP) для номера телефона {customer_phone}: {e.message}")
            await update.message.reply_text(
                f"❌ Неверный одноразовый код: {e.message}\n"
                "Пожалуйста, попробуйте снова с правильным одноразовым кодом:"
            )
            return WAITING_FOR_OTP
            
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при проверке одноразового кода (OTP) для пользователя {user.id}: {str(e)}")
        await update.message.reply_text(
            "❌ Произошла непредвиденная ошибка. Пожалуйста, попробуйте снова с новым номером заказа:"
        )
        return ASK_ORDER_ID

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle logout command."""
    user = update.effective_user
    logger.info(f"Logout requested by user {user.id}")
    
    await delete_token(user.id)
    context.user_data.clear()  # Clear all user data
    logger.info(f"User {user.id} logged out successfully")
    
    await update.message.reply_text(
        "👋 Вы успешно вышли из системы.\n"
        "Используйте /start для входа снова.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle cancel command."""
    user = update.effective_user
    logger.info(f"Операция отменена пользователем {user.id}")
    
    # Don't clear user data on cancel, preserve authentication
    await update.message.reply_text(
        "❌ Операция отменена.\n"
        "Используйте /start для начала снова.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END
