import asyncio
from functools import partial
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from reminders_bot.services.activity_service import process_events
from reminders_bot.services.medication_service import schedule_medication_reminders
from reminders_bot.services.task_service import process_task_reminders
from reminders_bot.services.fall_detection_service import (
    process_fall_alerts,
    handle_fall_response,
)
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
    scheduler = context.bot_data.get("scheduler")

    if scheduler:
        for job in scheduler.get_jobs():
            if job.id.startswith("med_"):
                scheduler.remove_job(job.id)

    await process_events()
    await process_task_reminders()
    await schedule_medication_reminders(scheduler)
    await process_fall_alerts()
    await update.message.reply_text(
        f"🔃 Updated your activities, tasks, medications, and fall alerts! 🔃"
    )


async def run_bot():
    """Async function to run the bot with proper event loop management"""
    application = Application.builder().token(REMINDERS_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("refresh", refresh))
    application.add_handler(CallbackQueryHandler(handle_fall_response))

    await application.initialize()

    scheduler = AsyncIOScheduler()

    # Check upcoming activities
    scheduler.add_job(
        process_events,
        IntervalTrigger(seconds=10),
        id="check_activities",
        name="Check for upcoming activities",
    )

    # Check upcoming tasks
    scheduler.add_job(
        process_task_reminders,
        IntervalTrigger(seconds=15),
        id="check_tasks",
        name="Check for upcoming tasks",
    )

    # Schedule meds daily
    scheduler.add_job(
        partial(schedule_medication_reminders, scheduler),
        CronTrigger(hour=0, minute=1, timezone="Asia/Singapore"),
        id="schedule_medications",
        name="Schedule medication reminders for the day",
    )

    # Fall detection check every 5 minutes
    scheduler.add_job(
        process_fall_alerts,
        IntervalTrigger(seconds=6),
        id="check_falls",
        name="Check recent fall detection logs",
    )

    application.bot_data["scheduler"] = scheduler
    scheduler.start()

    await process_events()
    await process_task_reminders()
    await process_fall_alerts()

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
