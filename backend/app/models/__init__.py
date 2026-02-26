import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


def _new_id():
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"

    id = Column(String(32), primary_key=True, default=_new_id)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum("user", "admin", name="user_role"), default="user", nullable=False)
    status = Column(Enum("active", "disabled", name="user_status"), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    notebooks = relationship("Notebook", back_populates="owner")


class Notebook(Base):
    __tablename__ = "notebooks"

    id = Column(String(32), primary_key=True, default=_new_id)
    owner_id = Column(String(32), ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    owner = relationship("User", back_populates="notebooks")
    entries = relationship("Entry", back_populates="notebook", cascade="all, delete-orphan")
    permissions = relationship(
        "Permission",
        primaryjoin="and_(Notebook.id == foreign(Permission.resource_id), Permission.resource_type == 'notebook')",
        viewonly=True,
    )


class Entry(Base):
    __tablename__ = "entries"

    id = Column(String(32), primary_key=True, default=_new_id)
    notebook_id = Column(String(32), ForeignKey("notebooks.id"), nullable=False)
    author_id = Column(String(32), ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    content_blocks = Column(JSON, default=list)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    notebook = relationship("Notebook", back_populates="entries")
    author = relationship("User")
    revisions = relationship("EntryRevision", back_populates="entry", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="entry", cascade="all, delete-orphan")


class EntryRevision(Base):
    __tablename__ = "entry_revisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_id = Column(String(32), ForeignKey("entries.id"), nullable=False)
    author_id = Column(String(32), ForeignKey("users.id"), nullable=False)
    content_blocks = Column(JSON, nullable=False)
    change_summary = Column(String(500), default="")
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    entry = relationship("Entry", back_populates="revisions")
    author = relationship("User")


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(String(32), primary_key=True, default=_new_id)
    entry_id = Column(String(32), ForeignKey("entries.id"), nullable=False)
    type = Column(Enum("image", "excel", "file", name="attachment_type"), nullable=False)
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(127), nullable=False)
    size = Column(Integer, nullable=False)
    storage_uri = Column(String(500), nullable=False)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    entry = relationship("Entry", back_populates="attachments")


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_id = Column(String(32), ForeignKey("users.id"), nullable=False)
    resource_type = Column(Enum("notebook", "entry", name="resource_type"), nullable=False)
    resource_id = Column(String(32), nullable=False, index=True)
    access_level = Column(Enum("read", "write", "admin", name="access_level"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    subject = relationship("User")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor_id = Column(String(32), ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(String(32), nullable=True)
    detail = Column(JSON, default=dict)
    timestamp = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    actor = relationship("User")
