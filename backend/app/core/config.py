from pydantic import model_validator
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Data directory — single location for all persistent state
    data_dir: Path = Path("./data")

    # Session
    session_cookie_name: str = "labo_session"
    session_expiry_hours: int = 24 * 30  # 30 days
    cookie_secure: bool = False  # set True when behind HTTPS
    cookie_samesite: str = "lax"

    # App
    debug: bool = False

    model_config = {"env_prefix": "LABO_", "env_file": ".env"}

    @model_validator(mode="after")
    def _ensure_data_dir_exists(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self

    @property
    def database_url(self) -> str:
        db_path = self.data_dir / "labo.db"
        return f"sqlite:///{db_path}"

    @property
    def storage_dir(self) -> Path:
        return self.data_dir / "storage"


settings = Settings()
