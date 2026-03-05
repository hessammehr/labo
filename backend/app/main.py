from fastapi import FastAPI

from app.core.config import settings
from app.core.database import Base, engine
from app.routers import auth, attachments, entries, notebooks, permissions

# Create tables (use alembic migrations for production)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Labo", version="0.1.0", debug=settings.debug)

app.include_router(auth.router)
app.include_router(notebooks.router)
app.include_router(entries.router)
app.include_router(attachments.router)
app.include_router(permissions.router)


@app.get("/health")
def health():
    return {"status": "ok"}
