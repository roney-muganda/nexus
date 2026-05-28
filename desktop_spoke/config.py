import os
from dotenv import load_dotenv

load_dotenv()

HUB_WS_URL = os.getenv("HUB_WS_URL", "ws://127.0.0.1:8000/ws/desktop")
DEVICE_ID = os.getenv("DEVICE_ID", "windows_laptop_001")
API_KEY = os.getenv("DESKTOP_API_KEY", "")
HMAC_SECRET = os.getenv("HMAC_SECRET", "")
ALLOWED_COMMANDS = [
    r"^git\s+",
    r"^python\s+",
    r"^pip\s+",
    r"^npm\s+",
    r"^node\s+",
    r"^dir(\s+.*)?$",
    r"^ls(\s+.*)?$",
    r"^cd\s+",
    r"^type\s+",
    r"^cat\s+",
    r"^echo\s+",
    r"^whoami$",
    r"^ipconfig(\s+.*)?$",
    r"^ping\s+",
    r"^curl\s+",
    r"^alembic\s+",
    r"^uvicorn\s+",
    r"^pytest(\s+.*)?$",
]