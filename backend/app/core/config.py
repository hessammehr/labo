from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./labo.db"

    # JWT
    jwt_secret: str = "change-me-in-production-use-32bytes!"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60 * 24  # 24 hours

    # Storage
    storage_dir: Path = Path("./storage")

    # App
    debug: bool = False

    model_config = {"env_prefix": "LABO_"}


settings = Settings()
