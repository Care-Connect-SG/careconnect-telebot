import logging
import openai
from config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

# Configure OpenAI client
openai.api_key = OPENAI_API_KEY

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
            
        # Create the prompt for OpenAI
        prompt = f"Please summarize and refine the following spoken text into concise notes:\n\n{text}"
        
        # Call OpenAI API with correct client syntax
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes spoken text into concise, well-formatted notes."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.5
        )
        
        # Extract the summary from the response
        summary = response.choices[0].message.content.strip()
        logger.info(f"Generated summary for text: {text[:50]}...")
        
        return summary
    except Exception as e:
        logger.error(f"Error in summarize_text: {e}")
        return f"An error occurred while generating a summary: {str(e)}" 