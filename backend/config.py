import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

DB_PATH = os.environ.get("AUTO_MAIL_DB_PATH", str(BASE_DIR / "auto_mail.db"))

DEFAULT_SETTINGS = {
    "smtp_host": "smtp.gmail.com",
    "smtp_port": "587",
    "smtp_user": "",
    "smtp_password": "",
    "from_name": "Automation Team",
    "from_email": "",
    "reply_to": "",
    "delay_min_seconds": "35",
    "delay_max_seconds": "75",
    "daily_send_limit": "40",
    "ai_provider": "groq",
    "groq_api_key": os.getenv("GROQ_API_KEY", ""),
    "groq_model": "openai/gpt-oss-120b",
    "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
    "agency_name": "AutomaFlow Solutions",
    "agency_pitch": "We build custom AI agents and workflow automations that eliminate manual data entry, streamline operations, and save teams 15+ hours per week.",
}

