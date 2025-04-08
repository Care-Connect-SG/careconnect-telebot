import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)


class QueryParser:
    def __init__(self):
        self.time_patterns = {
            "today": self._get_today_range,
            "tomorrow": self._get_tomorrow_range,
            "yesterday": self._get_yesterday_range,
            "this_week": self._get_this_week_range,
            "last_hours": self._get_last_hours_range,
        }

    def parse_query(self, message_text: str) -> Tuple[str, Dict[str, Any]]:
        """Parse the user's query and extract intent and parameters"""
        try:
            intent = "general_question"
            time_range = {}
            filters = {}

            # Normalize text before processing
            message_text = message_text.lower().strip()

            # Special case for "today's task" and similar phrases
            if "today" in message_text and (
                "task" in message_text or "tasks" in message_text
            ):
                intent = "task_query"
                time_range = self._get_today_range()
                logger.info(
                    f"Detected 'today's tasks' query, using time range: {time_range}"
                )
                return intent, {"time_range": time_range, "filters": filters}

            # Check for task-related queries
            if re.search(r"\btasks?\b", message_text, re.IGNORECASE):
                intent = "task_query"
                time_range = self._extract_time_range(message_text)
                filters.update(self._extract_task_filters(message_text))

            # Check for activity-related queries
            elif re.search(
                r"\bactivit(y|ies)\b|\bupcoming\b|\bscheduled\b",
                message_text,
                re.IGNORECASE,
            ):
                intent = "activity_query"
                time_range = self._extract_time_range(message_text)
                filters.update(self._extract_activity_filters(message_text))

            # Check for resident-related queries
            elif self._is_resident_query(message_text):
                intent = "resident_query"
                time_range = self._extract_time_range(message_text)
                filters["resident_name"] = self._extract_resident_name(message_text)

            return intent, {"time_range": time_range, "filters": filters}

        except Exception as e:
            logger.error(f"Error parsing query: {str(e)}")
            return "general_question", {"time_range": {}, "filters": {}}

    def _extract_time_range(self, text: str) -> Dict[str, datetime]:
        """Extract time range from text"""
        for pattern, handler in self.time_patterns.items():
            if pattern == "last_hours":
                match = re.search(r"last (\d+) hours?", text, re.IGNORECASE)
                if match:
                    hours = int(match.group(1))
                    return handler(hours)
            elif re.search(rf'\b{pattern.replace("_", " ")}\b', text, re.IGNORECASE):
                return handler()
        return {}

    def _extract_task_filters(self, text: str) -> Dict[str, Any]:
        """Extract task-specific filters"""
        filters = {}

        # Status filters
        status_map = {
            "overdue": "Overdue",
            "pending": "Pending",
            "completed": "Completed",
        }
        for status, value in status_map.items():
            if re.search(rf"\b{status}\b", text, re.IGNORECASE):
                filters["status"] = value
                break

        # Priority filters
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

    def _extract_activity_filters(self, text: str) -> Dict[str, Any]:
        """Extract activity-specific filters"""
        filters = {}

        # Location filter
        location_match = re.search(
            r"in\s+([A-Za-z\s]+)(room|hall|area)?", text, re.IGNORECASE
        )
        if location_match:
            filters["location"] = location_match.group(1).strip()

        # Category filters
        categories = ["Medication", "Exercise", "Social", "Entertainment", "Education"]
        for category in categories:
            if re.search(rf"\b{category}\b", text, re.IGNORECASE):
                filters["category"] = category
                break

        return filters

    def _extract_resident_name(self, text: str) -> str:
        """Extract resident name from query"""
        # Normalize the text
        text = text.lower().strip()

        # Direct mention patterns
        direct_patterns = [
            r"how\s+is\s+([A-Za-z\s]+?)(?:\s+doing)?(?:\s|$)",
            r"what\s+happened\s+to\s+([A-Za-z\s]+?)(?:\s+today|\s+yesterday|\s+this\s+week)?(?:\s|$)",
            r"(?:resident|patient)?\s+([A-Za-z\s]+?)(?:\s+info|information|details|profile|status)?(?:\s|$)",
            r"tell\s+me\s+about\s+([A-Za-z\s]+?)(?:\s|$)",
            r"show\s+(?:me\s+)?(?:resident|patient)?\s+([A-Za-z\s]+?)(?:\s|$)",
            r"(?:find|look\s+up|search\s+for)\s+(?:resident|patient)?\s+([A-Za-z\s]+?)(?:\s|$)",
        ]

        # Check direct patterns first
        for pattern in direct_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                logger.info(f"Extracted resident name from direct pattern: '{name}'")
                return name

        # Check if the text is just a name (2-3 words)
        words = text.split()
        if 1 <= len(words) <= 3:
            potential_name = " ".join(words)
            logger.info(f"Potential resident name from simple text: '{potential_name}'")
            return potential_name

        # Last resort - try to find a capitalized sequence of words
        name_match = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})", text)
        if name_match:
            name = name_match.group(1).strip()
            logger.info(f"Extracted resident name from capitalization: '{name}'")
            return name

        logger.info(f"No resident name found in: '{text}'")
        return ""

    def _is_resident_query(self, text: str) -> bool:
        """Check if the query is about a resident"""
        # Normalize the text
        text = text.lower().strip()

        # Check for common resident query indicators
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

        # If it contains any of these keywords, it's likely a resident query
        if any(indicator in text for indicator in resident_indicators):
            return True

        # If it's a short query (1-3 words), it could be just a name
        words = text.split()
        if 1 <= len(words) <= 3:
            return True

        return False

    def _get_today_range(self) -> Dict[str, datetime]:
        now = datetime.now()  # Use local time without timezone
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        logger.info(f"Generated today's range: {today_start} to {today_end}")
        return {"start_time": today_start, "end_time": today_end}

    def _get_tomorrow_range(self) -> Dict[str, datetime]:
        now = datetime.now()  # Use local time without timezone
        tomorrow = now + timedelta(days=1)
        tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_end = tomorrow.replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
        return {"start_time": tomorrow_start, "end_time": tomorrow_end}

    def _get_yesterday_range(self) -> Dict[str, datetime]:
        now = datetime.now()  # Use local time without timezone
        yesterday = now - timedelta(days=1)
        yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_end = yesterday.replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
        return {"start_time": yesterday_start, "end_time": yesterday_end}

    def _get_this_week_range(self) -> Dict[str, datetime]:
        now = datetime.now()  # Use local time without timezone
        start_of_week = now - timedelta(days=now.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_week = now
        return {"start_time": start_of_week, "end_time": end_of_week}

    def _get_last_hours_range(self, hours: int) -> Dict[str, datetime]:
        now = datetime.now()  # Use local time without timezone
        hours_ago = now - timedelta(hours=hours)
        return {"start_time": hours_ago, "end_time": now}
