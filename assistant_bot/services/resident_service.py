import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from bson import ObjectId

from ..db.connection import (
    resident_collection,
)

logger = logging.getLogger(__name__)


async def get_resident_by_name(name: str) -> Optional[Dict[str, Any]]:
    if not name:
        return None

    name = " ".join(name.split()).strip()
    logger.info(f"Searching for resident with name: '{name}'")

    query = {"full_name": {"$regex": f"^{name}$", "$options": "i"}}
    resident = await resident_collection.find_one(query)

    if resident:
        logger.info(f"Found resident by exact match: {resident.get('full_name')}")
        return resident

    query = {"full_name": {"$regex": f".*{name}.*", "$options": "i"}}
    resident = await resident_collection.find_one(query)

    if resident:
        logger.info(
            f"Found resident by partial full name match: {resident.get('full_name')}"
        )
        return resident

    name_parts = name.split()
    if len(name_parts) > 0:
        name_queries = []
        for part in name_parts:
            if len(part) > 2:
                name_queries.append(
                    {"full_name": {"$regex": f"\\b{part}\\b", "$options": "i"}}
                )

        if name_queries:
            query = {"$or": name_queries}
            resident = await resident_collection.find_one(query)

            if resident:
                logger.info(
                    f"Found resident by name part match: {resident.get('full_name')}"
                )
                return resident

    logger.info(f"No resident found matching name: '{name}'")
    return None


async def get_resident_tasks(
    resident_id: str, time_range: Dict[str, datetime] = None
) -> List[Dict[str, Any]]:
    try:
        from .task_service import get_tasks

        filters = {"assigned_for": ObjectId(resident_id)}

        if time_range and "start_time" in time_range and "end_time" in time_range:
            filters["start_date"] = {
                "$gte": time_range["start_time"],
                "$lte": time_range["end_time"],
            }

        return await get_tasks(filters)
    except Exception as e:
        logger.error(f"Error getting resident tasks: {str(e)}")
        return []


async def get_all_residents(limit: int = 50) -> List[Dict[str, Any]]:
    try:
        residents = await resident_collection.find().limit(limit).to_list(length=limit)
        logger.info(f"Retrieved {len(residents)} residents")
        return residents
    except Exception as e:
        logger.error(f"Error getting all residents: {str(e)}")
        return []


async def add_resident_note(resident_id: str, note: str, user_id: str = None) -> bool:
    try:
        if not resident_id or not note:
            return False

        update_result = await resident_collection.update_one(
            {"_id": ObjectId(resident_id)},
            {
                "$push": {
                    "notes": {
                        "text": note,
                        "created_by": user_id,
                        "timestamp": datetime.now(),
                    }
                }
            },
        )

        if update_result.modified_count > 0:
            logger.info(f"Added note to resident {resident_id}")
            return True
        else:
            logger.warning(f"Failed to add note to resident {resident_id}")
            return False
    except Exception as e:
        logger.error(f"Error adding note to resident: {str(e)}")
        return False
