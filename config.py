import os

from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL")
MONGO_URI = os.getenv("MONGO_URI")
ASSISTANT_BOT_TOKEN = os.getenv("ASSISTANT_BOT_TOKEN")
REMINDERS_BOT_TOKEN = os.getenv("REMINDERS_BOT_TOKEN")

# DB Configuration
DB_NAME = "caregiver"
RESIDENT_DB_NAME = "resident"
RESIDENT_COLLECTION = "resident_info"
TASKS_COLLECTION = "tasks"
ACTIVITIES_COLLECTION = "activities"
USERS_COLLECTION = "users"
