import re
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

time_patterns = {
    "today": lambda: get_today_range(),
    "tomorrow": lambda: get_tomorrow_range(),
    "yesterday": lambda: get_yesterday_range(),
    "this_week": lambda: get_this_week_range(),
    "last_hours": lambda h: get_last_hours_range(h),
}

def parse_query(message_text: str) -> Tuple[str, Dict[str, Any]]:
    try:
        intent = "general_question"
        time_range = {}
        filters = {}

        message_text = message_text.lower().strip()

        if "today" in message_text and ("task" in message_text or "tasks" in message_text):
            intent = "task_query"
            time_range = get_today_range()
            logger.info(f"Detected 'today's tasks' query, using time range: {time_range}")
            return intent, {"time_range": time_range, "filters": filters}

        if re.search(r"\btasks?\b", message_text, re.IGNORECASE):
            intent = "task_query"
            time_range = extract_time_range(message_text)
            filters.update(extract_task_filters(message_text))

        elif re.search(r"\bactivit(y|ies)\b|\bupcoming\b|\bscheduled\b", message_text, re.IGNORECASE):
            intent = "activity_query"
            time_range = extract_time_range(message_text)
            filters.update(extract_activity_filters(message_text))

        elif is_resident_query(message_text):
            intent = "resident_query"
            time_range = extract_time_range(message_text)
            filters["resident_name"] = extract_resident_name(message_text)

        return intent, {"time_range": time_range, "filters": filters}

    except Exception as e:
        logger.error(f"Error parsing query: {str(e)}")
        return "general_question", {"time_range": {}, "filters": {}}

def extract_time_range(text: str) -> Dict[str, datetime]:
    for pattern, handler in time_patterns.items():
        if pattern == "last_hours":
            match = re.search(r"last (\d+) hours?", text, re.IGNORECASE)
            if match:
                hours = int(match.group(1))
                return handler(hours)
        elif re.search(rf'\b{pattern.replace("_", " ")}\b', text, re.IGNORECASE):
            return handler()
    return {}

def extract_task_filters(text: str) -> Dict[str, Any]:
    filters = {}

    status_map = {
        "overdue": "Overdue",
        "pending": "Pending",
        "completed": "Completed",
    }
    for status, value in status_map.items():
        if re.search(rf"\b{status}\b", text, re.IGNORECASE):
            filters["status"] = value
            break

    priority_map = {
        "high priority": "High",
        "medium priority": "Medium",
        "low priority": "Low",
    }
    for priority, value in priority_map.items():
        if re.search(rf"\b{priority}\b", text, re.IGNORECASE):
            filters["priority"] = value
            break

    return filters

def extract_activity_filters(text: str) -> Dict[str, Any]:
    filters = {}

    location_match = re.search(r"in\s+([A-Za-z\s]+)(room|hall|area)?", text, re.IGNORECASE)
    if location_match:
        filters["location"] = location_match.group(1).strip()

    categories = ["Medication", "Exercise", "Social", "Entertainment", "Education"]
    for category in categories:
        if re.search(rf"\b{category}\b", text, re.IGNORECASE):
            filters["category"] = category
            break

    return filters

def extract_resident_name(text: str) -> str:
    text = text.lower().strip()

    direct_patterns = [
        r"how\s+is\s+([A-Za-z\s]+?)(?:\s+doing)?(?:\s|$)",
        r"what\s+happened\s+to\s+([A-Za-z\s]+?)(?:\s+today|\s+yesterday|\s+this\s+week)?(?:\s|$)",
        r"(?:resident|patient)?\s+([A-Za-z\s]+?)(?:\s+info|information|details|profile|status)?(?:\s|$)",
        r"tell\s+me\s+about\s+([A-Za-z\s]+?)(?:\s|$)",
        r"show\s+(?:me\s+)?(?:resident|patient)?\s+([A-Za-z\s]+?)(?:\s|$)",
        r"(?:find|look\s+up|search\s+for)\s+(?:resident|patient)?\s+([A-Za-z\s]+?)(?:\s|$)",
    ]

    for pattern in direct_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            logger.info(f"Extracted resident name from direct pattern: '{name}'")
            return name

    words = text.split()
    if 1 <= len(words) <= 3:
        potential_name = " ".join(words)
        logger.info(f"Potential resident name from simple text: '{potential_name}'")
        return potential_name

    name_match = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})", text)
    if name_match:
        name = name_match.group(1).strip()
        logger.info(f"Extracted resident name from capitalization: '{name}'")
        return name

    logger.info(f"No resident name found in: '{text}'")
    return ""

def is_resident_query(text: str) -> bool:
    text = text.lower().strip()

    resident_indicators = [
        "resident",
        "patient",
        "how is",
        "tell me about",
        "profile",
        "details",
        "information",
        "status",
        "what happened to",
        "show resident",
    ]

    if any(indicator in text for indicator in resident_indicators):
        return True

    words = text.split()
    if 1 <= len(words) <= 3:
        return True

    return False

def get_today_range() -> Dict[str, datetime]:
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    logger.info(f"Generated today's range: {today_start} to {today_end}")
    return {"start_time": today_start, "end_time": today_end}

def get_tomorrow_range() -> Dict[str, datetime]:
    now = datetime.now()
    tomorrow = now + timedelta(days=1)
    tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59, microsecond=999999)
    return {"start_time": tomorrow_start, "end_time": tomorrow_end}

def get_yesterday_range() -> Dict[str, datetime]:
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
    return {"start_time": yesterday_start, "end_time": yesterday_end}

def get_this_week_range() -> Dict[str, datetime]:
    now = datetime.now()
    start_of_week = now - timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = now
    return {"start_time": start_of_week, "end_time": end_of_week}

def get_last_hours_range(hours: int) -> Dict[str, datetime]:
    now = datetime.now()
    hours_ago = now - timedelta(hours=hours)
    return {"start_time": hours_ago, "end_time": now}
