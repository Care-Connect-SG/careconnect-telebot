from motor.motor_asyncio import AsyncIOMotorClient
from utils.config import MONGO_URI
from .db_service import DatabaseService

mongo_client = AsyncIOMotorClient(MONGO_URI, tlsAllowInvalidCertificates=True)

resident_db = mongo_client["resident"]
resident_collection = resident_db["resident_info"]

caregiver_db = mongo_client["caregiver"]
users_collection = caregiver_db["users"]
tasks_collection = caregiver_db["tasks"]
activities_collection = caregiver_db["activities"]

db_service = DatabaseService(mongo_client)
