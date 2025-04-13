import logging
from datetime import datetime, timedelta, timezone
from telegram import Bot
import aiohttp

from utils.config import API_BASE_URL, REMINDERS_BOT_TOKEN
from reminders_bot.chat_registry import user_chat_map

logger = logging.getLogger(__name__)
fallBot = Bot(token=REMINDERS_BOT_TOKEN)


async def fetch_fall_logs():
    """Fetch fall logs that occurred within the last 5 minutes"""
    try:
        async with aiohttp.ClientSession() as session:
            now_utc = datetime.now(timezone.utc)
            start_time = (now_utc - timedelta(minutes=5)).isoformat()

            url = f"{API_BASE_URL}/fall-detection/logs?start_after={start_time}"

            logger.info(f"Fetching fall logs after {start_time}")

            async with session.get(url) as response:
                if response.status == 200:
                    logs = await response.json()
                    logger.info(f"Fetched {len(logs)} fall logs from the last 5 minutes")
                    return logs
                else:
                    logger.error(f"API returned {response.status}")
                    return []
    except Exception as e:
        logger.error(f"Error fetching fall logs: {e}")
        return []


async def process_fall_alerts(context=None):
    """Check fall logs and send alerts if necessary"""
    logger.info("Processing fall alerts...")

    logs = await fetch_fall_logs()
    sent_count = 0

    for log in logs:
        try:
            status = log.get("status")
            if status not in ["pending", "confirmed"]:
                continue

            # Optional check: you can add a `alert_sent` field in your DB later
            if log.get("alert_sent", False):
                continue

            timestamp_str = log.get("timestamp")
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

            resident_id = log.get("resident_id", "unknown")
            acceleration = log.get("acceleration_magnitude", 0.0)

            # Send to all mapped chat IDs (e.g., admins/nurses)
            for user_id, chat_id in user_chat_map.items():
                await send_fall_alert(resident_id, status, timestamp, acceleration, chat_id)
                sent_count += 1

            # Optionally mark the log as notified
            await mark_fall_notified(log["_id"])

        except Exception as e:
            logger.error(f"Error processing fall log {log.get('_id', 'unknown')}: {e}")

    logger.info(f"Sent {sent_count} fall alert(s)")


async def send_fall_alert(resident_id, status, timestamp, acceleration, chat_id):
    try:
        formatted_time = timestamp.astimezone().strftime("%Y-%m-%d %H:%M")

        if status == "pending":
            message = (
                f"⚠️ *Fall Detected*\n"
                f"Resident: `{resident_id}`\n"
                f"Time: `{formatted_time}`\n"
                f"Acceleration: `{acceleration}`\n"
                f"Status: *Pending Review*"
            )
        else:
            message = (
                f"✅ *Fall Confirmed*\n"
                f"Resident: `{resident_id}`\n"
                f"Time: `{formatted_time}`\n"
                f"Acceleration: `{acceleration}`\n"
                f"Status: *Confirmed Fall*"
            )

        await fallBot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
        logger.info(f"Sent fall alert to chat {chat_id} for resident {resident_id}")

    except Exception as e:
        logger.error(f"Error sending fall alert to chat {chat_id}: {e}")

