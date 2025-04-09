import logging
from typing import Dict, Any, List
from datetime import datetime
from bson import ObjectId

from .database import db

logger = logging.getLogger(__name__)

# Collections
activities_collection = db["activities"]
users_collection = db["users"]

async def get_activities(filters: Dict[str, Any] = None, limit: int = 20) -> List[Dict[str, Any]]:
    try:
        query = filters or {}
        activities = (
            await activities_collection.find(query)
            .sort("start_time", -1)
            .limit(limit)
            .to_list(length=limit)
        )

        # Enrich activities with creator names
        for activity in activities:
            if "created_by" in activity and activity["created_by"]:
                try:
                    user = await users_collection.find_one(
                        {"_id": ObjectId(activity["created_by"])}, {"full_name": 1}
                    )
                    if user:
                        activity["created_by_name"] = user.get("full_name", "Unknown")
                except:
                    activity["created_by_name"] = "Unknown"

        return activities
    except Exception as e:
        logger.error(f"Error getting activities: {str(e)}")
        return []

async def get_activities_by_time_range(start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
    try:
        filters = {
            "$or": [
                {"start_time": {"$gte": start_time, "$lte": end_time}},
                {"end_time": {"$gte": start_time, "$lte": end_time}},
            ]
        }
        return await get_activities(filters)
    except Exception as e:
        logger.error(f"Error getting activities by time range: {str(e)}")
        return []

async def get_activities_by_category(category: str) -> List[Dict[str, Any]]:
    try:
        filters = {"category": category}
        return await get_activities(filters)
    except Exception as e:
        logger.error(f"Error getting activities by category: {str(e)}")
        return []

async def get_activities_by_location(location: str) -> List[Dict[str, Any]]:
    try:
        filters = {"location": {"$regex": f".*{location}.*", "$options": "i"}}
        return await get_activities(filters)
    except Exception as e:
        logger.error(f"Error getting activities by location: {str(e)}")
        return []

async def get_today_activities() -> List[Dict[str, Any]]:
    try:
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        return await get_activities_by_time_range(today_start, today_end)
    except Exception as e:
        logger.error(f"Error getting today's activities: {str(e)}")
        return [] 