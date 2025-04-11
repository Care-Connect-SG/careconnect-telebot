import logging
from typing import Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ..db.db_service import DatabaseService
from .query_handler import parse_query
from .response_handler import (
    format_task_response,
    format_activity_response,
    format_resident_response,
    RESPONSE_TEMPLATES,
)

logger = logging.getLogger(__name__)

db = None

user_context = {}


def init_handler(database_service: DatabaseService):
    global db
    db = database_service


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        message_text = update.message.text.strip().lower()

        await update.message.chat.send_action(action="typing")

        if user_id not in user_context:
            user_context[user_id] = {
                "last_query": None,
                "last_resident": None,
                "last_task_type": None,
                "last_time_range": None,
            }

        if is_follow_up_question(message_text, user_id):
            await handle_follow_up(update, user_id)
            return

        intent, params = parse_query(message_text)
        time_range = params.get("time_range", {})
        filters = params.get("filters", {})

        user_context[user_id].update(
            {
                "last_query": intent,
                "last_resident": filters.get("resident_name"),
                "last_task_type": filters.get("task_type"),
                "last_time_range": time_range,
            }
        )

        if intent == "task_query":
            await handle_task_query(update, time_range, filters)
        elif intent == "activity_query":
            await handle_activity_query(update, time_range, filters)
        elif intent == "resident_query":
            await handle_resident_query(update, time_range, filters)
        else:
            await handle_general_query(update)

    except Exception as e:
        logger.error(f"Error handling message: {str(e)}")
        await update.message.reply_text(RESPONSE_TEMPLATES["error"])


def is_follow_up_question(message: str, user_id: int) -> bool:
    follow_up_indicators = ["what about", "how about", "and", "also", "what else"]
    return any(indicator in message for indicator in follow_up_indicators)


async def handle_follow_up(update: Update, user_id: int) -> None:
    context = user_context[user_id]
    if not context["last_query"]:
        await handle_general_query(update)
        return

    time_range = context["last_time_range"] or {}
    filters = {
        "resident_name": context["last_resident"],
        "task_type": context["last_task_type"],
    }

    if context["last_query"] == "task_query":
        await handle_task_query(update, time_range, filters)
    elif context["last_query"] == "activity_query":
        await handle_activity_query(update, time_range, filters)
    elif context["last_query"] == "resident_query":
        await handle_resident_query(update, time_range, filters)


