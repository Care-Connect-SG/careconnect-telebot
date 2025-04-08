import logging
from typing import List, Dict, Any
from datetime import datetime

from ..config import MAX_MESSAGE_LENGTH, RESPONSE_TEMPLATES

logger = logging.getLogger(__name__)


class ResponseFormatter:
    def __init__(self):
        self.max_length = MAX_MESSAGE_LENGTH

    def format_task_response(self, tasks: List[Dict[str, Any]]) -> str:
        """Format tasks for the response"""
        if not tasks:
            return RESPONSE_TEMPLATES["no_results"]

        response = f"📋 *Found {len(tasks)} tasks:*\n\n"

        for idx, task in enumerate(tasks[:10], start=1):
            title = task.get("task_title", "Untitled Task")
            status = task.get("status", "Unknown")
            priority = task.get("priority", "")
            assigned_to = task.get("assigned_to_name", "Unassigned")
            assigned_for = task.get("assigned_for_name", "Not specified")

            start_date = task.get("start_date")
            due_date = task.get("due_date")

            date_str = ""
            if start_date:
                date_str = f"{self._format_datetime(start_date)}"
            if due_date:
                date_str += f" to {self._format_datetime(due_date)}"

            response += (
                f"{idx}. *{title}*\n"
                f"   Status: {status} | Priority: {priority}\n"
                f"   For: {assigned_for} | By: {assigned_to}\n"
                f"   Time: {date_str}\n\n"
            )

        if len(tasks) > 10:
            response += f"...and {len(tasks) - 10} more tasks (showing first 10 only)."

        return self._truncate_response(response)

    def format_activity_response(self, activities: List[Dict[str, Any]]) -> str:
        """Format activities for the response"""
        if not activities:
            return RESPONSE_TEMPLATES["no_results"]

        response = f"🗓️ *Found {len(activities)} activities:*\n\n"

        for idx, activity in enumerate(activities[:10], start=1):
            title = activity.get("title", "Untitled Activity")
            location = activity.get("location", "No location")
            category = activity.get("category", "Uncategorized")
            created_by = activity.get("created_by_name", "Unknown")

            start_time = activity.get("start_time")
            end_time = activity.get("end_time")

            time_str = ""
            if start_time:
                time_str = f"{self._format_datetime(start_time)}"
            if end_time:
                time_str += f" to {self._format_datetime(end_time)}"

            response += (
                f"{idx}. *{title}*\n"
                f"   Category: {category} | Location: {location}\n"
                f"   Created by: {created_by}\n"
                f"   Time: {time_str}\n\n"
            )

        if len(activities) > 10:
            response += f"...and {len(activities) - 10} more activities (showing first 10 only)."

        return self._truncate_response(response)

    def format_resident_response(self, resident, tasks, is_general_query=False) -> str:
        """Format resident info for the response"""
        # Check if resident is a list or a single dict
        if isinstance(resident, list):
            # Multiple residents
            if not resident:
                return RESPONSE_TEMPLATES["resident_not_found"]

            response = f"👥 *Found {len(resident)} residents:*\n\n"
            for idx, res in enumerate(resident[:10], start=1):
                full_name = res.get("full_name", "Unknown")
                room_number = res.get("room_number", "Unknown")
                response += f"{idx}. *{full_name}* (Room: {room_number})\n\n"

            if len(resident) > 10:
                response += f"...and {len(resident) - 10} more residents (showing first 10 only)."

            return self._truncate_response(response)

        # Single resident
        if not resident:
            return RESPONSE_TEMPLATES["resident_not_found"]

        full_name = resident.get("full_name", "Unknown")
        room_number = resident.get("room_number", "Unknown")

        # Add more resident details
        medical_conditions = resident.get("medical_conditions", [])
        medications = resident.get("medications", [])
        notes = resident.get("notes", "")

        response = f"👤 *Resident Profile: {full_name}*\n"
        response += f"Room: {room_number}\n"

        if medical_conditions:
            response += f"Medical Conditions: {', '.join(medical_conditions)}\n"

        if medications:
            response += f"Medications: {', '.join(medications)}\n"

        if notes:
            response += f"Notes: {notes}\n"

        response += "\n"

        # Add task information
        if tasks:
            response += f"*Recent tasks for {full_name}:*\n\n"

            for idx, task in enumerate(tasks[:5], start=1):
                title = task.get("task_title", "Untitled Task")
                status = task.get("status", "Unknown")
                assigned_to = task.get("assigned_to_name", "Unassigned")

                # Get datetime information
                start_date = task.get("start_date")
                date_str = (
                    self._format_datetime(start_date) if start_date else "Unknown"
                )

                response += (
                    f"{idx}. *{title}*\n"
                    f"   Status: {status} | Assigned to: {assigned_to}\n"
                    f"   Time: {date_str}\n\n"
                )

            if len(tasks) > 5:
                response += (
                    f"...and {len(tasks) - 5} more tasks (showing first 5 only)."
                )
        else:
            response += "No recent tasks found for this resident."

        return self._truncate_response(response)

    def _format_datetime(self, dt: datetime) -> str:
        """Format datetime object to string"""
        if not dt:
            return "Unknown time"
        try:
            # Format the datetime in a consistent way
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception as e:
            logger.error(f"Error formatting datetime {dt}: {str(e)}")
            return "Invalid time format"

    def _truncate_response(self, text: str) -> str:
        """Truncate long messages to avoid Telegram message size limits"""
        if len(text) <= self.max_length:
            return text

        # Basic truncation method
        truncated_text = text[: self.max_length - 100]
        # Try to find a reasonable place to break
        last_newline = truncated_text.rfind("\n")
        if last_newline > self.max_length - 200:
            truncated_text = truncated_text[:last_newline]

        return truncated_text + "\n\n...(message truncated due to length)"
