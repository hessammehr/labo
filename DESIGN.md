# Electronic Lab Notebook (ELN) — Design Document

## 1. Overview
This document outlines the design for an Electronic Lab Notebook (ELN) system. The ELN enables authenticated users to create and manage lab notebooks with rich text entries, attachments, and structured data. It provides secure sharing and permissions, a WYSIWYG editor, attachment handling (including Excel workbooks with an embedded editor), and a comprehensive API for programmatic access and export.

## 2. Goals
- Provide user-centric lab notebooks with secure sharing and permissions.
- Offer a block-based rich text editor with embedded images and attachments.
- Support Excel workbooks with a built-in editor and structured data access.
- Enable export of notebooks and entries into multiple formats (Markdown, ZIP, DOCX, LaTeX).
- Provide APIs for programmatic access to entries, notebooks, and attachments.
- Support streaming access to tabular data for analytics tools (DuckDB, Pandas, etc.).

## 3. Non-Goals (for v1)
- Fully offline desktop clients (web-first approach).
- Complex LIMS integration or experiment automation.
- Real-time collaborative editing (can be added later).

## 4. Personas & Use Cases
- **Researcher**: Creates experiments, adds notes, images, and Excel data, shares with team.
- **PI/Admin**: Manages accounts, oversees access permissions, compliance review.
- **Data Scientist**: Pulls structured data into DuckDB/Pandas for analysis.

## 5. High-Level Requirements
### Functional
- User registration, login, password reset, and admin management.
- Per-user notebooks with entries and metadata (date, tags, project, author).
- Sharing permissions at notebook and entry level.
- WYSIWYG editor with block-based content (text, headers, lists, tables, equations, images, attachments).
- Drag-and-drop attachments (images, files, spreadsheets).
- Excel workbook support with built-in editor.
- Export entries/notebooks to Markdown, ZIP (Markdown + attachments), DOCX, LaTeX.
- API for:
  - Entries as Markdown
  - Notebooks as JSON/Markdown
  - Attachments download
  - Structured/streamed tabular data

### Non-Functional
- Secure authentication and authorization.
- Audit logging for access and changes.
- Scalable storage for binary attachments.
- Efficient streaming for large files (Excel/CSV).

## 6. System Architecture (High Level)
- **Frontend**: React + TypeScript single-page workspace app (Bun + Vite + Tailwind) with:
  - Left tree navigation pane (notebooks + entries)
  - Center editor pane (BlockNote)
  - Right utility pane (reserved for future features)
- **Backend**: Python/FastAPI REST API with services for:
  - User management & auth (session cookies + API keys, bcrypt)
  - Notebook & entry management
  - Attachment storage & streaming
  - Export pipeline
- **Storage**:
  - SQLite database (migrate to PostgreSQL as needed) for metadata, content structure, permissions. Managed via SQLAlchemy ORM with Alembic migrations.
  - Local filesystem for binary attachments (abstract storage layer to support S3-compatible in future).

## 7. Data Model (Conceptual)
### Entities
- **User**: id, name, email, role (user/admin), status
- **Notebook**: id, owner_id, title, description, created_at, updated_at
- **Entry**: id, notebook_id, author_id, title, content_blocks, created_at, updated_at, tags
- **EntryRevision**: id, entry_id, author_id, content_blocks, created_at, change_summary
- **Attachment**: id, entry_id, type (image, excel, file), filename, mime_type, size, storage_uri, metadata
- **Permission**: id, subject_id (user/group), resource_type (notebook/entry), resource_id, access_level (read/write/admin)
- **AuditLog**: id, actor_id, action, resource_type, resource_id, timestamp

### Content Blocks
Block-based structure for rich text (JSON):
- Text block
- Header block
- List block
- Table block
- Image block
- File/Attachment block
- Code block
- Equation block
- Chemical structure block (KET JSON via Ketcher)

## 8. Permissions & Sharing
- **Notebook-level**: default permissions applied to entries.
- **Entry-level overrides**: allow more granular access control.
- Access levels:
  - **Read**: view only
  - **Write**: edit entries and upload attachments
  - **Admin**: manage sharing and permissions
- Admin users can manage all resources.

## 9. Rich Text & Block Editor
- Use BlockNote for the block-based editor (Notion-like UX, fast integration).
- UI is a single workspace page with **three resizable panes** separated by draggable vertical splitters:
  - **Left pane**: VS Code-style Explorer tree of notebooks and entries
  - **Center pane**: active entry editor
  - **Right pane**: reserved for future context tools (metadata, history, assistants, etc.)
