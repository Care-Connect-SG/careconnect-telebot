import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot Configuration
ASSISTANT_BOT_TOKEN = os.getenv("ASSISTANT_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# Database Configuration
DB_NAME = "caregiver"
RESIDENT_DB_NAME = "resident"
RESIDENT_COLLECTION = "resident_info"
TASKS_COLLECTION = "tasks"
ACTIVITIES_COLLECTION = "activities"
USERS_COLLECTION = "users"

# Query Configuration
MAX_RESULTS = 20
MAX_MESSAGE_LENGTH = 4000

# Time Configuration
TIMEZONE = "UTC"

# Response Templates
RESPONSE_TEMPLATES = {
    "no_results": "No results found matching your criteria.",
    "error": "I'm sorry, I encountered an error while processing your request. Please try again.",
    "unknown_command": "I'm not sure how to help with that. You can ask me about tasks, residents, or activities.",
    "resident_not_found": "Sorry, I couldn't find a resident with that name.",
}