async def handle_task_query(
    update: Update, time_range: Dict[str, Any], filters: Dict[str, Any]
) -> None:
    try:
        query_filters = {}

        if time_range and "start_time" in time_range and "end_time" in time_range:
            if time_range["start_time"].date() == time_range["end_time"].date():
                today_start = time_range["start_time"].replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                today_end = time_range["end_time"].replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )

                logger.info(f"Today's date range: {today_start} to {today_end}")

                query_filters["$or"] = [
                    {"start_date": {"$gte": today_start, "$lte": today_end}},
                    {
                        "recurring": True,
                        "recurring_days": {"$in": [today_start.weekday()]},
                    },
                ]
            else:
                query_filters["start_date"] = {
                    "$gte": time_range["start_time"],
                    "$lte": time_range["end_time"],
                }

        query_filters.update(filters)

        tasks = await db.get_tasks(query_filters)

        if not tasks:
            message = (
                update.callback_query.message
                if update.callback_query
                else update.message
            )

            if filters.get("status") == "pending" and filters.get("due_date", {}).get(
                "$lt"
            ):
                response = "No overdue tasks found."
            else:
                response = "No tasks found matching your criteria."

            await message.reply_text(response, parse_mode="Markdown")
            return

        response = format_task_response(tasks)

        keyboard = [
            [
                InlineKeyboardButton(
                    "Show Overdue Tasks", callback_data="overdue_tasks"
                ),
                InlineKeyboardButton("Show Today's Tasks", callback_data="today_tasks"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = (
            update.callback_query.message if update.callback_query else update.message
        )
        await message.reply_text(
            response, parse_mode="Markdown", reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Error handling task query: {str(e)}")
        message = (
            update.callback_query.message if update.callback_query else update.message
        )
        await message.reply_text(RESPONSE_TEMPLATES["error"])


async def get_task_suggestions(filters: Dict[str, Any]) -> str:
    suggestions = []

    if filters.get("priority"):
        suggestions.append(
            "Try removing the priority filter or checking other priorities."
        )

    if filters.get("status"):
        suggestions.append("You might want to check tasks with different statuses.")

    if filters.get("assigned_to"):
        suggestions.append("Consider checking tasks assigned to other staff members.")

    if not suggestions:
        return ""

    return "Here are some suggestions:\n" + "\n".join(f"• {s}" for s in suggestions)


async def handle_activity_query(
    update: Update, time_range: Dict[str, Any], filters: Dict[str, Any]
) -> None:
    try:
        query_filters = {}

        if time_range and "start_time" in time_range and "end_time" in time_range:
            query_filters["$or"] = [
                {
                    "start_time": {
                        "$gte": time_range["start_time"],
                        "$lte": time_range["end_time"],
                    }
                },
                {
                    "end_time": {
                        "$gte": time_range["start_time"],
                        "$lte": time_range["end_time"],
                    }
                },
            ]

        query_filters.update(filters)

        activities = await db.get_activities(query_filters)

        response = format_activity_response(activities)
        await update.message.reply_text(response, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error handling activity query: {str(e)}")
        await update.message.reply_text(RESPONSE_TEMPLATES["error"])


async def handle_resident_query(
    update: Update, time_range: Dict[str, Any], filters: Dict[str, Any]
) -> None:
    try:
        resident_name = filters.get("resident_name", "")
        resident = await db.get_resident_by_name(resident_name)

        if not resident:
            message = (
                update.callback_query.message
                if update.callback_query
                else update.message
            )
            await message.reply_text(
                "No residents found matching your criteria.", parse_mode="Markdown"
            )
            return

        tasks = []
        if time_range:
            tasks = await db.get_resident_tasks(str(resident["_id"]), time_range)
        else:
            tasks = await db.get_resident_tasks(str(resident["_id"]))

        response = format_resident_response(resident, tasks)

        message = (
            update.callback_query.message if update.callback_query else update.message
        )
        await message.reply_text(response, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error handling resident query: {str(e)}")
        message = (
            update.callback_query.message if update.callback_query else update.message
        )
        await message.reply_text(RESPONSE_TEMPLATES["error"])


async def get_resident_suggestions(query: str) -> str:
    suggestions = []

    if len(query) < 3:
        suggestions.append("Try using a longer search term.")
    else:
        suggestions.append("Check for spelling errors in the name.")
        suggestions.append("Try searching for the resident's last name only.")
        suggestions.append("Try searching with fewer characters to get more results.")

    if not suggestions:
        return ""

    return "Here are some suggestions:\n" + "\n".join(f"• {s}" for s in suggestions)


async def handle_general_query(update: Update) -> None:
    help_text = (
        "I'm not sure what you're asking for. You can try:\n\n"
        "• Asking about tasks (e.g., 'What tasks are due today?')\n"
        "• Asking about residents (e.g., 'How is John Smith doing?')\n"
        "• Asking about activities (e.g., 'What activities are scheduled today?')\n\n"
        "Or try one of these commands:\n"
        "/residents - List all residents\n"
        "/tasks - Show today's tasks\n"
        "/help - Get more detailed help"
    )
    await update.message.reply_text(help_text)


async def list_all_residents(update: Update) -> None:
    try:
        residents = await db.resident_collection.find({}, {"full_name": 1}).to_list(
            length=50
        )

        if not residents:
            message = (
                update.callback_query.message
                if update.callback_query
                else update.message
            )
            await message.reply_text("No residents found in the database.")
            return

        response = "👵👴 Resident List:\n\n"
        for idx, resident in enumerate(residents, start=1):
            name = resident.get("full_name", "Unnamed")
            response += f"{idx}. {name}\n"

        message = (
            update.callback_query.message if update.callback_query else update.message
        )
        await message.reply_text(response)
        logger.info(f"Sent list of {len(residents)} residents")

    except Exception as e:
        logger.error(f"Error listing residents: {str(e)}")
        message = (
            update.callback_query.message if update.callback_query else update.message
        )
        await message.reply_text(
            "Sorry, I couldn't retrieve the resident list. Please try again later."
        )
