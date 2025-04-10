import logging
from typing import Dict, Any, List
from datetime import datetime
from bson import ObjectId

from ..db.connection import db, resident_db

logger = logging.getLogger(__name__)

tasks_collection = db["tasks"]
users_collection = db["users"]
resident_collection = resident_db["resident_info"]


async def get_tasks(query=None):
    try:
        query_filters = query.copy() if query else {}
        logger.info(f"Task query filters: {query_filters}")

        tasks = (
            await tasks_collection.find(query_filters)
            .sort("start_date", -1)
            .to_list(length=100)
        )

        if tasks:
            task_info = [
                f"{task.get('task_title')} - Date: {task.get('start_date')}"
                for task in tasks[:5]
            ]
            logger.info(f"Found {len(tasks)} tasks. Sample tasks: {task_info}")
        else:
            logger.info("No tasks found matching the query filters")

        for task in tasks:
            if "assigned_to" in task and task["assigned_to"]:
                user = await users_collection.find_one(
                    {"_id": task["assigned_to"]}, {"full_name": 1}
                )
                if user:
                    task["assigned_to_name"] = user.get("full_name", "Unknown")

            if "assigned_for" in task and task["assigned_for"]:
                try:
                    resident = await resident_collection.find_one(
                        {"_id": ObjectId(task["assigned_for"])}, {"full_name": 1}
                    )
                    if resident:
                        task["assigned_for_name"] = resident.get("full_name", "Unknown")
                except:
                    task["assigned_for_name"] = "Unknown"

        return tasks
    except Exception as e:
        logger.error(f"Error retrieving tasks: {str(e)}")
        return []


async def get_tasks_by_time_range(
    start_time: datetime, end_time: datetime
) -> List[Dict[str, Any]]:
    try:
        filters = {"start_date": {"$gte": start_time, "$lte": end_time}}
        return await get_tasks(filters)
    except Exception as e:
        logger.error(f"Error getting tasks by time range: {str(e)}")
        return []


async def get_tasks_by_status(status: str) -> List[Dict[str, Any]]:
    try:
        filters = {"status": status}
        return await get_tasks(filters)
    except Exception as e:
        logger.error(f"Error getting tasks by status: {str(e)}")
        return []


async def get_overdue_tasks() -> List[Dict[str, Any]]:
    try:
        now = datetime.now()
        filters = {"status": "pending", "due_date": {"$lt": now}}
        return await get_tasks(filters)
    except Exception as e:
        logger.error(f"Error getting overdue tasks: {str(e)}")
        return []


async def get_today_tasks() -> List[Dict[str, Any]]:
    try:
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        query_filters = {
            "$or": [
                {"start_date": {"$gte": today_start, "$lte": today_end}},
                {
                    "recurring": True,
                    "recurring_days": {"$in": [today_start.weekday()]},
                },
            ]
        }

        return await get_tasks(query_filters)
    except Exception as e:
        logger.error(f"Error getting today's tasks: {str(e)}")
        return []
