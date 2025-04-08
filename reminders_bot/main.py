import asyncio
import logging

from datetime import datetime, timedelta, timezone
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from reminders_bot.services.activity_service import process_events, fetch_activities
from config import REMINDERS_BOT_TOKEN
from reminders_bot.chat_registry import user_chat_map

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id

    user_chat_map[str(user.id)] = chat_id

    logger.info(f"User {user.id} started the reminders bot. Chat ID: {chat_id}")

    await update.message.reply_text(
        f"Hello {user.first_name}! I'll send reminders for upcoming activities. "
        f"Use /check to manually check for activities now."
    )


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually check for activities"""
    await update.message.reply_text("Checking for upcoming activities now...")
    await process_events()
    await update.message.reply_text("Check complete!")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot status"""
    activities = await fetch_activities()
    now_utc = datetime.now(timezone.utc)

    upcoming = []
    pending_reminders = []

    for activity in activities:
        start_time_str = activity["start_time"]

        if "Z" in start_time_str or "+" in start_time_str:
            start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        else:
            start_time = datetime.fromisoformat(start_time_str).replace(
                tzinfo=timezone.utc
            )

        if start_time > now_utc:
            upcoming.append(activity)

            reminder_minutes = activity.get("reminder_minutes")
            if reminder_minutes is None:
                reminder_minutes = 5

            reminder_time = start_time - timedelta(minutes=reminder_minutes)

            if now_utc < reminder_time and not activity.get("reminder_sent", False):
                pending_reminders.append(activity)

    status = (
        f"🤖 Reminders Bot Status:\n\n"
        f"Total upcoming activities: {len(activities)}\n"
        f"Activities within next 2 days: {len(upcoming)}\n"
        f"Pending reminders: {len(pending_reminders)}\n"
        f"Next check in: < 10 seconds"
    )

    await update.message.reply_text(status)


async def run_bot():
    """Async function to run the bot with proper event loop management"""
    application = Application.builder().token(REMINDERS_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check", check_command))
    application.add_handler(CommandHandler("status", status_command))

    await application.initialize()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        process_events,
        IntervalTrigger(seconds=10),
        id="check_events",
        name="Check for upcoming activities",
    )
    scheduler.start()

    await process_events()

    await application.start()

    logger.info("Starting Reminders Bot...")
    await application.updater.start_polling()

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopping bot...")
    finally:
        scheduler.shutdown()
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        logger.info("Reminders Bot stopped")


def main():
    """Entry point that runs the async bot function"""
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
