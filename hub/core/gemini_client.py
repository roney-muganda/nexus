from groq import Groq
from hub.config import settings

def get_groq_client():
    return Groq(api_key=settings.groq_api_key)