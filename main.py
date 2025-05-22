### Directory structure (for clarity):
# bot/
# ├── main.py+
# ├── handlers.py+
# ├── api.py+
# ├── storage.py
# ├── config.py
# └── requirements.txt


import asyncio
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    PicklePersistence,
)
from config import BOT_TOKEN
from handlers import (
    start,
    ask_email,
    ask_password,
    ask_order_id,
    handle_otp,
    logout,
    cancel,
    ASK_EMAIL,
    ASK_PASSWORD,
    ASK_ORDER_ID,
    WAITING_FOR_OTP,
)
from storage import init_db

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def register_handlers(application: Application) -> None:
    """Register all bot handlers."""
    
    # Create conversation handler with persistence
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_email)],
            ASK_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_password)],
            ASK_ORDER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_order_id),
                CommandHandler("logout", logout)
            ],
            WAITING_FOR_OTP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_otp),
                CommandHandler("cancel", cancel)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="main_conversation",
        persistent=True
    )

    # Add handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("logout", logout))

def main():
    """Start the bot."""
    # Initialize persistence
    persistence = PicklePersistence(filepath="bot_data.pkl")
    
    # Create application with persistence
    application = Application.builder()\
        .token(BOT_TOKEN)\
        .persistence(persistence)\
        .build()
    
    register_handlers(application)
    
    # Start the bot
    logger.info("Starting bot...")
    application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
