import logging
from functools import wraps
from motor.motor_asyncio import AsyncIOMotorClient
from telegram import Update
from telegram.ext import ContextTypes
from config import MONGO_URI

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client["caregiver"]
users_collection = db["users"]

def restricted(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        username = update.effective_user.username
        
        # Check if user exists in database with matching telegram_handle
        user = await users_collection.find_one({"telegram_handle": username})
        
        if not user:
            await update.message.reply_text(
                "Sorry, you are not authorized to use this bot. Please make sure your Telegram username is registered in the system."
            )
            return
            
        # Store user info in context for use in handlers
        context.user_data["name"] = user["name"]
        context.user_data["email"] = user["email"]
        context.user_data["role"] = user["role"]
        return await func(update, context, *args, **kwargs)
    return wrapped

async def verify_user(telegram_username: str) -> dict:
    """Verify if a user exists in the database by their Telegram username"""
    try:
        # Remove @ symbol if present and convert to lowercase for comparison
        telegram_username = telegram_username.lower().replace('@', '')
        logger.info(f"Verifying user with telegram_handle: {telegram_username}")
        
        # First, let's check if the collection exists and has any documents
        count = await users_collection.count_documents({})
        logger.info(f"Total users in database: {count}")
        
        # Let's also log all users with their telegram handles for debugging
        async for user in users_collection.find({}, {"telegram_handle": 1, "name": 1}):
            db_handle = user.get('telegram_handle', '').lower().replace('@', '')
            logger.info(f"Found user: {user.get('name')} with telegram_handle: {db_handle}")
            if db_handle == telegram_username:
                logger.info(f"Found exact match for username: {telegram_username}")
        
        # Try to find the user with case-insensitive comparison
        user = await users_collection.find_one({
            "$expr": {
                "$eq": [
                    {"$toLower": {"$trim": {"input": "$telegram_handle"}}},
                    telegram_username
                ]
            }
        })
        
        if user:
            logger.info(f"Found matching user: {user.get('name')}")
            return {
                "id": str(user["_id"]),
                "name": user["name"],
                "email": user["email"],
                "role": user["role"]
            }
        logger.info(f"No user found with telegram_handle: {telegram_username}")
        return None
    except Exception as e:
        logger.error(f"Error verifying user: {e}")
        return None 