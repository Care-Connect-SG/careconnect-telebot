import logging
import os
import certifi
from openai import AsyncOpenAI
from utils.config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

# Set SSL certificate path
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# Initialize the async client
client = AsyncOpenAI(
    api_key=OPENAI_API_KEY,
    http_client=None  # Let the client use default httpx client
)

async def summarize_text(text):
    """
    Summarize the given text using OpenAI's GPT model.

    Args:
        text (str): The transcribed text to summarize

    Returns:
        str: Summarized text
    """
    try:
        if not text.strip():
            return "No text to summarize."

        prompt = f"Please summarize and refine the following spoken text into concise notes:\n\n{text}"

        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that summarizes spoken text into concise, well-formatted notes.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=100,
            temperature=0.5,
        )

        summary = response.choices[0].message.content.strip()
        logger.info(f"Generated summary for text: {text[:50]}...")

        return summary
    except Exception as e:
        logger.error(f"Error in summarize_text: {e}")
        return f"An error occurred while generating a summary: {str(e)}"
