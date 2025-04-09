import os
import logging
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler as TelegramMessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
)
from datetime import datetime, timedelta

from config import ASSISTANT_BOT_TOKEN, MONGO_URI
from assistant_bot.handlers import message_handler
from auth.user_auth import restricted, users_collection

# Set SSL certificate environment variable
os.environ["SSL_CERT_FILE"] = certifi.where()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize MongoDB
mongo_client = AsyncIOMotorClient(
    MONGO_URI,
    tlsAllowInvalidCertificates=True
)
resident_db = mongo_client["resident"]
caregiver_db = mongo_client["caregiver"]

users_collection = caregiver_db["users"]
resident_collection = resident_db["resident_info"]

@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    user_name = context.user_data.get("name", user.first_name)
    logger.info(f"User {user.id} started the assistant bot")

    # Create quick action buttons
    keyboard = [
        [
            InlineKeyboardButton("List Residents", callback_data="list_residents"),
            InlineKeyboardButton("Today's Tasks", callback_data="today_tasks"),
        ],
        [
            InlineKeyboardButton("Show Help", callback_data="show_help"),
            InlineKeyboardButton("Quick Stats", callback_data="quick_stats"),
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
    """Send a message when the command /help is issued."""
    help_text = (
        "🤖 *CareConnect Bot Help* 🤖\n\n"
        "*Available Commands:*\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/residents - List all residents\n"
        "/tasks - List today's tasks\n"
        "/stats - Show quick statistics\n"
        "/whoami - Show your user information\n\n"
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
    """Show current user information"""
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
    """List all residents from MongoDB"""
    logger.info(f"User {update.effective_user.id} requested resident list")
    await message_handler.list_all_residents(update)


async def get_today_date_range():
    """Get consistent date range for today's tasks"""
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    logger.info(f"Main today range: {today_start} to {today_end}")
    return today_start, today_end


@restricted
async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List today's tasks"""
    logger.info(f"User {update.effective_user.id} requested today's tasks")
    today_start, today_end = await get_today_date_range()
    await message_handler.handle_task_query(
        update, {"start_time": today_start, "end_time": today_end}, {}
    )


@restricted
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show quick statistics about the facility"""
    try:
        # Get statistics from the database
        from assistant_bot.services.database import DatabaseService
        db = DatabaseService()
        total_residents = await db.resident_collection.count_documents({})

        # Get today's tasks count (including recurring tasks)
        today_start, today_end = await get_today_date_range()
        today_tasks = await db.tasks_collection.count_documents(
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

        # Get overdue tasks count consistently
        now = datetime.now()
        overdue_tasks = await db.tasks_collection.count_documents(
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


# Add a new function to handle authorization for callback queries
async def check_auth_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Custom handler for callback queries that checks authorization first"""
    query = update.callback_query
    await query.answer()
    
    # Check authorization
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
    
    # Set user data in context
    context.user_data["name"] = user["name"]
    context.user_data["email"] = user["email"]
    context.user_data["role"] = user["role"]
    
    # Create a new update object with the message from the callback query
    new_update = Update(update.update_id, message=query.message, callback_query=query)
    
    # Process callback data
    if query.data == "list_residents":
        await message_handler.list_all_residents(new_update)
    elif query.data == "today_tasks":
        today_start, today_end = await get_today_date_range()
        await message_handler.handle_task_query(
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
            "/whoami - Show your user information\n\n"
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
    elif query.data == "quick_stats":
        try:
            from assistant_bot.services.database import DatabaseService
            db = DatabaseService()
            total_residents = await db.resident_collection.count_documents({})

            today_start, today_end = await get_today_date_range()
            today_tasks = await db.tasks_collection.count_documents(
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
            overdue_tasks = await db.tasks_collection.count_documents(
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

            await query.message.reply_text(
                stats_text, parse_mode="Markdown", reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error showing stats: {str(e)}")
            await query.message.reply_text("Sorry, I couldn't fetch the statistics right now.")
    elif query.data == "overdue_tasks":
        now = datetime.now()
        await message_handler.handle_task_query(
            new_update, {}, {"status": "pending", "due_date": {"$lt": now}}
        )
    elif query.data == "resident_stats":
        await message_handler.handle_resident_query(new_update, {}, {})
    elif query.data == "task_stats":
        await message_handler.handle_task_query(new_update, {}, {})


def main():
    """Start the bot."""
    # Create the Application and pass it your bot's token
    application = Application.builder().token(ASSISTANT_BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("residents", list_residents))
    application.add_handler(CommandHandler("whoami", whoami_command))
    application.add_handler(CommandHandler("tasks", list_tasks))
    application.add_handler(CommandHandler("stats", show_stats))

    # Add callback query handler - use our custom handler instead of handle_callback
    application.add_handler(CallbackQueryHandler(check_auth_callback))

    # Add message handler for natural language queries
    application.add_handler(
        TelegramMessageHandler(
            filters.TEXT & ~filters.COMMAND, message_handler.handle_message
        )
    )

    # Start the Bot
    logger.info("Starting Assistant Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Assistant Bot stopped")


if __name__ == "__main__":
    main()
