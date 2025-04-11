import os
import certifi
import shutil
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# Environment Variables
API_BASE_URL = os.getenv("API_BASE_URL")
API_EMAIL = os.getenv("API_EMAIL")
API_PASSWORD = os.getenv("API_PASSWORD")
MONGO_URI = os.getenv("MONGO_URI")
ASSISTANT_BOT_TOKEN = os.getenv("ASSISTANT_BOT_TOKEN")
REMINDERS_BOT_TOKEN = os.getenv("REMINDERS_BOT_TOKEN")
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_ENDPOINT = os.getenv("AZURE_SPEECH_ENDPOINT")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# FFmpeg Configuration
ffmpeg_path = shutil.which("ffmpeg")

# Azure Speech Configuration
speech_config = speechsdk.SpeechConfig(
    subscription=AZURE_SPEECH_KEY,
    endpoint=AZURE_SPEECH_ENDPOINT,
)
speech_config.speech_recognition_language = "en-US"
