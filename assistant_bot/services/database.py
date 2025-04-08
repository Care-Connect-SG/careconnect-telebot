import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from ..config import (
    MONGO_URI,
    DB_NAME,
    RESIDENT_DB_NAME,
    RESIDENT_COLLECTION,
    TASKS_COLLECTION,
    ACTIVITIES_COLLECTION,
    USERS_COLLECTION,
)

logger = logging.getLogger(__name__)


class DatabaseService:
    def __init__(self):
        self.client = AsyncIOMotorClient(MONGO_URI)
        self.db = self.client[DB_NAME]
        self.resident_db = self.client[RESIDENT_DB_NAME]

        # Collections
        self.resident_collection = self.resident_db[RESIDENT_COLLECTION]
        self.tasks_collection = self.db[TASKS_COLLECTION]
        self.activities_collection = self.db[ACTIVITIES_COLLECTION]
        self.users_collection = self.db[USERS_COLLECTION]

    async def get_resident_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a resident by name (partial match)"""
        try:
            if not name:
                return None

            # Clean up the name by removing extra spaces
            name = " ".join(name.split()).strip()
            logger.info(f"Searching for resident with name: '{name}'")

            # Try exact match first (case insensitive)
            query = {"full_name": {"$regex": f"^{name}$", "$options": "i"}}
            resident = await self.resident_collection.find_one(query)

            if resident:
                logger.info(
                    f"Found resident by exact match: {resident.get('full_name')}"
                )
                return resident

            # Try partial match with full name
            query = {"full_name": {"$regex": f".*{name}.*", "$options": "i"}}
            resident = await self.resident_collection.find_one(query)

            if resident:
                logger.info(
                    f"Found resident by partial full name match: {resident.get('full_name')}"
                )
                return resident

            # Try matching individual parts of the name
            name_parts = name.split()
            if len(name_parts) > 0:
                # Build a query to match any part of the name
                name_queries = []
                for part in name_parts:
                    if len(part) > 2:  # Only consider parts with more than 2 characters
                        name_queries.append(
                            {"full_name": {"$regex": f"\\b{part}\\b", "$options": "i"}}
                        )

                if name_queries:
                    query = {"$or": name_queries}
                    resident = await self.resident_collection.find_one(query)

                    if resident:
                        logger.info(
                            f"Found resident by name part match: {resident.get('full_name')}"
                        )
                        return resident

            logger.info(f"No resident found matching name: '{name}'")
            return None
        except Exception as e:
            logger.error(f"Error finding resident: {str(e)}")
            return None

    async def get_tasks(self, query=None):
        """Get tasks based on provided query filters"""
        try:
            # Clone the query to avoid modifying the original
            query_filters = query.copy() if query else {}

            # For debugging
            logger.info(f"Task query filters: {query_filters}")

            # Execute the query
            tasks = (
                await self.tasks_collection.find(query_filters)
                .sort("start_date", -1)
                .to_list(length=100)
            )

            # Log the found tasks for debugging
            if tasks:
                task_info = [
                    f"{task.get('title')} - Date: {task.get('start_date')}"
                    for task in tasks[:5]
                ]
                logger.info(f"Found {len(tasks)} tasks. Sample tasks: {task_info}")
            else:
                logger.info("No tasks found matching the query filters")

            # Enrich tasks with names
            for task in tasks:
                if "assigned_to" in task and task["assigned_to"]:
                    user = await self.users_collection.find_one(
                        {"_id": task["assigned_to"]}, {"full_name": 1}
                    )
                    if user:
                        task["assigned_to_name"] = user.get("full_name", "Unknown")

                if "assigned_for" in task and task["assigned_for"]:
                    try:
                        resident = await self.resident_collection.find_one(
                            {"_id": ObjectId(task["assigned_for"])}, {"full_name": 1}
                        )
                        if resident:
                            task["assigned_for_name"] = resident.get(
                                "full_name", "Unknown"
                            )
                    except:
                        task["assigned_for_name"] = "Unknown"

            return tasks
        except Exception as e:
            logger.error(f"Error retrieving tasks: {str(e)}")
            return []

    async def get_activities(
        self, filters: Dict[str, Any] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get activities with optional filters"""
        try:
            query = filters or {}
            activities = (
                await self.activities_collection.find(query)
                .sort("start_time", -1)
                .limit(limit)
                .to_list(length=limit)
            )

            # Enrich activities with creator names
            for activity in activities:
                if "created_by" in activity and activity["created_by"]:
                    try:
                        user = await self.users_collection.find_one(
                            {"_id": ObjectId(activity["created_by"])}, {"full_name": 1}
                        )
                        if user:
                            activity["created_by_name"] = user.get(
                                "full_name", "Unknown"
                            )
                    except:
                        activity["created_by_name"] = "Unknown"

            return activities
        except Exception as e:
            logger.error(f"Error getting activities: {str(e)}")
            return []

    async def get_resident_tasks(
        self, resident_id: str, time_range: Dict[str, datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get tasks for a specific resident with optional time range"""
        try:
            filters = {"assigned_for": ObjectId(resident_id)}

            if time_range and "start_time" in time_range and "end_time" in time_range:
                filters["start_date"] = {
                    "$gte": time_range["start_time"],
                    "$lte": time_range["end_time"],
                }

            return await self.get_tasks(filters)
        except Exception as e:
            logger.error(f"Error getting resident tasks: {str(e)}")
            return []

    async def get_tasks_by_time_range(
        self, start_time: datetime, end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Get tasks within a specific time range"""
        try:
            filters = {"start_date": {"$gte": start_time, "$lte": end_time}}
            return await self.get_tasks(filters)
        except Exception as e:
            logger.error(f"Error getting tasks by time range: {str(e)}")
            return []

    async def get_activities_by_time_range(
        self, start_time: datetime, end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Get activities within a specific time range"""
        try:
            filters = {
                "$or": [
                    {"start_time": {"$gte": start_time, "$lte": end_time}},
                    {"end_time": {"$gte": start_time, "$lte": end_time}},
                ]
            }
            return await self.get_activities(filters)
        except Exception as e:
            logger.error(f"Error getting activities by time range: {str(e)}")
            return []
