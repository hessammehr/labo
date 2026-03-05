from datetime import datetime

from pydantic import BaseModel, EmailStr


# --- Auth ---

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    role: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Notebooks ---

class NotebookCreate(BaseModel):
    title: str
    description: str = ""


class NotebookUpdate(BaseModel):
    title: str | None = None
    description: str | None = None


class NotebookOut(BaseModel):
    id: str
    owner_id: str
    title: str
    description: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Entries ---

class EntryCreate(BaseModel):
    notebook_id: str
    title: str
    content_blocks: list[dict] = []
    tags: list[str] = []


class EntryImport(BaseModel):
    notebook_id: str
    filename: str
    markdown: str


class EntryUpdate(BaseModel):
    notebook_id: str | None = None
    title: str | None = None
    content_blocks: list[dict] | None = None
    tags: list[str] | None = None
    change_summary: str = ""
    checkpoint: bool = False


class EntryOut(BaseModel):
    id: str
    notebook_id: str
    author_id: str
    title: str
    content_blocks: list[dict]
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EntryRevisionOut(BaseModel):
    id: int
    entry_id: str
    author_id: str
    content_blocks: list[dict]
    change_summary: str
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Permissions ---

class PermissionCreate(BaseModel):
    subject_id: str
    resource_type: str  # "notebook" | "entry"
    resource_id: str
    access_level: str  # "read" | "write" | "admin"


class PermissionOut(BaseModel):
    id: int
    subject_id: str
    resource_type: str
    resource_id: str
    access_level: str
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Attachments ---

class AttachmentOut(BaseModel):
    id: str
    entry_id: str
    type: str
    filename: str
    mime_type: str
    size: int
    storage_uri: str
    created_at: datetime

    model_config = {"from_attributes": True}
