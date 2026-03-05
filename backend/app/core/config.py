from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./labo.db"

    # Session
    session_cookie_name: str = "labo_session"
    session_expiry_hours: int = 24 * 30  # 30 days
    cookie_secure: bool = False  # set True when behind HTTPS
    cookie_samesite: str = "lax"

    # Storage
    storage_dir: Path = Path("./storage")

    # App
    debug: bool = False

    model_config = {"env_prefix": "LABO_"}


settings = Settings()
