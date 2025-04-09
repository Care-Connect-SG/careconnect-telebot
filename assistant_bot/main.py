import logging
import os
import uuid
import wave
import tempfile
import asyncio
import ffmpeg
import ssl
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from config import ASSISTANT_BOT_TOKEN, MONGO_URI, AZURE_SPEECH_KEY, AZURE_SPEECH_ENDPOINT, OPENAI_API_KEY
import azure.cognitiveservices.speech as speechsdk
from .services.ai_service import summarize_text

# Set SSL certificate path for HTTPS requests
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

# 🛠️ Make sure ffmpeg binary is accessible
ffmpeg_path = r"C:\ffmpeg\bin\ffmpeg.exe"
os.environ["PATH"] += os.pathsep + os.path.dirname(ffmpeg_path)

# 🎤 Azure Speech Config
speech_config = speechsdk.SpeechConfig(
    subscription=AZURE_SPEECH_KEY,
    endpoint=AZURE_SPEECH_ENDPOINT,
)
speech_config.speech_recognition_language = "en-US"

# 📋 Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# 🗃️ MongoDB Setup
mongo_client = AsyncIOMotorClient(
    MONGO_URI,
    tlsAllowInvalidCertificates=True
)
db = mongo_client["resident"]
resident_collection = db["resident_info"]

# 🟢 Bot Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Hello {update.effective_user.first_name}! How can I help you today.")

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

# 🎧 Voice Handler
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ogg_path, wav_path = None, None
    try:
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)

        tmp_dir = os.path.join(os.path.dirname(__file__), "tmp")
        os.makedirs(tmp_dir, exist_ok=True)

        unique_id = str(uuid.uuid4())
        ogg_path = os.path.join(tmp_dir, f"{unique_id}.ogg")
        wav_path = os.path.join(tmp_dir, f"{unique_id}.wav")

        logger.info(f"Downloading voice to: {ogg_path}")
        await file.download_to_drive(ogg_path)

        if not os.path.exists(ogg_path) or os.path.getsize(ogg_path) == 0:
            raise FileNotFoundError(f"OGG file not found or empty at {ogg_path}")

        logger.info("Converting OGG to WAV using ffmpeg-python...")
        ffmpeg.input(ogg_path).output(wav_path, ac=1, ar=16000).run(overwrite_output=True)

        with wave.open(wav_path, 'rb') as wf:
            logger.info(f"WAV format: {wf.getnchannels()} channels, {wf.getframerate()} Hz, {wf.getsampwidth()} bytes/sample")

        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=speechsdk.audio.AudioConfig(filename=wav_path),
        )

        loop = asyncio.get_running_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, recognizer.recognize_once),
                timeout=15
            )
        except asyncio.TimeoutError:
            logger.error("Speech recognition timed out.")
            await update.message.reply_text("⏱️ Speech recognition timed out. Please try again.")
            return

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            transcribed_text = result.text
            
            # Get AI summary
            ai_summary = await summarize_text(transcribed_text)
            
            # Format the response with both the transcription and summary
            response = f"You said: \"{transcribed_text}\"\n\nAI Summary: {ai_summary}"
            
            await update.message.reply_text(response)
        else:
            await update.message.reply_text("Sorry, I couldn't understand the audio.")

    except Exception as e:
        logger.error(f"Error in handle_voice: {e}")
        await update.message.reply_text("Something went wrong while processing your voice.")
    finally:
        for path in [ogg_path, wav_path]:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except PermissionError:
                logger.warning(f"Could not delete file {path} because it is still in use.")


# 🚀 Entry Point
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
