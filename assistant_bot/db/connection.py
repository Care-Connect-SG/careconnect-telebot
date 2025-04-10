from typing import Dict, Any, Optional
import logging
from datetime import datetime
from datetime import timezone
from bson import ObjectId

logger = logging.getLogger(__name__)


class DatabaseService:
    def __init__(self, mongo_client):
        self.mongo_client = mongo_client
        self.resident_db = mongo_client["resident"]
        self.caregiver_db = mongo_client["caregiver"]

        self.resident_collection = self.resident_db["resident_info"]
        self.task_collection = self.resident_db["task"]
        self.user_collection = self.caregiver_db["users"]

    async def get_resident_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a resident by name (partial match)"""
        try:
            if not name:
                return None

            name = " ".join(name.split()).strip()
            logger.info(f"Searching for resident with name: '{name}'")

            query = {"full_name": {"$regex": f"^{name}$", "$options": "i"}}
            resident = await self.resident_collection.find_one(query)

            if resident:
                logger.info(
                    f"Found resident by exact match: {resident.get('full_name')}"
                )
                return resident

            query = {"full_name": {"$regex": f".*{name}.*", "$options": "i"}}
            resident = await self.resident_collection.find_one(query)

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

    async def get_resident_tasks(self, resident_id, time_range):
        try:
            start_time = time_range.get("start")
            end_time = time_range.get("end")

            query = {
                "resident_id": resident_id,
            }

            if start_time and end_time:
                query["due_time"] = {"$gte": start_time, "$lte": end_time}

            cursor = self.task_collection.find(query)
            tasks = await cursor.to_list(length=50)
            return tasks
        except Exception as e:
            logger.error(f"Error fetching tasks for resident {resident_id}: {str(e)}")
            return []

    async def get_all_residents(self, limit=50):
        try:
            cursor = self.resident_collection.find(
                {}, {"_id": 1, "full_name": 1, "room_number": 1}
            )
            residents = await cursor.to_list(length=limit)
            return residents
        except Exception as e:
            logger.error(f"Error fetching all residents: {str(e)}")
            return []

    async def add_resident_note(self, resident_id, note):
        """Add a note to a resident's record

        Args:
            resident_id (str): MongoDB ObjectId of the resident
            note (str): The note to add

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not ObjectId.is_valid(resident_id):
                logger.error(f"Invalid resident ID: {resident_id}")
                return False

            resident = await self.resident_collection.find_one(
                {"_id": ObjectId(resident_id)}
            )
            if not resident:
                logger.error(f"Resident not found with ID: {resident_id}")
                return False

            current_notes = resident.get("additional_notes", [])
            current_timestamps = resident.get("additional_notes_timestamp", [])

            new_notes = current_notes + [note]
            new_timestamps = current_timestamps + [datetime.now(timezone.utc)]

            result = await self.resident_collection.update_one(
                {"_id": ObjectId(resident_id)},
                {
                    "$set": {
                        "additional_notes": new_notes,
                        "additional_notes_timestamp": new_timestamps,
                    }
                },
            )

            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error adding note to resident {resident_id}: {str(e)}")
            return False
