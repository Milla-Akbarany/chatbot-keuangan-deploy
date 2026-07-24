"""
app/config/settings.py
Semua konfigurasi dibaca dari .env — tidak ada nilai sensitif di sini.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # MySQL
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str
    mysql_database: str = "data_finance"

    # Qdrant
    qdrant_url: str = "https://be6b5e1a-220c-443b-9837-fcf277bf4f97.us-west-1-0.aws.cloud.qdrant.io"
    qdrant_api_key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIiwic3ViamVjdCI6ImFwaS1rZXk6MmQ4MzhkZTMtOGQwNy00NTllLTlkNDMtYjE4MzFhMTc1NzI4In0.p2aY_3K6ZMqjCowV_FS81tFyAmp0S1HfkpOPlkd9qLE"

    # Groq
    groq_api_key: str
    groq_model: str = "llama3-8b-8192"

    # Embedding
    embedding_model: str = "paraphrase-MiniLM-L6-v2"
    embedding_dim: int = 384

    # Threshold (akan diperbarui setelah threshold tuning empiris)
    threshold_intent: float = 0.50
    threshold_entity: float = 0.55

    # Qdrant collection names
    collection_intent: str = "data_intent"
    collection_entity: str = "dict_user"
    collection_transactions: str = "data_finance"

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = True

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Singleton settings — hanya dibaca sekali dari .env."""
    return Settings()
