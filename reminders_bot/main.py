import asyncio
from functools import partial
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from reminders_bot.services.activity_service import process_events
from reminders_bot.services.medication_service import schedule_medication_reminders
from reminders_bot.services.task_service import process_task_reminders
from auth.user_auth import restricted
from utils.config import REMINDERS_BOT_TOKEN
from reminders_bot.chat_registry import user_chat_map, user_name_map

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    user_name = context.user_data.get("name", "there")

    mongo_user_id = context.user_data.get("id")

    user_chat_map[mongo_user_id] = chat_id
    user_name_map[mongo_user_id] = user_name

    logger.info(
        f"User {user.id} ({user_name}) started the reminders bot. Chat ID: {chat_id}, MongoDB ID: {mongo_user_id}"
    )

    await update.message.reply_text(
        f"""Hello {user_name} 👋  I’m your personal reminders bot, here to help you stay on top of your activities, tasks, and medications!
        """
    )

@restricted
async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🔃 Fetching the latest activities, tasks and medication reminders for you 🔃"
    )
    scheduler = AsyncIOScheduler()
    scheduler.remove_all_jobs() # clear away previous scheduled jobs to avoid repeated reminders

    await process_events()
    await process_task_reminders()
    await schedule_medication_reminders(scheduler)

    scheduler.start()
    
  
async def run_bot():
    """Async function to run the bot with proper event loop management"""
    application = Application.builder().token(REMINDERS_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("refresh", refresh))

    await application.initialize()

    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        process_events,
        IntervalTrigger(seconds=10),
        id="check_activities",
        name="Check for upcoming activities",
    )

    scheduler.add_job(
        process_task_reminders,
        IntervalTrigger(seconds=15),
        id="check_tasks",
        name="Check for upcoming tasks",
    )

    scheduler.add_job(
        partial(schedule_medication_reminders, scheduler),
        CronTrigger(hour=0, minute=1, timezone="Asia/Singapore"),
        id="schedule_medications",
        name="Schedule medication reminders for the day",
    )

    scheduler.start()

    await process_events()
    await process_task_reminders()

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
