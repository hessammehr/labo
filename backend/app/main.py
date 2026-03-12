from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from app.core.config import settings
from app.core.database import Base, engine
from app.routers import auth, attachments, entries, events, files, notebooks, permissions, scoped_tokens

# Create tables (use alembic migrations for production)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Labo", version="0.1.0", debug=settings.debug)

app.include_router(auth.router, prefix="/api")
app.include_router(notebooks.router, prefix="/api")
app.include_router(entries.router, prefix="/api")
app.include_router(attachments.router, prefix="/api")
app.include_router(permissions.router, prefix="/api")
app.include_router(scoped_tokens.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(events.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}


# Serve frontend static files if the build directory exists
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="static")

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        file = FRONTEND_DIST / path
        if file.is_file():
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")
