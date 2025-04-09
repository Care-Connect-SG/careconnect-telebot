import logging
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Dict, Any

from config import (
    MONGO_URI,
    DB_NAME,
    RESIDENT_DB_NAME
)

logger = logging.getLogger(__name__)

# Initialize MongoDB client
mongo_client = AsyncIOMotorClient(MONGO_URI, tlsAllowInvalidCertificates=True)
db = mongo_client[DB_NAME]
resident_db = mongo_client[RESIDENT_DB_NAME]

# Create a simple service class that delegates to specialized services
class DatabaseService:
    def __init__(self):
        # Initialize collections for access by other services
        self.resident_collection = resident_db["resident_info"]
        self.tasks_collection = db["tasks"]
        self.activities_collection = db["activities"] 
        self.users_collection = db["users"]
        
        # Import functions here to avoid circular imports
        from .resident_service import get_resident_by_name, get_resident_tasks
        from .task_service import get_tasks, get_tasks_by_time_range
        from .activity_service import get_activities, get_activities_by_time_range
        
        # Assign imported functions
        self.get_resident_by_name = get_resident_by_name
        self.get_resident_tasks = get_resident_tasks
        self.get_tasks = get_tasks
        self.get_tasks_by_time_range = get_tasks_by_time_range
        self.get_activities = get_activities
        self.get_activities_by_time_range = get_activities_by_time_range
