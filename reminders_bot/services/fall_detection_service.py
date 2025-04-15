import logging
from datetime import datetime, timedelta, timezone
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton, Update
import aiohttp
from telegram.ext import ContextTypes


from utils.config import API_BASE_URL, REMINDERS_BOT_TOKEN
from reminders_bot.chat_registry import user_chat_map

logger = logging.getLogger(__name__)
fallBot = Bot(token=REMINDERS_BOT_TOKEN)


async def process_fall_alerts(context=None):
    """Check fall logs and send alerts if they are recent (within 5 mins)"""
    logger.info("Processing fall alerts...")

    logs = await fetch_fall_logs()
    sent_count = 0

    now_utc = datetime.now(timezone.utc)
    five_minutes_ago = now_utc - timedelta(minutes=5)

    for log in logs:
        try:
            status = log.get("status")
            if status not in ["pending", "confirmed"]:
                continue

            timestamp_str = log.get("timestamp")
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)

            if timestamp < five_minutes_ago:
                continue

            resident_id = log.get("resident_id", "unknown")
            acceleration = log.get("acceleration_magnitude", 0.0)

            for user_id, chat_id in user_chat_map.items():
                await send_fall_alert(
                    resident_id,
                    status,
                    timestamp,
                    acceleration,
                    chat_id,
                    fall_id=log.get("_id"),
                )
                sent_count += 1

        except Exception as e:
            logger.error(f"Error processing fall log {log.get('_id', 'unknown')}: {e}")

    logger.info(f"Sent {sent_count} fall alert(s)")


async def fetch_fall_logs():
    """Fetch fall logs"""
    try:
        async with aiohttp.ClientSession() as session:
            now_utc = datetime.now(timezone.utc)
            start_time = (now_utc - timedelta(minutes=5)).isoformat()

            url = f"{API_BASE_URL}/fall-detection/logs?start_after={start_time}"

            logger.info(f"Fetching fall logs after {start_time}")

            async with session.get(url) as response:
                if response.status == 200:
                    logs = await response.json()
                    logger.info(f"Fetched All {len(logs)} fall logs")
                    return logs
                else:
                    logger.error(f"API returned {response.status}")
                    return []
    except Exception as e:
        logger.error(f"Error fetching fall logs: {e}")
        return []


async def send_fall_alert(
    resident_id, status, timestamp, acceleration, chat_id, fall_id=None
):
    try:
        formatted_time = timestamp.astimezone().strftime("%Y-%m-%d %H:%M")
        resident_name = await get_resident_name(resident_id)

        message = (
            f"⚠️ *Fall Detected*\n"
            f"Resident: *{resident_name}*\n"
            f"Time: `{formatted_time}`\n"
            f"Acceleration: `{acceleration}`\n"
            f"Status: *{status.capitalize()}*"
        )

        if status == "pending" and fall_id:
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Confirmed", callback_data=f"confirm|{fall_id}"
                        ),
                        InlineKeyboardButton(
                            "🚫 False Alarm", callback_data=f"false|{fall_id}"
                        ),
                    ]
                ]
            )
            await fallBot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
        else:
            await fallBot.send_message(
                chat_id=chat_id, text=message, parse_mode="Markdown"
            )

        logger.info(f"Sent fall alert to chat {chat_id} for resident {resident_name}")

    except Exception as e:
        logger.error(f"Error sending fall alert to chat {chat_id}: {e}")


async def handle_fall_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    action, fall_id = data.split("|")

    new_status = "confirmed" if action == "confirm" else "false_positive"
    status_text = (
        "✅ Fall was Confirmed"
        if action == "confirm"
        else "🚫 Fall was marked as False Alarm"
    )

    try:
        async with aiohttp.ClientSession() as session:
            url = f"{API_BASE_URL}/fall-detection/log/{fall_id}/status?status={new_status}"
            response = await session.patch(url)

            if response.status == 200:
                await query.edit_message_reply_markup(None)
                await query.message.reply_text(status_text)
            else:
                await query.message.reply_text("⚠️ Failed to update fall status.")
    except Exception as e:
        logger.error(f"Error updating fall log status: {e}")
        await query.message.reply_text("❌ Error updating fall status.")


async def get_resident_name(resident_id: str) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{API_BASE_URL}/residents/{resident_id}"
            logger.info(f"Fetching resident name from: {url}")
            async with session.get(url) as response:
                if response.status == 200:
                    user = await response.json()
                    logger.info(f"Got resident data: {user}")
                    return user.get("full_name", resident_id)
                else:
                    logger.warning(
                        f"Resident fetch failed with status {response.status}"
                    )
                    return resident_id
    except Exception as e:
        logger.error(f"Error fetching resident name for {resident_id}: {e}")
        return resident_id
