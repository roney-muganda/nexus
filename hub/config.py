from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # App
    app_name: str = "nexus"
    debug: bool = False
    secret_key: str

    # Database
    database_url: str

    # Redis
    redis_url: str

    # Gemini
    gemini_api_key: str

    groq_api_key: str = ""

    # Telegram
    telegram_bot_token: str

    # ChromaDB
    chroma_host: str = "localhost"
    chroma_port: int = 8000

    chroma_api_key: str = ""
    chroma_tenant: str = "default_tenant"
    chroma_database: str = "default_database"

    # Auth
    jwt_private_key: str     
    jwt_public_key: str
    jwt_algorithm: str = "RS256"
    access_token_expire_minutes: int = 60

    gmail_token_b64: str | None = None

    # Desktop Spoke
    hmac_secret: str
    expected_desktop_api_key: str | None = None

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()