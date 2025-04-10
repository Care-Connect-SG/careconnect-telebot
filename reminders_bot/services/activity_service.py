import logging
import aiohttp
from datetime import datetime, timedelta, timezone
from telegram import Bot

from utils.config import API_BASE_URL, REMINDERS_BOT_TOKEN
from reminders_bot.chat_registry import user_chat_map

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

reminderBot = Bot(token=REMINDERS_BOT_TOKEN)


async def fetch_activities(user_id=None):
    """Fetch upcoming activities that might need reminders soon

    Args:
        user_id: Optional user ID to filter activities by creator
    """
    try:
        async with aiohttp.ClientSession() as session:
            now_utc = datetime.now(timezone.utc)

            end_time_utc = now_utc + timedelta(days=2)

            start_date_param = now_utc.strftime("%Y-%m-%dT%H:%M:%S")

            url = f"{API_BASE_URL}/activities/?start_date={start_date_param}&sort_by=start_time&sort_order=asc"

            if user_id:
                url += f"&created_by={user_id}"

            logger.info(
                f"Fetching activities starting after {start_date_param}"
                + (f" for user {user_id}" if user_id else "")
            )

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
                        + (f" for user {user_id}" if user_id else "")
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
    logger.info("Checking for upcoming activities for all users...")

    now_utc = datetime.now(timezone.utc)
    sent_count = 0

    for user_id, chat_id in user_chat_map.items():
        logger.info(f"Checking activities for user {user_id}")

        activities = await fetch_activities(user_id)
        logger.info(f"Fetched {len(activities)} activities for user {user_id}")

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
                        f"Sending reminder for activity {activity.get('id')}: {activity.get('title')} to user {user_id}"
                    )
                    await send_reminder(activity, start_time, chat_id)
                    sent_count += 1

            except Exception as e:
                logger.error(
                    f"Error processing activity {activity.get('id', 'unknown')}: {e}"
                )

    logger.info(
        f"Processed activities for {len(user_chat_map)} users, sent {sent_count} reminders"
    )


async def send_reminder(activity, start_time, chat_id):
    """Send a reminder message for an activity to a specific chat

    Args:
        activity: The activity data dict
        start_time: The parsed start time datetime
        chat_id: The Telegram chat ID to send the reminder to
    """
    try:
        title = activity.get("title", "Unnamed activity")

        formatted_start_time = start_time.astimezone().strftime("%Y-%m-%d %H:%M")

        end_time_str = activity.get("end_time")
        if end_time_str:
            if "Z" in end_time_str or "+" in end_time_str:
                end_time = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
            else:
                end_time = datetime.fromisoformat(end_time_str).replace(
                    tzinfo=timezone.utc
                )

            formatted_end_time = end_time.astimezone().strftime("%Y-%m-%d %H:%M")
            time_display = f"from {formatted_start_time} to {formatted_end_time}"
        else:
            time_display = f"at {formatted_start_time}"

        location = activity.get("location", "")
        location_text = f" at {location}" if location else ""

        message = f"📅 REMINDER: {title} starts {time_display}{location_text}"

        if description := activity.get("description"):
            message += f"\n\n{description}"

        await reminderBot.send_message(chat_id=chat_id, text=message)
        logger.info(
            f"Sent reminder for activity: {activity.get('id', 'unknown')} to chat {chat_id}"
        )

        await mark_reminder_sent(activity["id"])

    except Exception as e:
        logger.error(f"Error sending reminder: {e}")


async def mark_reminder_sent(activity_id):
    url = f"{API_BASE_URL}/activities/{activity_id}/mark_reminder_sent"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.patch(url) as response:
                if response.status == 200:
                    logger.info(f"Marked activity {activity_id} as reminder_sent")

        except Exception as e:
            logger.warning(f"Failed to mark reminder sent for {activity_id}")
            logger.error(f"Error marking reminder as sent: {e}")
