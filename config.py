# config.py

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token
BOT_TOKEN = "6559280372:AAH09-C1KTRttGvpMUxyKXL6MIPDtzVDS9U"

# API endpoints
LOGIN_URL = "https://bi1.wyzo.shop/api/v1/admin/login"
ORDER_URL = "https://wyzo.shop/api/v1/admin/sales/orders"

# Device name for authorization
DEVICE_NAME = "pc"

# SQLite settings
DB_NAME = "sessions.db"
