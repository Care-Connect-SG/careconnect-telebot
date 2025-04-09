import logging
import os
import uuid
import tempfile
from motor.motor_asyncio import AsyncIOMotorClient
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from config import ASSISTANT_BOT_TOKEN, MONGO_URI, AZURE_SPEECH_KEY, AZURE_SPEECH_ENDPOINT
from pydub import AudioSegment
import azure.cognitiveservices.speech as speechsdk
from pydub.utils import which


# Azure Speech Config
speech_config = speechsdk.SpeechConfig(
    subscription=AZURE_SPEECH_KEY,
    endpoint=AZURE_SPEECH_ENDPOINT,
)
speech_config.speech_recognition_language = "en-US"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client["resident"]
resident_collection = db["resident_info"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Hello {update.effective_user.first_name}! Send me a voice message and I’ll transcribe it for you."
    )

async def list_residents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    residents = await resident_collection.find({}, {"full_name": 1}).to_list(50)
    if not residents:
        await update.message.reply_text("No residents found.")
    else:
        msg = "👵👴 Resident List:\n" + "\n".join(
            [f"{i+1}. {r.get('full_name', 'Unnamed')}" for i, r in enumerate(residents)]
        )
        await update.message.reply_text(msg)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Use /start, /residents or send a voice message to transcribe.")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sorry, I didn't understand that command.")


ffmpeg_bin = r"C:\Users\klohe\OneDrive\Documents\ffmpeg-7.1.1-essentials_build\ffmpeg-7.1.1-essentials_build\bin"
ffmpeg_path = os.path.join(ffmpeg_bin, "ffmpeg.exe")
ffprobe_path = os.path.join(ffmpeg_bin, "ffprobe.exe")

# ✅ Register paths with pydub
AudioSegment.converter = r"C:\Users\klohe\OneDrive\Documents\ffmpeg-7.1.1-essentials_build\ffmpeg-7.1.1-essentials_build\bin\ffmpeg.exe"
AudioSegment.ffprobe   = r"C:\Users\klohe\OneDrive\Documents\ffmpeg-7.1.1-essentials_build\ffmpeg-7.1.1-essentials_build\bin\ffprobe.exe"

logger = logging.getLogger(__name__)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        print("FFmpeg:", which(ffmpeg_path))
        print("FFprobe:", which(ffprobe_path))

        # 🔧 Use local 'tmp' folder in your project
        tmp_dir = os.path.join(os.path.dirname(__file__), "tmp")
        os.makedirs(tmp_dir, exist_ok=True)

        unique_id = str(uuid.uuid4())
        ogg_path = os.path.join(tmp_dir, f"{unique_id}.ogg")
        wav_path = os.path.join(tmp_dir, f"{unique_id}.wav")

        logger.info(f"Downloading to: {ogg_path}")
        await file.download_to_drive(ogg_path)

        if not os.path.exists(ogg_path):
            raise FileNotFoundError(f"OGG file not found at {ogg_path}")

        # 🎧 Convert
        logger.info("Converting to WAV...")
        audio = AudioSegment.from_file(ogg_path, format="ogg")
        audio.export(wav_path, format="wav")

        # 🧠 Transcribe
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=speechsdk.audio.AudioConfig(filename=wav_path)
        )
        result = recognizer.recognize_once()

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            await update.message.reply_text(f"You said: \"{result.text}\"")
        else:
            await update.message.reply_text("Sorry, I couldn't understand the audio.")

    except Exception as e:
        logger.error(f"Error in handle_voice: {e}")
        await update.message.reply_text("Something went wrong while processing your voice.")
    finally:
        # 🧹 Clean up
        for path in [ogg_path, wav_path]:
            if os.path.exists(path):
                os.remove(path)
    
def main():
    application = Application.builder().token(ASSISTANT_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("residents", list_residents))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Starting Assistant Bot...")
    application.run_polling()

if __name__ == "__main__":
    main()