- Notebook and entry operations (create, rename, delete, move entry across notebooks) are initiated in the left tree pane via inline controls and right-click context menus.
- v1 interaction model avoids modal dialogs for core tree operations; creation/rename/move flows are inline in the workspace.
- Theme follows system appearance (light/dark mode) across shell, explorer, and editor chrome.
- Blocks store as JSON in the database.
- Markdown export uses a renderer to convert blocks to Markdown.
- Supports inline images and attachments.

## 10. Attachment & File Handling
- Drag-and-drop upload in the editor.
- Files stored on the local filesystem, referenced by metadata in DB (storage layer abstracted for future object storage).
- Large files use multipart upload.
- Supported types: images, PDFs, CSV, Excel, and other binary files.

## 11. Excel Workbooks & Tabular Data
- **Embedded Editor**: use Jspreadsheet CE (MIT-licensed) for in-browser spreadsheet editing.
- **Storage**:
  - Original file stored as binary.
  - Extracted tabular data generated on demand (no caching in v1).
- **Streaming API**:
  - Convert Excel/CSV to Arrow, Parquet, and CSV streams for direct consumption by DuckDB/Pandas.
  - Support partial reads (sheet selection, column filtering).
  - Parquet chunking/partitioning can be added later; initial support may stream whole files.

## 12. API Design (Outline)
### Authentication
- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`

### Notebooks
- `GET /notebooks` (list)
- `POST /notebooks` (create)
- `GET /notebooks/{id}`
- `PATCH /notebooks/{id}` (update)
- `DELETE /notebooks/{id}`
- `GET /notebooks/{id}/export` (md/json)

### Entries
- `GET /entries/notebook/{notebook_id}` (list entries for tree view)
- `GET /entries/{id}` (json)
- `GET /entries/{id}/markdown`
- `GET /entries/{id}/revisions`
- `POST /entries` (create)
- `PUT /entries/{id}` (update, creates revision; supports move by setting `notebook_id`)
- `DELETE /entries/{id}`
- `POST /entries/{id}/export` (docx/latex)

### Attachments
- `POST /attachments` (upload)
- `GET /attachments/{id}` (download)
- `GET /attachments/{id}/stream?format=arrow|parquet|csv` (tabular data streaming for excel/csv)

### Permissions
- `POST /permissions` (grant/upsert)
- `DELETE /permissions/{id}` (revoke)
- `GET /permissions/resource/{type}/{id}` (list for a resource)

## 13. Export Pipeline
- Markdown export: block rendering to MD.
- ZIP export: Markdown + attachments, preserving structure.
- DOCX/LaTeX: use conversion libraries (Pandoc or custom exporters).

## 14. Security & Compliance
- Enforce RBAC with notebook/entry-level permissions.
- Dual authentication:
  - **Session cookies** (HttpOnly, SameSite) for browser-based UI — set on login, cleared on logout. No client-side token management.
  - **API keys** (`X-API-Key` header) for instruments, scripts, and programmatic access — long-lived, revocable, shown once on creation.
- Both resolve to the same user principal; all endpoints work with either.
- HTTPS via Tailscale serve.
- Audit logs for edit history and access.
- Immutable revision history for compliance and auditability.

## 15. Scalability & Performance
- Streaming endpoints for large files.
- Pagination for notebook/entry listings.

## 16. Tooling & Dev Workflow
- **Backend package management**: `uv` exclusively — no pip, no manual venv. `uv run` for project commands, `uvx` for standalone tools.
- **Frontend package management**: Bun (`bun install`, `bun dev`, `bun run build`).
- **Database migrations**: Alembic (auto-generates migrations by diffing SQLAlchemy models against the DB).
- **Makefile targets**:
  - `dev` runs backend and frontend together
  - `dev-backend`, `dev-frontend`
  - `run`, `serve` (Tailscale HTTPS), `test`, `lint`, `fmt`, `migrate`, `migrate-new`, `build-frontend`
- **Deployment**: Dockerfile + docker-compose.yml using the same `uv run` entrypoint as local dev.
- **Testing**: pytest with in-memory SQLite, FastAPI TestClient.

## 17. Future: Data Capture & Live Analysis

- **Data capture**: Instruments push data (spectra, sensor readings, etc.) into entries/attachments via the API using long-lived API keys.
- **Live analysis pane**: The right pane will host a marimo-style reactive Python environment (Pyodide or server-side kernel) with access to notebooks, entries, and attachments for in-place data analysis.
- **Feedback loop**: capture → store → analyse → embed results back into entries.

## 18. Open Questions
- Marimo integration: embedded iframe, custom reactive runtime, or Pyodide?
- Data capture: REST only, or also WebSocket/SSE for streaming ingest?
- Analysis pane auth: service account or inherited user session?
