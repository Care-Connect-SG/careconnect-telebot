import logging
import os
import uuid
import wave
import tempfile
import asyncio
import ffmpeg
import ssl
import certifi
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)
from config import ASSISTANT_BOT_TOKEN, MONGO_URI, AZURE_SPEECH_KEY, AZURE_SPEECH_ENDPOINT, OPENAI_API_KEY
import azure.cognitiveservices.speech as speechsdk
from .services.ai_service import summarize_text
from .services.database import DatabaseService

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
db_service = DatabaseService(mongo_client)

# Conversation states
SELECTING_RESIDENT, RECORDING_NOTE, CONFIRMING_NOTE = range(3)

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
    help_text = (
        "Here are the commands you can use:\n\n"
        "/start - Start the bot\n"
        "/residents - List all residents\n"
        "/voicenote - Add a voice note for a resident\n"
        "/help - Show this help message\n\n"
        "You can also send a voice message directly to transcribe it."
    )
    await update.message.reply_text(help_text)

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sorry, I didn't understand that command.")

# Voice Note Command Handlers
async def voicenote_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the voice note process by selecting a resident"""
    logger.info("Starting voice note command")
    
    # Fetch all residents
    residents = await db_service.get_all_residents(limit=20)
    
    if not residents:
        await update.message.reply_text("No residents found in the database.")
        return ConversationHandler.END
    
    # Create keyboard with resident buttons
    keyboard = []
    for resident in residents:
        name = resident.get("full_name", "Unknown")
        room = resident.get("room_number", "")
        display = f"{name} (Room: {room})" if room else name
        
        # Store resident ID in the callback data
        callback_data = f"resident_{resident['_id']}"
        keyboard.append([InlineKeyboardButton(display, callback_data=callback_data)])
    
    # Add cancel button
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Select a resident to add a voice note:",
        reply_markup=reply_markup
    )
    
    return SELECTING_RESIDENT

async def resident_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle resident selection and prompt for voice note"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.message.edit_text("Voice note creation cancelled.")
        return ConversationHandler.END
    
    # Extract resident ID from callback data
    resident_id = query.data.replace("resident_", "")
    context.user_data["current_resident_id"] = resident_id
    
    # Get resident details
    resident = await resident_collection.find_one({"_id": ObjectId(resident_id)})
    if not resident:
        await query.message.edit_text("Error: Resident not found.")
        return ConversationHandler.END
    
    context.user_data["resident_name"] = resident.get("full_name", "Unknown")
    
    await query.message.edit_text(
        f"Selected: {resident.get('full_name')}\n\nPlease send a voice message for your note."
    )
    
    return RECORDING_NOTE

async def process_voice_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process the voice note, transcribe it, generate summary and confirm saving"""
    ogg_path, wav_path = None, None
    try:
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)

        tmp_dir = os.path.join(os.path.dirname(__file__), "tmp")
        os.makedirs(tmp_dir, exist_ok=True)

        unique_id = str(uuid.uuid4())
        ogg_path = os.path.join(tmp_dir, f"{unique_id}.ogg")
        wav_path = os.path.join(tmp_dir, f"{unique_id}.wav")

        logger.info(f"Downloading voice note to: {ogg_path}")
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
            return RECORDING_NOTE

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            transcribed_text = result.text
            
            # Get AI summary
            ai_summary = await summarize_text(transcribed_text)
            
            # Store the transcription and summary for later use
            context.user_data["transcription"] = transcribed_text
            context.user_data["ai_summary"] = ai_summary
            
            # Format the response with both the transcription and summary
            response = (
                f"You said: \"{transcribed_text}\"\n\n"
                f"AI Summary: {ai_summary}\n\n"
                f"Do you want to save this note for {context.user_data['resident_name']}?"
            )
            
            # Create confirmation keyboard
            keyboard = [
                [
                    InlineKeyboardButton("Save Summary as Note", callback_data="save_summary"),
                    InlineKeyboardButton("Save Full Transcript", callback_data="save_transcript")
                ],
                [InlineKeyboardButton("Cancel", callback_data="cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(response, reply_markup=reply_markup)
            return CONFIRMING_NOTE
        else:
            await update.message.reply_text("Sorry, I couldn't understand the audio. Please try again.")
            return RECORDING_NOTE

    except Exception as e:
        logger.error(f"Error in process_voice_note: {e}")
        await update.message.reply_text("Something went wrong while processing your voice note. Please try again.")
        return RECORDING_NOTE
    finally:
        # Clean up temp files
        for path in [ogg_path, wav_path]:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except PermissionError:
                logger.warning(f"Could not delete file {path} because it is still in use.")

async def save_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the note to the resident's record"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.message.edit_text("Voice note cancelled. No note was saved.")
        return ConversationHandler.END
    
    resident_id = context.user_data.get("current_resident_id")
    resident_name = context.user_data.get("resident_name", "Unknown")
    
    # Determine which text to save based on the button pressed
    if query.data == "save_summary":
        note_text = f"[AI Summary] {context.user_data.get('ai_summary')}"
    else:  # save_transcript
        note_text = f"[Voice Transcript] {context.user_data.get('transcription')}"
    
    # Add date/time prefix to the note
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    note_with_timestamp = f"[{timestamp}] {note_text}"
    
    # Save to database
    success = await db_service.add_resident_note(resident_id, note_with_timestamp)
    
    if success:
        await query.message.edit_text(f"✅ Voice note successfully saved for {resident_name}.")
    else:
        await query.message.edit_text(f"❌ Failed to save note for {resident_name}. Please try again.")
    
    # Clear conversation data
    context.user_data.clear()
    return ConversationHandler.END

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

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("residents", list_residents))
    application.add_handler(CommandHandler("help", help_command))
    
    # Voice note conversation handler
    voice_note_handler = ConversationHandler(
        entry_points=[CommandHandler("voicenote", voicenote_start)],
        states={
            SELECTING_RESIDENT: [CallbackQueryHandler(resident_selected)],
            RECORDING_NOTE: [MessageHandler(filters.VOICE, process_voice_note)],
            CONFIRMING_NOTE: [CallbackQueryHandler(save_note)]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )
    application.add_handler(voice_note_handler)
    
    # Regular message handlers
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Starting Assistant Bot...")
    application.run_polling()

if __name__ == "__main__":
    main()
