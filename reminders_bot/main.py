import asyncio
import logging
import aiohttp
from datetime import datetime, timedelta
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import REMINDERS_BOT_TOKEN, API_BASE_URL, CHAT_ID

CHECK_INTERVAL = 1  # minutes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

bot = Bot(token=REMINDERS_BOT_TOKEN)

async def fetch_events():
    """Fetch upcoming events from the API"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_BASE_URL) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"API returned status {response.status}")
                    return []
    except Exception as e:
        logger.error(f"Error fetching events: {e}")
        return []

async def process_events(context=None):
    """Process events and send reminders"""
    logger.info("Checking for upcoming events...")

    events = await fetch_events()
    logger.info(f"Found {len(events)} events")

    now = datetime.now()
    upcoming_count = 0

    for event in events:
        try:
            event_time = datetime.fromisoformat(event['datetime'])
            time_until_event = event_time - now

            if time_until_event <= timedelta(hours=1) and time_until_event > timedelta(0) and not event.get('reminder_sent', False):
                await send_reminder(event)
                await mark_reminder_sent(event['id'])
                upcoming_count += 1
        except Exception as e:
            logger.error(f"Error processing event {event.get('id', 'unknown')}: {e}")

    logger.info(f"Processed {len(events)} events, sent {upcoming_count} reminders")

async def send_reminder(event):
    """Send a reminder message"""
    try:
        title = event.get('title', 'Unnamed event')
        event_time = datetime.fromisoformat(event['datetime'])
        formatted_time = event_time.strftime("%Y-%m-%d %H:%M")

        message = f"📅 REMINDER: {title} starts at {formatted_time}"
        await bot.send_message(chat_id=CHAT_ID, text=message)
        logger.info(f"Sent reminder for event: {event.get('id', 'unknown')}")
    except Exception as e:
        logger.error(f"Error sending reminder: {e}")

async def mark_reminder_sent(event_id):
    """Mark the reminder as sent in the API"""
    try:
        update_url = f"{API_BASE_URL}/{event_id}"
        async with aiohttp.ClientSession() as session:
            async with session.patch(update_url, json={"reminder_sent": True}) as response:
                if response.status not in (200, 201, 204):
                    logger.error(f"Failed to mark reminder sent. API returned {response.status}")
    except Exception as e:
        logger.error(f"Error marking reminder as sent: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command"""
    user = update.effective_user
    logger.info(f"User {user.id} started the reminders bot")
    await update.message.reply_text(
        f"Hello {user.first_name}! I'll send reminders for upcoming events. "
        f"Use /check to manually check for events now."
    )

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually check for events"""
    await update.message.reply_text("Checking for events now...")
    await process_events()
    await update.message.reply_text("Check complete!")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot status"""
    events = await fetch_events()
    now = datetime.now()

    upcoming = [e for e in events if datetime.fromisoformat(e['datetime']) > now]
    pending_reminders = [e for e in upcoming if not e.get('reminder_sent', False)]

    status = (
        f"🤖 Reminders Bot Status:\n\n"
        f"Total events: {len(events)}\n"
        f"Upcoming events: {len(upcoming)}\n"
        f"Pending reminders: {len(pending_reminders)}\n"
        f"Next check in: < {CHECK_INTERVAL} minutes"
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
        IntervalTrigger(minutes=CHECK_INTERVAL),
        id='check_events',
        name='Check for upcoming events'
    )
    scheduler.start()

    await process_events()

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
