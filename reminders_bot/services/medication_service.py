import logging
from uuid import uuid4
import aiohttp
from pytz import timezone
from datetime import datetime
from telegram import Bot
from dateutil import parser


from utils.config import API_BASE_URL, REMINDERS_BOT_TOKEN
from reminders_bot.chat_registry import user_chat_map, user_name_map

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

reminderBot = Bot(token=REMINDERS_BOT_TOKEN)

sg = timezone("Asia/Singapore")


async def fetch_residents(user_name):
    """Fetch residents for the current user

    Args:
        user_name: Name of the current user
    """
    try:
        async with aiohttp.ClientSession() as session:
            residents_url = (
                f"{API_BASE_URL}/residents/getAllResidents?caregiver_name={user_name}"
            )

            logger.info(f"Fetching residents for {user_name}")

            async with session.get(residents_url) as response:
                if response.status == 200:
                    residents = await response.json()

                    logger.info(f"Fetched {len(residents)} residents for {user_name}")
                    return residents
                else:
                    logger.error(f"API returned status {response.status}")
                    try:
                        error_text = await response.text()
                        logger.error(f"Response body: {error_text}")
                    except:
                        pass
                    return []
    except Exception as e:
        logger.error(f"Error fetching residents: {e}")
        return []


async def fetch_medications(resident_id):
    """Fetch medications for the resident

    Args:
        resident_id: ID of the resident
    """
    try:
        async with aiohttp.ClientSession() as session:
            now_sg = datetime.now(sg)

            current_date = now_sg.strftime("%Y-%m-%d")

            medications_url = f"{API_BASE_URL}/residents/{resident_id}/medications"

            logger.info(f"Fetching medications for resident {resident_id}")

            async with session.get(medications_url) as response:
                if response.status == 200:
                    medications = await response.json()

                    logger.info(
                        f"Fetched {len(medications)} medications for resident {resident_id}"
                    )

                    current_medications = [
                        m
                        for m in medications
                        if m.get("start_date") <= current_date
                        and m.get("end_date") > current_date
                    ]

                    reminder_medications = [
                        m
                        for m in current_medications
                        if m.get("schedule_type") != "custom"
                    ]

                    return reminder_medications
                else:
                    logger.error(f"API returned status {response.status}")
                    try:
                        error_text = await response.text()
                        logger.error(f"Response body: {error_text}")
                    except:
                        pass
                    return []
    except Exception as e:
        logger.error(f"Error fetching medications: {e}")
        return []


async def schedule_medication_reminders(scheduler, context=None):
    """Fetch medications and schedule reminders

    Args:
        scheduler: The scheduler to use for scheduling reminders
    """
    logger.info("Checking for upcoming medication administration for all users...")

    now_sg = datetime.now(sg)

    for user_id, chat_id in user_chat_map.items():
        user_name = user_name_map[user_id]
        logger.info(f"Checking medication administrations for {user_name} ({user_id})")

        residents = await fetch_residents(user_name)
        medications = []

        for res in residents:
            try:
                medications = await fetch_medications(res.get("id"))

                logger.info(f"Processing medications for {res.get('full_name')}")

                for med in medications:
                    start_date = parser.parse(med.get("start_date"))
                    if start_date.tzinfo is None:
                        start_date = start_date.replace(tzinfo=sg)
                    logger.info(
                        f"Processing medication {med.get('medication_name')} for resident {res.get('full_name')}"
                    )

                    if med.get("schedule_type") == "day":
                        repeat_interval = med.get("repeat")
                        remainder = (now_sg - start_date).days % repeat_interval

                        if remainder == 0:
                            logger.info(
                                f"Queing medication reminder for {res.get('full_name')}-{med.get('medication_name')} to user {user_id}"
                            )
                            await queue_medication_reminder(
                                res, med, chat_id, scheduler
                            )

                    elif med.get("schedule_type") == "week":
                        repeat_interval = med.get("repeat")
                        start_week = start_date.isocalendar()[1]
                        current_week = now_sg.isocalendar()[1]
                        remainder = (current_week - start_week) % repeat_interval
                        today = datetime.now(sg).strftime("%a")

                        if remainder == 0 and today in med.get("days_of_week"):
                            logger.info(
                                f"Queing medication reminder for {res.get('full_name')}-{med.get('medication_name')} to user {user_id}"
                            )
                            await queue_medication_reminder(
                                res, med, chat_id, scheduler
                            )

            except Exception as e:
                logger.error(
                    f"Error processing medications for resident {res.get('full_name', 'unknown')}: {e}"
                )

    logger.info(f"Processed medications reminders for all users")


async def queue_medication_reminder(resident, medication, chat_id, scheduler):
    """Schedule a reminder message for a medication to a specific chat

    Args:
        resident: The resident that the medication is for
        medication: The medication
        chat_id: The Telegram chat ID to send the reminder to
    """
    try:
        for time in medication.get("times_of_day", []):
            hour = time.get("hour")
            minute = time.get("minute")

            now_sg = datetime.now(sg)
            reminder_time = now_sg.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )

            title = f"🔔 [{hour}:{minute}] {medication.get('medication_name')} for {resident.get('full_name')}"
            reminder = "Please administer the following medication:"
            med_name = f"💊 Medication: {medication.get('medication_name')}"
            dosage = f"🩺 Dosage: {medication.get('dosage')}"
            instructions = ""
            if resident.get("gender") == "Male":
                res_name = f"👴 Resident: {resident.get('full_name')}"
            else:
                res_name = f"👵 Resident: {resident.get('full_name')}"

            if medication.get("instructions"):
                instructions = f"📝 Instructions: {medication.get('instructions')}"

            message = (
                title
                + "\n\n"
                + reminder
                + "\n\n"
                + res_name
                + "\n"
                + med_name
                + "\n"
                + dosage
                + "\n"
                + instructions
            )

            logger.info("Medication Reminder Message Scheduled: \n", message)

            scheduler.add_job(
                send_medication_reminder,
                "date",
                run_date=reminder_time,
                args=[message, chat_id],
                id=f"med_{uuid4()}",
            )

    except Exception as e:
        logger.error(f"Error queuing medication reminder: {e}")


async def send_medication_reminder(reminder, chat_id):
    """Send a reminder message for a medication to a specific chat

    Args:
        reminder: The medication reminder to send
        chat_id: The Telegram chat ID to send the reminder to
    """
    try:
        await reminderBot.send_message(chat_id=chat_id, text=reminder)
        logger.info(f"Sent medication reminder: {reminder} to chat {chat_id}")

    except Exception as e:
        logger.error(f"Error sending task reminder: {e}")
