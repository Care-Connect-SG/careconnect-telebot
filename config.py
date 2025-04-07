import os

from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
ASSISTANT_BOT_TOKEN = os.getenv("ASSISTANT_BOT_TOKEN")
REMINDERS_BOT_TOKEN = os.getenv("REMINDERS_BOT_TOKEN")
