import logging
from typing import Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ..services.database import DatabaseService
from .query_handler import QueryParser
from .response_handler import ResponseFormatter, RESPONSE_TEMPLATES

logger = logging.getLogger(__name__)


class MessageHandler:
    def __init__(self):
        self.db = DatabaseService()
        self.parser = QueryParser()
        self.formatter = ResponseFormatter()
        self.user_context = {}  # Store user context for better conversations

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle incoming messages with enhanced NLP and context awareness"""
        try:
            user_id = update.effective_user.id
            message_text = update.message.text.strip().lower()

            # Send typing action to indicate the bot is processing
            await update.message.chat.send_action(action="typing")

            # Initialize user context if not exists
            if user_id not in self.user_context:
                self.user_context[user_id] = {
                    "last_query": None,
                    "last_resident": None,
                    "last_task_type": None,
                    "last_time_range": None,
                }

            # Check for follow-up questions
            if self._is_follow_up_question(message_text, user_id):
                await self._handle_follow_up(update, user_id)
                return

            # Parse the query to determine intent and extract parameters
            intent, params = self.parser.parse_query(message_text)
            time_range = params.get("time_range", {})
            filters = params.get("filters", {})

            # Update user context
            self.user_context[user_id].update(
                {
                    "last_query": intent,
                    "last_resident": filters.get("resident_name"),
                    "last_task_type": filters.get("task_type"),
                    "last_time_range": time_range,
                }
            )

            # Handle based on intent
            if intent == "task_query":
                await self._handle_task_query(update, time_range, filters)
            elif intent == "activity_query":
                await self._handle_activity_query(update, time_range, filters)
            elif intent == "resident_query":
                await self._handle_resident_query(update, time_range, filters)
            else:
                await self._handle_general_query(update)

        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            await update.message.reply_text(RESPONSE_TEMPLATES["error"])

    def _is_follow_up_question(self, message: str, user_id: int) -> bool:
        """Check if the message is a follow-up question"""
        follow_up_indicators = ["what about", "how about", "and", "also", "what else"]
        return any(indicator in message for indicator in follow_up_indicators)

    async def _handle_follow_up(self, update: Update, user_id: int) -> None:
        """Handle follow-up questions using context"""
        context = self.user_context[user_id]
        if not context["last_query"]:
            await self._handle_general_query(update)
            return

        # Reuse last query parameters with updated time range if needed
        time_range = context["last_time_range"] or {}
        filters = {
            "resident_name": context["last_resident"],
            "task_type": context["last_task_type"],
        }

        if context["last_query"] == "task_query":
            await self._handle_task_query(update, time_range, filters)
        elif context["last_query"] == "activity_query":
            await self._handle_activity_query(update, time_range, filters)
        elif context["last_query"] == "resident_query":
            await self._handle_resident_query(update, time_range, filters)

    async def _handle_task_query(
        self, update: Update, time_range: Dict[str, Any], filters: Dict[str, Any]
    ) -> None:
        """Handle task-related queries with enhanced filtering and suggestions"""
        try:
            # Prepare MongoDB query
            query_filters = {}

            # Time-based filters
            if time_range and "start_time" in time_range and "end_time" in time_range:
                # For today's tasks, we want to show both one-time tasks and recurring tasks
                if time_range["start_time"].date() == time_range["end_time"].date():
                    # Always use the full day range for today's tasks
                    today_start = time_range["start_time"].replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    today_end = time_range["end_time"].replace(
                        hour=23, minute=59, second=59, microsecond=999999
                    )

                    # Debug the date range
                    logger.info(f"Today's date range: {today_start} to {today_end}")

                    query_filters["$or"] = [
                        {"start_date": {"$gte": today_start, "$lte": today_end}},
                        {
                            "recurring": True,
                            "recurring_days": {"$in": [today_start.weekday()]},
                        },
                    ]
                else:
                    # For other time ranges, only show one-time tasks
                    query_filters["start_date"] = {
                        "$gte": time_range["start_time"],
                        "$lte": time_range["end_time"],
                    }

            # Add other filters
            query_filters.update(filters)

            # Get tasks based on filters
            tasks = await self.db.get_tasks(query_filters)

            if not tasks:
                # Provide suggestions based on the query
                suggestions = await self._get_task_suggestions(filters)
                response = (
                    f"I couldn't find any tasks matching your criteria. {suggestions}"
                )
                message = (
                    update.callback_query.message
                    if update.callback_query
                    else update.message
                )
                await message.reply_text(response, parse_mode="Markdown")
                return

            # Format and send response
            response = self.formatter.format_task_response(tasks)

            # Add interactive buttons for common follow-up actions
            keyboard = [
                [
                    InlineKeyboardButton(
                        "Show Overdue Tasks", callback_data="overdue_tasks"
                    ),
                    InlineKeyboardButton(
                        "Show Today's Tasks", callback_data="today_tasks"
                    ),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            message = (
                update.callback_query.message
                if update.callback_query
                else update.message
            )
            await message.reply_text(
                response, parse_mode="Markdown", reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error handling task query: {str(e)}")
            message = (
                update.callback_query.message
                if update.callback_query
                else update.message
            )
            await message.reply_text(RESPONSE_TEMPLATES["error"])

    async def _get_task_suggestions(self, filters: Dict[str, Any]) -> str:
        """Generate helpful suggestions based on the query filters"""
        suggestions = []

        if filters.get("priority"):
            suggestions.append(
                "Try removing the priority filter or checking other priorities."
            )

        if filters.get("status"):
            suggestions.append("You might want to check tasks with different statuses.")

        if filters.get("assigned_to"):
            suggestions.append(
                "Consider checking tasks assigned to other staff members."
            )

        return "Here are some suggestions:\n" + "\n".join(f"• {s}" for s in suggestions)

    async def _handle_activity_query(
        self, update: Update, time_range: Dict[str, Any], filters: Dict[str, Any]
    ) -> None:
        """Handle activity-related queries"""
        try:
            # Prepare MongoDB query
            query_filters = {}

            # Time-based filters
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

            # Add other filters
            query_filters.update(filters)

            # Get activities based on filters
            activities = await self.db.get_activities(query_filters)

            # Format and send response
            response = self.formatter.format_activity_response(activities)
            await update.message.reply_text(response, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error handling activity query: {str(e)}")
            await update.message.reply_text(RESPONSE_TEMPLATES["error"])

    async def _handle_resident_query(
        self, update: Update, time_range: Dict[str, Any], filters: Dict[str, Any]
    ) -> None:
        """Handle resident-related queries"""
        try:
            # Extract resident name from filters
            resident_name = filters.get("resident_name", "")
            logger.info(f"Searching for resident with name: '{resident_name}'")

            if not resident_name:
                # If no resident name specified, list all residents
                await self.list_all_residents(update)
                return

            # Get resident by name using the service method
            resident = await self.db.get_resident_by_name(resident_name)

            if not resident:
                logger.info(f"No resident found with name: '{resident_name}'")
                message = (
                    update.callback_query.message
                    if update.callback_query
                    else update.message
                )
                suggestions = await self._get_resident_suggestions(resident_name)
                response = (
                    f"I couldn't find a resident named '{resident_name}'. {suggestions}"
                )
                await message.reply_text(response)
                return

            logger.info(f"Found resident: {resident.get('full_name')}")

            # Get tasks for the resident
            resident_id = str(resident["_id"])
            tasks = await self.db.get_resident_tasks(resident_id, time_range)

            # Format and send response
            response = self.formatter.format_resident_response(resident, tasks, True)

            # Add interactive buttons for common follow-up actions
            keyboard = [
                [
                    InlineKeyboardButton(
                        "Show Today's Tasks", callback_data="today_tasks"
                    ),
                    InlineKeyboardButton(
                        "Show All Residents", callback_data="list_residents"
                    ),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            message = (
                update.callback_query.message
                if update.callback_query
                else update.message
            )
            await message.reply_text(
                response, parse_mode="Markdown", reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error handling resident query: {str(e)}")
            message = (
                update.callback_query.message
                if update.callback_query
                else update.message
            )
            await message.reply_text(RESPONSE_TEMPLATES["error"])

    async def _get_resident_suggestions(self, query: str) -> str:
        """Generate helpful suggestions based on similar resident names"""
        try:
            # Try to find similar resident names
            similar_residents = (
                await self.db.resident_collection.find(
                    {"full_name": {"$regex": f".*{query}.*", "$options": "i"}},
                    {"full_name": 1},
                )
                .limit(5)
                .to_list(length=5)
            )

            if similar_residents:
                suggestions = [res.get("full_name") for res in similar_residents]
                return f"Did you mean one of these residents?\n• " + "\n• ".join(
                    suggestions
                )
            else:
                return "Please check the spelling or try another resident name."
        except Exception as e:
            logger.error(f"Error getting resident suggestions: {str(e)}")
            return "Please try with a different resident name."

    async def _handle_general_query(self, update: Update) -> None:
        """Handle general queries or unknown commands"""
        help_text = (
            "I'm not sure how to help with that. You can ask me about:\n\n"
            "*Tasks:*\n"
            "• What tasks are due today?\n"
            "• Show me all high priority tasks\n"
            "• Any overdue tasks?\n\n"
            "*Residents:*\n"
            "• How is [resident name] doing?\n"
            "• What happened to [resident name] today?\n"
            "• Show tasks for [resident name]\n\n"
            "*Activities:*\n"
            "• What activities are scheduled today?\n"
            "• Show me activities for this week\n"
            "• Any activities in [location]?\n\n"
            "Type /help for more information."
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def list_all_residents(self, update: Update) -> None:
        """List all residents with enhanced formatting and quick actions"""
        try:
            # Get all residents with more details
            residents = await self.db.resident_collection.find(
                {},
                {
                    "full_name": 1,
                    "room_number": 1,
                    "medical_conditions": 1,
                    "medications": 1,
                },
            ).to_list(length=50)

            if not residents:
                message = (
                    update.callback_query.message
                    if update.callback_query
                    else update.message
                )
                await message.reply_text("No residents found in the database.")
                return

            # Format response
            response = "👵👴 *Resident List:*\n\n"
            for idx, resident in enumerate(residents, start=1):
                name = resident.get("full_name", "Unnamed")
                room = resident.get("room_number", "No room")
                conditions = resident.get("medical_conditions", [])
                meds = resident.get("medications", [])

                response += f"{idx}. {name} (Room: {room})\n"
                if conditions:
                    response += f"   Conditions: {', '.join(conditions)}\n"
                if meds:
                    response += f"   Medications: {', '.join(meds)}\n"
                response += "\n"

            # Add quick action button for tasks
            keyboard = [
                [
                    InlineKeyboardButton(
                        "Show Today's Tasks", callback_data="today_tasks"
                    ),
                    InlineKeyboardButton(
                        "Show Overdue Tasks", callback_data="overdue_tasks"
                    ),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            message = (
                update.callback_query.message
                if update.callback_query
                else update.message
            )
            await message.reply_text(
                response, parse_mode="Markdown", reply_markup=reply_markup
            )
            logger.info(f"Sent list of {len(residents)} residents")
        except Exception as e:
            logger.error(f"Error listing residents: {str(e)}")
            message = (
                update.callback_query.message
                if update.callback_query
                else update.message
            )
            await message.reply_text(RESPONSE_TEMPLATES["error"])
