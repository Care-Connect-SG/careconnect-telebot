import os

from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL")
MONGO_URI = os.getenv("MONGO_URI")
ASSISTANT_BOT_TOKEN = os.getenv("ASSISTANT_BOT_TOKEN")
REMINDERS_BOT_TOKEN = os.getenv("REMINDERS_BOT_TOKEN")
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_ENDPOINT = os.getenv("AZURE_SPEECH_ENDPOINT")