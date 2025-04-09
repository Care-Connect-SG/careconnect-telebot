from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class MessageHandler:
    async def _handle_resident_query(self, update: Update, time_range: Dict[str, Any], filters: Dict[str, Any]) -> None:
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
                message = update.callback_query.message if update.callback_query else update.message
                suggestions = await self._get_resident_suggestions(resident_name)
                response = f"I couldn't find a resident named '{resident_name}'. {suggestions}"
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
                    InlineKeyboardButton("Show Today's Tasks", callback_data="today_tasks"),
                    InlineKeyboardButton("Show All Residents", callback_data="list_residents")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            message = update.callback_query.message if update.callback_query else update.message
            await message.reply_text(response, parse_mode="Markdown", reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error handling resident query: {str(e)}")
            message = update.callback_query.message if update.callback_query else update.message
            await message.reply_text(RESPONSE_TEMPLATES["error"])
            
    async def _get_resident_suggestions(self, query: str) -> str:
        """Generate helpful suggestions based on similar resident names"""
        try:
            # Try to find similar resident names
            similar_residents = await self.db.resident_collection.find(
                {"full_name": {"$regex": f".*{query}.*", "$options": "i"}},
                {"full_name": 1}
            ).limit(5).to_list(length=5)
            
            if similar_residents:
                suggestions = [res.get("full_name") for res in similar_residents]
                return f"Did you mean one of these residents?\n• " + "\n• ".join(suggestions)
            else:
                return "Please check the spelling or try another resident name."
        except Exception as e:
            logger.error(f"Error getting resident suggestions: {str(e)}")
            return "Please try with a different resident name."