import logging
import aiohttp
from datetime import datetime, timedelta, timezone

from config import API_BASE_URL
from reminders_bot.bot import reminderBot

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def fetch_activities():
    """Fetch upcoming activities that might need reminders soon"""
    try:
        async with aiohttp.ClientSession() as session:
            now_utc = datetime.now(timezone.utc)

            end_time_utc = now_utc + timedelta(days=2)

            start_date_param = now_utc.strftime("%Y-%m-%dT%H:%M:%S")

            logger.info(f"Fetching activities starting after {start_date_param}")

            url = f"{API_BASE_URL}/activities?start_date={start_date_param}&sort_by=start_time&sort_order=asc"

            async with session.get(url) as response:
                if response.status == 200:
                    all_activities = await response.json()

                    activities = []
                    for activity in all_activities:
                        start_time_str = activity["start_time"]

                        if "Z" in start_time_str or "+" in start_time_str:
                            start_time = datetime.fromisoformat(
                                start_time_str.replace("Z", "+00:00")
                            )
                        else:
                            start_time = datetime.fromisoformat(start_time_str).replace(
                                tzinfo=timezone.utc
                            )

                        if start_time <= end_time_utc:
                            activities.append(activity)

                    logger.info(
                        f"Fetched {len(activities)} upcoming activities within the next 2 days"
                    )
                    return activities
                else:
                    logger.error(f"API returned status {response.status}")
                    try:
                        error_text = await response.text()
                        logger.error(f"Response body: {error_text}")
                    except:
                        pass
                    return []
    except Exception as e:
        logger.error(f"Error fetching activities: {e}")
        return []


async def process_events(context=None):
    """Process activities and send reminders"""
    logger.info("Checking for upcoming activities...")

    activities = await fetch_activities()
    logger.info(f"Fetched {len(activities)} activities for processing")

    now_utc = datetime.now(timezone.utc)
    sent_count = 0

    for activity in activities:
        try:
            start_time_str = activity["start_time"]

            if "Z" in start_time_str or "+" in start_time_str:
                start_time = datetime.fromisoformat(
                    start_time_str.replace("Z", "+00:00")
                )
            else:
                start_time = datetime.fromisoformat(start_time_str).replace(
                    tzinfo=timezone.utc
                )

            reminder_minutes = activity.get("reminder_minutes")
            if reminder_minutes is None:
                reminder_minutes = 5

            reminder_time = start_time - timedelta(minutes=reminder_minutes)

            time_until_reminder = reminder_time - now_utc
            time_until_start = start_time - now_utc
            logger.debug(f"Activity: {activity.get('title')}")
            logger.debug(f"  Start time (UTC): {start_time}")
            logger.debug(f"  Reminder time (UTC): {reminder_time}")
            logger.debug(f"  Current time (UTC): {now_utc}")
            logger.debug(f"  Time until reminder: {time_until_reminder}")
            logger.debug(f"  Time until start: {time_until_start}")

            if (
                now_utc >= reminder_time
                and now_utc < start_time
                and not activity.get("reminder_sent", False)
            ):
                logger.info(
                    f"Sending reminder for activity {activity.get('id')}: {activity.get('title')}"
                )
                await send_reminder(activity, start_time)
                sent_count += 1

        except Exception as e:
            logger.error(
                f"Error processing activity {activity.get('id', 'unknown')}: {e}"
            )

    logger.info(f"Processed {len(activities)} activities, sent {sent_count} reminders")


async def send_reminder(activity, start_time):
    """Send a reminder message for an activity"""
    try:
        title = activity.get("title", "Unnamed activity")

        formatted_time = start_time.astimezone().strftime("%Y-%m-%d %H:%M")

        location = activity.get("location", "")
        location_text = f" at {location}" if location else ""

        message = f"📅 REMINDER: {title} starts at {formatted_time}{location_text}"

        if description := activity.get("description"):
            message += f"\n\n{description}"

        await reminderBot.send_message(chat_id="", text=message)  # needs to fix
        logger.info(f"Sent reminder for activity: {activity.get('id', 'unknown')}")

    except Exception as e:
        logger.error(f"Error sending reminder: {e}")
