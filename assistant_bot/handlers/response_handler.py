import logging
from typing import List, Dict, Any
from datetime import datetime


logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4000

RESPONSE_TEMPLATES = {
    "no_results": "No results found matching your criteria.",
    "error": "I'm sorry, I encountered an error while processing your request. Please try again.",
    "unknown_command": "I'm not sure how to help with that. You can ask me about tasks, residents, or activities.",
    "resident_not_found": "Sorry, I couldn't find a resident with that name.",
}

def format_task_response(tasks: List[Dict[str, Any]]) -> str:
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
            date_str = f"{format_datetime(start_date)}"
        if due_date:
            date_str += f" to {format_datetime(due_date)}"

        response += (
            f"{idx}. *{title}*\n"
            f"   Status: {status} | Priority: {priority}\n"
            f"   For: {assigned_for} | By: {assigned_to}\n"
            f"   Time: {date_str}\n\n"
        )

    if len(tasks) > 10:
        response += f"...and {len(tasks) - 10} more tasks (showing first 10 only)."

    return truncate_response(response)

def format_activity_response(activities: List[Dict[str, Any]]) -> str:
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
            time_str = f"{format_datetime(start_time)}"
        if end_time:
            time_str += f" to {format_datetime(end_time)}"

        response += (
            f"{idx}. *{title}*\n"
            f"   Category: {category} | Location: {location}\n"
            f"   Created by: {created_by}\n"
            f"   Time: {time_str}\n\n"
        )

    if len(activities) > 10:
        response += f"...and {len(activities) - 10} more activities (showing first 10 only)."

    return truncate_response(response)

def format_resident_response(resident, tasks, is_general_query=False) -> str:
    if isinstance(resident, list):
        if not resident:
            return RESPONSE_TEMPLATES["resident_not_found"]

        response = f"👥 *Found {len(resident)} residents:*\n\n"
        for idx, res in enumerate(resident[:10], start=1):
            full_name = res.get("full_name", "Unknown")
            room_number = res.get("room_number", "Unknown")
            response += f"{idx}. *{full_name}* (Room: {room_number})\n\n"

        if len(resident) > 10:
            response += f"...and {len(resident) - 10} more residents (showing first 10 only)."

        return truncate_response(response)

    if not resident:
        return RESPONSE_TEMPLATES["resident_not_found"]

    full_name = resident.get("full_name", "Unknown")
    room_number = resident.get("room_number", "Unknown")

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

    if tasks:
        response += f"*Recent tasks for {full_name}:*\n\n"

        for idx, task in enumerate(tasks[:5], start=1):
            title = task.get("task_title", "Untitled Task")
            status = task.get("status", "Unknown")
            assigned_to = task.get("assigned_to_name", "Unassigned")

            start_date = task.get("start_date")
            date_str = format_datetime(start_date) if start_date else "Unknown"

            response += (
                f"{idx}. *{title}*\n"
                f"   Status: {status} | Assigned to: {assigned_to}\n"
                f"   Time: {date_str}\n\n"
            )

        if len(tasks) > 5:
            response += f"...and {len(tasks) - 5} more tasks (showing first 5 only)."
    else:
        response += "No recent tasks found for this resident."

    return truncate_response(response)

def format_datetime(dt: datetime) -> str:
    if not dt:
        return "Unknown time"
    try:
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception as e:
        logger.error(f"Error formatting datetime {dt}: {str(e)}")
        return "Invalid time format"

def truncate_response(text: str) -> str:
    if len(text) <= MAX_MESSAGE_LENGTH:
        return text

    truncated_text = text[:MAX_MESSAGE_LENGTH - 100]
    last_newline = truncated_text.rfind("\n")
    if last_newline > MAX_MESSAGE_LENGTH - 200:
        truncated_text = truncated_text[:last_newline]

    return truncated_text + "\n\n...(message truncated due to length)"
