import os
import logging
import os
import uuid
import wave
import asyncio
import ffmpeg
from datetime import datetime
from bson import ObjectId
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler as TelegramMessageHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    CallbackQueryHandler,
)
from utils.config import ASSISTANT_BOT_TOKEN, speech_config, ffmpeg_path
import azure.cognitiveservices.speech as speechsdk
from .services.ai_service import summarize_text
from .handlers.message_handler import (
    handle_message,
    list_all_residents,
    handle_task_query,
    handle_resident_query,
    init_handler,
)
from auth.user_auth import restricted
from assistant_bot.db.connection import (
    db_service,
    users_collection,
    resident_collection,
)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

SELECTING_RESIDENT, RECORDING_NOTE, CONFIRMING_NOTE = range(3)

init_handler(db_service)


async def get_today_date_range():
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    logger.info(f"Main today range: {today_start} to {today_end}")
    return today_start, today_end


async def check_auth_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    username = update.effective_user.username
    user = await users_collection.find_one({"telegram_handle": username})

    if not user and username:
        clean_username = username.lower().replace("@", "")
        user = await users_collection.find_one({"telegram_handle": clean_username})

        if not user:
            user = await users_collection.find_one(
                {
                    "$expr": {
                        "$eq": [
                            {"$toLower": "$telegram_handle"},
                            username.lower(),
                        ]
                    }
                }
            )

    if not user:
        await query.message.reply_text(
            "Sorry, you are not authorized to use this bot. Please make sure your Telegram username is registered in the system."
        )
        return

    context.user_data["name"] = user["name"]
    context.user_data["email"] = user["email"]
    context.user_data["role"] = user["role"]

    new_update = Update(update.update_id, message=query.message, callback_query=query)

    if query.data == "list_residents":
        await list_all_residents(new_update)
    elif query.data == "today_tasks":
        today_start, today_end = await get_today_date_range()
        await handle_task_query(
            new_update, {"start_time": today_start, "end_time": today_end}, {}
        )
    elif query.data == "show_help":
        help_text = (
            "🤖 *CareConnect Bot Help* 🤖\n\n"
            "*Available Commands:*\n"
            "/start - Start the bot\n"
            "/help - Show this help message\n"
            "/residents - List all residents\n"
            "/tasks - List today's tasks\n"
            "/stats - Show quick statistics\n"
            "/voicenote - Add a voice note for a resident\n"
            "/whoami - Show your user information\n\n"
            "*Voice Notes:*\n"
            "• Use /voicenote to add a voice note for a specific resident\n"
            "• You can also send a voice message directly to get a transcription\n\n"
            "*Natural Language Queries:*\n"
            "You can ask me about tasks, residents, and activities in natural language. For example:\n\n"
            "*Tasks:*\n"
            "• What tasks are due today?\n"
            "• Show me all high priority tasks\n"
            "• Any overdue tasks?\n"
            "• List pending tasks for [nurse name]\n\n"
            "*Residents:*\n"
            "• How is [resident name] doing?\n"
            "• What happened to [resident name] today?\n"
            "• Show tasks for [resident name]\n"
            "• List residents in [care level]\n\n"
            "*Activities:*\n"
            "• What activities are scheduled today?\n"
            "• Show me activities for this week\n"
            "• Any activities in [location]?\n\n"
            "*Time Ranges:*\n"
            "• last 3 hours\n"
            "• yesterday\n"
            "• this week\n"
            "• tomorrow\n\n"
            "*Follow-up Questions:*\n"
            "You can ask follow-up questions like:\n"
            "• What about tomorrow?\n"
            "• And high priority tasks?\n"
            "• Also show me activities"
        )
        await query.message.reply_text(help_text, parse_mode="Markdown")
    elif query.data == "voicenote":
        await voicenote_start(new_update, context)
    elif query.data == "quick_stats":
        try:
            total_residents = await resident_collection.count_documents({})

            today_start, today_end = await get_today_date_range()
            today_tasks = await db_service.task_collection.count_documents(
                {
                    "$or": [
                        {"start_date": {"$gte": today_start, "$lte": today_end}},
                        {
                            "recurring": True,
                            "recurring_days": {"$in": [today_start.weekday()]},
                        },
                    ]
                }
            )

            now = datetime.now()
            overdue_tasks = await db_service.task_collection.count_documents(
                {"status": "pending", "due_date": {"$lt": now}}
            )

            stats_text = (
                "📊 *Quick Statistics*\n\n"
                f"• Total Residents: {total_residents}\n"
                f"• Today's Tasks: {today_tasks}\n"
                f"• Overdue Tasks: {overdue_tasks}\n\n"
                "Use the buttons below for more details:"
            )

            keyboard = [
                [
                    InlineKeyboardButton(
                        "Show Today's Tasks", callback_data="today_tasks"
                    ),
                    InlineKeyboardButton(
                        "Show Overdue Tasks", callback_data="overdue_tasks"
                    ),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.message.reply_text(
                stats_text, parse_mode="Markdown", reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error showing stats: {str(e)}")
            await query.message.reply_text(
                "Sorry, I couldn't fetch the statistics right now."
            )
    elif query.data == "overdue_tasks":
        now = datetime.now()
        await handle_task_query(
            new_update, {}, {"status": "pending", "due_date": {"$lt": now}}
        )
    elif query.data == "resident_stats":
        await handle_resident_query(new_update, {}, {})
    elif query.data == "task_stats":
        await handle_task_query(new_update, {}, {})


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sorry, I didn't understand that command.")


@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_name = context.user_data.get("name", user.first_name)
    logger.info(f"User {user.id} started the assistant bot")

    keyboard = [
        [
            InlineKeyboardButton("List Residents", callback_data="list_residents"),
            InlineKeyboardButton("Today's Tasks", callback_data="today_tasks"),
        ],
        [
            InlineKeyboardButton("Add Voice Note", callback_data="voicenote"),
            InlineKeyboardButton("Quick Stats", callback_data="quick_stats"),
        ],
        [
            InlineKeyboardButton("Show Help", callback_data="show_help"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        f"Welcome to CareConnect Assistant Bot, {user_name}! 🤖\n\n"
        "I can help you manage and query information about residents, tasks, and activities.\n\n"
        "Try these quick actions or type /help for more information:"
    )

    await update.message.reply_text(welcome_text, reply_markup=reply_markup)


@restricted
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 *CareConnect Bot Help* 🤖\n\n"
        "*Available Commands:*\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/residents - List all residents\n"
        "/tasks - List today's tasks\n"
        "/stats - Show quick statistics\n"
        "/voicenote - Add a voice note for a resident\n"
        "/whoami - Show your user information\n\n"
        "*Voice Notes:*\n"
        "• Use /voicenote to add a voice note for a specific resident\n"
        "• You can also send a voice message directly to get a transcription\n\n"
        "*Natural Language Queries:*\n"
        "You can ask me about tasks, residents, and activities in natural language. For example:\n\n"
        "*Tasks:*\n"
        "• What tasks are due today?\n"
        "• Show me all high priority tasks\n"
        "• Any overdue tasks?\n"
        "• List pending tasks for [nurse name]\n\n"
        "*Residents:*\n"
        "• How is [resident name] doing?\n"
        "• What happened to [resident name] today?\n"
        "• Show tasks for [resident name]\n"
        "• List residents in [care level]\n\n"
        "*Activities:*\n"
        "• What activities are scheduled today?\n"
        "• Show me activities for this week\n"
        "• Any activities in [location]?\n\n"
        "*Time Ranges:*\n"
        "• last 3 hours\n"
        "• yesterday\n"
        "• this week\n"
        "• tomorrow\n\n"
        "*Follow-up Questions:*\n"
        "You can ask follow-up questions like:\n"
        "• What about tomorrow?\n"
        "• And high priority tasks?\n"
        "• Also show me activities"
    )
    message = update.callback_query.message if update.callback_query else update.message
    await message.reply_text(help_text, parse_mode="Markdown")


@restricted
async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_info = (
        f"👤 Your Information:\n\n"
        f"Name: {context.user_data.get('name')}\n"
        f"Email: {context.user_data.get('email')}\n"
        f"Role: {context.user_data.get('role')}\n"
        f"Telegram Username: @{update.effective_user.username}"
    )

    await update.message.reply_text(user_info)


@restricted
async def list_residents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"User {update.effective_user.id} requested resident list")
    await list_all_residents(update)


async def resident_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle resident selection and prompt for voice note"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.message.edit_text("Voice note creation cancelled.")
        return ConversationHandler.END

    resident_id = query.data.replace("resident_", "")
    context.user_data["current_resident_id"] = resident_id

    resident = await resident_collection.find_one({"_id": ObjectId(resident_id)})
    if not resident:
        await query.message.edit_text("Error: Resident not found.")
        return ConversationHandler.END

    context.user_data["resident_name"] = resident.get("full_name", "Unknown")

    await query.message.edit_text(
        f"Selected: {resident.get('full_name')}\n\nPlease send a voice message for your note."
    )

    return RECORDING_NOTE


@restricted
async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"User {update.effective_user.id} requested today's tasks")
    today_start, today_end = await get_today_date_range()
    await handle_task_query(
        update, {"start_time": today_start, "end_time": today_end}, {}
    )


@restricted
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        total_residents = await resident_collection.count_documents({})

        today_start, today_end = await get_today_date_range()
        today_tasks = await db_service.task_collection.count_documents(
            {
                "$or": [
                    {"start_date": {"$gte": today_start, "$lte": today_end}},
                    {
                        "recurring": True,
                        "recurring_days": {"$in": [today_start.weekday()]},
                    },
                ]
            }
        )

        now = datetime.now()
        overdue_tasks = await db_service.task_collection.count_documents(
            {"status": "pending", "due_date": {"$lt": now}}
        )

        stats_text = (
            "📊 *Quick Statistics*\n\n"
            f"• Total Residents: {total_residents}\n"
            f"• Today's Tasks: {today_tasks}\n"
            f"• Overdue Tasks: {overdue_tasks}\n\n"
            "Use the buttons below for more details:"
        )

        keyboard = [
            [
                InlineKeyboardButton("Show Today's Tasks", callback_data="today_tasks"),
                InlineKeyboardButton(
                    "Show Overdue Tasks", callback_data="overdue_tasks"
                ),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = (
            update.callback_query.message if update.callback_query else update.message
        )
        await message.reply_text(
            stats_text, parse_mode="Markdown", reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error showing stats: {str(e)}")
        message = (
            update.callback_query.message if update.callback_query else update.message
        )
        await message.reply_text("Sorry, I couldn't fetch the statistics right now.")


@restricted
async def voicenote_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the voice note process by selecting a resident"""
    logger.info("Starting voice note command")

    residents = await db_service.get_all_residents(limit=20)

    if not residents:
        message = (
            update.callback_query.message if update.callback_query else update.message
        )
        await message.reply_text("No residents found in the database.")
        return ConversationHandler.END

    keyboard = []
    for resident in residents:
        name = resident.get("full_name", "Unknown")
        room = resident.get("room_number", "")
        display = f"{name} (Room: {room})" if room else name

        callback_data = f"resident_{resident['_id']}"
        keyboard.append([InlineKeyboardButton(display, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    message = update.callback_query.message if update.callback_query else update.message

    if update.callback_query:
        await message.edit_text(
            "Select a resident to add a voice note:", reply_markup=reply_markup
        )
    else:
        await message.reply_text(
            "Select a resident to add a voice note:", reply_markup=reply_markup
        )

    return SELECTING_RESIDENT


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
        ffmpeg.input(ogg_path).output(wav_path, ac=1, ar=16000).run(
            overwrite_output=True
        )

        with wave.open(wav_path, "rb") as wf:
            logger.info(
                f"WAV format: {wf.getnchannels()} channels, {wf.getframerate()} Hz, {wf.getsampwidth()} bytes/sample"
            )

        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=speechsdk.audio.AudioConfig(filename=wav_path),
        )

        loop = asyncio.get_running_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, recognizer.recognize_once), timeout=15
            )
        except asyncio.TimeoutError:
            logger.error("Speech recognition timed out.")
            await update.message.reply_text(
                "⏱️ Speech recognition timed out. Please try again."
            )
            return RECORDING_NOTE

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            transcribed_text = result.text

            ai_summary = await summarize_text(transcribed_text)

            context.user_data["transcription"] = transcribed_text
            context.user_data["ai_summary"] = ai_summary

            response = (
                f'You said: "{transcribed_text}"\n\n'
                f"AI Summary: {ai_summary}\n\n"
                f"Do you want to save this note for {context.user_data['resident_name']}?"
            )

            keyboard = [
                [
                    InlineKeyboardButton(
                        "Save Summary as Note", callback_data="save_summary"
                    ),
                    InlineKeyboardButton(
                        "Save Full Transcript", callback_data="save_transcript"
                    ),
                ],
                [InlineKeyboardButton("Cancel", callback_data="cancel")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(response, reply_markup=reply_markup)
            return CONFIRMING_NOTE
        else:
            await update.message.reply_text(
                "Sorry, I couldn't understand the audio. Please try again."
            )
            return RECORDING_NOTE

    except Exception as e:
        logger.error(f"Error in process_voice_note: {e}")
        await update.message.reply_text(
            "Something went wrong while processing your voice note. Please try again."
        )
        return RECORDING_NOTE
    finally:
        for path in [ogg_path, wav_path]:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except PermissionError:
                logger.warning(
                    f"Could not delete file {path} because it is still in use."
                )


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

        logger.info(f"FFMPEG HERE:{ffmpeg_path}")

        logger.info("Converting OGG to WAV using ffmpeg-python...")
        ffmpeg.input(ogg_path).output(wav_path, ac=1, ar=16000).run(
            overwrite_output=True
        )

        with wave.open(wav_path, "rb") as wf:
            logger.info(
                f"WAV format: {wf.getnchannels()} channels, {wf.getframerate()} Hz, {wf.getsampwidth()} bytes/sample"
            )

        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=speechsdk.audio.AudioConfig(filename=wav_path),
        )

        loop = asyncio.get_running_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, recognizer.recognize_once), timeout=15
            )
        except asyncio.TimeoutError:
            logger.error("Speech recognition timed out.")
            await update.message.reply_text(
                "⏱️ Speech recognition timed out. Please try again."
            )
            return

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            transcribed_text = result.text

            ai_summary = await summarize_text(transcribed_text)

            response = f'You said: "{transcribed_text}"\n\nAI Summary: {ai_summary}'

            await update.message.reply_text(response)
        else:
            await update.message.reply_text("Sorry, I couldn't understand the audio.")

    except Exception as e:
        logger.error(f"Error in handle_voice: {e}")
        await update.message.reply_text(
            "Something went wrong while processing your voice."
        )
    finally:
        for path in [ogg_path, wav_path]:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except PermissionError:
                logger.warning(
                    f"Could not delete file {path} because it is still in use."
                )


async def save_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the note to the resident's record"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.message.edit_text("Voice note cancelled. No note was saved.")
        return ConversationHandler.END

    resident_id = context.user_data.get("current_resident_id")
    resident_name = context.user_data.get("resident_name", "Unknown")

    if query.data == "save_summary":
        note_text = f"[AI Summary] {context.user_data.get('ai_summary')}"
    else:
        note_text = f"[Voice Transcript] {context.user_data.get('transcription')}"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    note_with_timestamp = f"[{timestamp}] {note_text}"

    success = await db_service.add_resident_note(resident_id, note_with_timestamp)

    if success:
        await query.message.edit_text(
            f"✅ Voice note successfully saved for {resident_name}."
        )
    else:
        await query.message.edit_text(
            f"❌ Failed to save note for {resident_name}. Please try again."
        )

    context.user_data.clear()
    return ConversationHandler.END


def main():
    application = Application.builder().token(ASSISTANT_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("residents", list_residents))
    application.add_handler(CommandHandler("whoami", whoami_command))
    application.add_handler(CommandHandler("help", help_command))

    voice_note_handler = ConversationHandler(
        entry_points=[
            CommandHandler("voicenote", voicenote_start),
            CallbackQueryHandler(voicenote_start, pattern="^voicenote$"),
        ],
        states={
            SELECTING_RESIDENT: [CallbackQueryHandler(resident_selected)],
            RECORDING_NOTE: [MessageHandler(filters.VOICE, process_voice_note)],
            CONFIRMING_NOTE: [CallbackQueryHandler(save_note)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    )
    application.add_handler(voice_note_handler)

    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.COMMAND, unknown))
    application.add_handler(CommandHandler("tasks", list_tasks))
    application.add_handler(CommandHandler("stats", show_stats))

    application.add_handler(CallbackQueryHandler(check_auth_callback))

    application.add_handler(
        TelegramMessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("Starting Assistant Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Assistant Bot stopped")


if __name__ == "__main__":
    main()
