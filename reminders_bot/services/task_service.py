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


async def fetch_tasks(user_id=None):
    """Fetch upcoming tasks that might need reminders soon

    Args:
        user_id: Optional user ID to filter tasks by creator
    """
    try:
        async with aiohttp.ClientSession() as session:
            now_utc = datetime.now(timezone.utc)

            # Current date
            current_date = now_utc.strftime("%Y-%m-%d")

            # Date 2 days from now
            future_date = (now_utc + timedelta(days=2)).strftime("%Y-%m-%d")

            # Use both dates as a range
            url = f"{API_BASE_URL}/tasks/telegram?start_date={current_date}&end_date={future_date}"

            if user_id:
                url += f"&assigned_to={user_id}"

            logger.info(f"Fetching tasks from {current_date} to {future_date}" +
                       (f" for user {user_id}" if user_id else ""))

            async with session.get(url) as response:
                if response.status == 200:
                    tasks = await response.json()

                    logger.info(
                        f"Fetched {len(tasks)} tasks" +
                        (f" for user {user_id}" if user_id else "")
                    )
                    return tasks
                else:
                    logger.error(f"API returned status {response.status}")
                    try:
                        error_text = await response.text()
                        logger.error(f"Response body: {error_text}")
                    except:
                        pass
                    return []
    except Exception as e:
        logger.error(f"Error fetching tasks: {e}")
        return []

async def process_task_reminders(context=None):
    """Process tasks and send reminders"""
    logger.info("Checking for upcoming tasks for all users...")

    now_utc = datetime.now(timezone.utc)
    sent_count = 0

    for user_id, chat_id in user_chat_map.items():
        logger.info(f"Checking tasks for user {user_id}")

        tasks = await fetch_tasks(user_id)
        logger.info(f"Fetched {len(tasks)} tasks for user {user_id}")

        for task in tasks:
            try:
                start_time_str = task["start_date"]

                if isinstance(start_time_str, str):
                    if "Z" in start_time_str or "+" in start_time_str:
                        start_time = datetime.fromisoformat(
                            start_time_str.replace("Z", "+00:00")
                        )
                    else:
                        start_time = datetime.fromisoformat(start_time_str).replace(
                            tzinfo=timezone.utc
                        )
                else:
                    start_time = start_time_str

                remind_prior = task.get("remind_prior")
                if remind_prior is None:
                    remind_prior = 5

                reminder_time = start_time - timedelta(minutes=remind_prior)

                time_until_reminder = reminder_time - now_utc
                time_until_start = start_time - now_utc

                logger.debug(f"Task: {task.get('task_title')}")
                logger.debug(f"  Start time (UTC): {start_time}")
                logger.debug(f"  Reminder time (UTC): {reminder_time}")
                logger.debug(f"  Current time (UTC): {now_utc}")
                logger.debug(f"  Time until reminder: {time_until_reminder}")
                logger.debug(f"  Time until start: {time_until_start}")

                # Check if it's time to send a reminder and the reminder hasn't been sent yet
                if (
                    now_utc >= reminder_time
                    and now_utc < start_time
                    and not task.get("reminder_sent", False)
                ):
                    logger.info(
                        f"Sending reminder for task {task.get('id')}: {task.get('task_title')} to user {user_id}"
                    )
                    await send_task_reminder(task, start_time, chat_id)
                    sent_count += 1

            except Exception as e:
                logger.error(
                    f"Error processing task {task.get('id', 'unknown')}: {e}"
                )

    logger.info(f"Processed tasks for {len(user_chat_map)} users, sent {sent_count} reminders")

async def send_task_reminder(task, start_time, chat_id):
    """Send a reminder message for a task to a specific chat

    Args:
        task: The task data dict
        start_time: The parsed start time datetime
        chat_id: The Telegram chat ID to send the reminder to
    """
    try:
        title = task.get("task_title", "Unnamed task")

        formatted_start_time = start_time.astimezone().strftime("%Y-%m-%d %H:%M")

        due_time_str = task.get("due_date")
        if due_time_str:
            if isinstance(due_time_str, str):
                if "Z" in due_time_str or "+" in due_time_str:
                    due_time = datetime.fromisoformat(
                        due_time_str.replace("Z", "+00:00")
                    )
                else:
                    due_time = datetime.fromisoformat(due_time_str).replace(
                        tzinfo=timezone.utc
                    )
            else:
                due_time = due_time_str

            formatted_due_time = due_time.astimezone().strftime("%Y-%m-%d %H:%M")
            time_display = f"from {formatted_start_time} to {formatted_due_time}"
        else:
            time_display = f"at {formatted_start_time}"

        resident = task.get("resident_name", "")
        resident_text = f" for {resident}" if resident else ""

        priority = task.get("priority", "")
        priority_text = f" [{priority}]" if priority else ""

        room = task.get("resident_room", "")
        room_text = f" (Room: {room})" if room else ""

        details = task.get("task_details", "")
        details_text = f"\n\n{details}" if details else ""

        message = f"📋 TASK REMINDER{priority_text}: {title} {time_display}{resident_text}{room_text}{details_text}"

        await reminderBot.send_message(chat_id=chat_id, text=message)
        logger.info(f"Sent reminder for task: {task.get('id', 'unknown')} to chat {chat_id}")

        await mark_task_reminder_sent(task["id"])

    except Exception as e:
        logger.error(f"Error sending task reminder: {e}")


async def mark_task_reminder_sent(task_id):
    """Mark a task reminder as sent in the backend"""
    url = f"{API_BASE_URL}/tasks/{task_id}/mark_reminder_sent"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.patch(url) as response:
                if response.status == 200:
                    logger.info(f"Marked task {task_id} as reminder_sent")
                else:
                    logger.error(f"Failed to mark task reminder sent. Status: {response.status}")
                    try:
                        error_text = await response.text()
                        logger.error(f"Response error: {error_text}")
                    except:
                        pass

        except Exception as e:
            logger.warning(f"Failed to mark reminder sent for task {task_id}")
            logger.error(f"Error marking reminder as sent: {e}")
