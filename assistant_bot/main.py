import logging
from motor.motor_asyncio import AsyncIOMotorClient
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import ASSISTANT_BOT_TOKEN, MONGO_URI
from auth_service import restricted

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client["caregiver"]
users_collection = db["users"]
resident_collection = db["resident_info"]


@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = context.user_data.get("name", "there")
    await update.message.reply_text(
        f"Hello {user_name}! I'm your assistant bot. "
        f"Use /residents to see the list of residents."
    )


@restricted
async def list_residents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all residents from MongoDB"""
    try:
        residents_cursor = resident_collection.find({}, {"full_name": 1})
        residents = await residents_cursor.to_list(length=50)

        if not residents:
            await update.message.reply_text("No residents found in the database.")
            return

        response = "👵👴 Resident List:\n\n"
        for idx, resident in enumerate(residents, start=1):
            name = resident.get("full_name", "Unnamed")
            response += f"{idx}. {name}\n"

        await update.message.reply_text(response)
        logger.info(f"Sent list of {len(residents)} residents")
    except Exception as e:
        logger.error(f"Error retrieving residents: {e}")
        await update.message.reply_text(
            "Sorry, I couldn't retrieve the resident list. Please try again later."
        )


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
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    help_text = (
        "Here are the commands you can use:\n\n"
        "/start - Start the bot\n"
        "/residents - List all residents\n"
        "/whoami - Show your user information\n"
        "/help - Show this help message"
    )
    await update.message.reply_text(help_text)


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown commands."""
    await update.message.reply_text("Sorry, I didn't understand that command.")


def main():
    application = Application.builder().token(ASSISTANT_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("residents", list_residents))
    application.add_handler(CommandHandler("whoami", whoami_command))
    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Starting Assistant Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Assistant Bot stopped")


if __name__ == "__main__":
    main()
