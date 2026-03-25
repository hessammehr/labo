"""Global fuzzy search across notebooks and entries visible to the current user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Entry, Notebook, Permission, User

router = APIRouter(prefix="/search", tags=["search"])

MAX_RESULTS = 30
MIN_SCORE = 55  # rapidfuzz scores 0–100; skip low-quality matches


class SearchResult(BaseModel):
    type: str  # "notebook" | "entry"
    id: str
    title: str
    notebook_id: str | None = None
    notebook_title: str | None = None
    snippet: str
    score: float


def _extract_plaintext(blocks: list[dict] | None) -> str:
    """Recursively pull text from BlockNote JSON content_blocks."""
    if not blocks:
        return ""
    parts: list[str] = []
    for block in blocks:
        # BlockNote stores text in inline content arrays
        for inline in block.get("content", []):
            if isinstance(inline, dict):
                parts.append(inline.get("text", ""))
            elif isinstance(inline, str):
                parts.append(inline)
        # Table cells contain nested blocks
        table_content = block.get("tableContent", {})
        if isinstance(table_content, dict):
            for row in table_content.get("rows", []):
                for cell in row.get("cells", []):
                    if isinstance(cell, list):
                        for item in cell:
                            if isinstance(item, dict):
                                for inline in item.get("content", []):
                                    if isinstance(inline, dict):
                                        parts.append(inline.get("text", ""))
        # Recurse into nested children
        children = block.get("children", [])
        if children:
            parts.append(_extract_plaintext(children))
    return " ".join(parts)


def _snippet(text: str, query: str, max_len: int = 120) -> str:
    """Return a short substring of *text* centred around the best match for *query*."""
    if not text:
        return ""
    lower_text = text.lower()
    lower_query = query.lower()
    idx = lower_text.find(lower_query)
    if idx == -1:
        # Fallback: find the first query token
        for token in lower_query.split():
            idx = lower_text.find(token)
            if idx != -1:
                break
    if idx == -1:
        return text[:max_len] + ("…" if len(text) > max_len else "")
    start = max(0, idx - max_len // 4)
    end = min(len(text), idx + max_len)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end] + suffix


def _score_candidate(query: str, title: str, tags_str: str, plaintext: str) -> tuple[float, str]:
    """Score a candidate against the query.

    Returns (weighted_score, matched_field).  Raw scores are compared against
    MIN_SCORE first (so a perfect substring match in content always passes),
    then a weight bonus is applied to favour title > tags > content for ranking.
    """
    title_raw = fuzz.WRatio(query, title)
    tags_raw = fuzz.partial_ratio(query, tags_str) if tags_str else 0.0
    content_raw = fuzz.partial_ratio(query, plaintext[:4000]) if plaintext else 0.0

    # Pick the best *raw* match to decide if the candidate qualifies
    best_raw = max(title_raw, tags_raw, content_raw)
    if best_raw < MIN_SCORE:
        return 0.0, "title"

    # Apply ranking weights so title matches sort above content matches
    title_weighted = title_raw + 20  # bonus for title hit
    tags_weighted = tags_raw + 10
    content_weighted = content_raw

    best = content_weighted
    field = "content"
    if tags_weighted > best:
        best = tags_weighted
        field = "tags"
    if title_weighted > best:
        best = title_weighted
        field = "title"
    return best, field


@router.get("/", response_model=list[SearchResult])
def search(
    q: str = Query(..., min_length=1, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = q.strip()
    if not query:
        return []

    # Determine accessible notebook IDs
    if user.role == "admin":
        notebooks = db.query(Notebook).all()
    else:
        notebooks = (
            db.query(Notebook)
            .filter(
                Notebook.id.in_(
                    db.query(Permission.resource_id).filter(
                        Permission.subject_id == user.id,
                        Permission.resource_type == "notebook",
                    )
                )
            )
            .all()
        )

    notebook_map = {nb.id: nb for nb in notebooks}
    accessible_notebook_ids = list(notebook_map.keys())

    if not accessible_notebook_ids:
        return []

    # Load all entries in accessible notebooks
    entries = (
        db.query(Entry)
        .filter(Entry.notebook_id.in_(accessible_notebook_ids))
        .all()
    )

    results: list[tuple[float, SearchResult]] = []

    # Score notebooks
    for nb in notebooks:
        haystack = f"{nb.title} {nb.description or ''}"
        title_score = fuzz.WRatio(query, nb.title)
        full_score = fuzz.partial_ratio(query, haystack)
        raw = max(title_score, full_score)
        if raw < MIN_SCORE:
            continue
        score = raw + 20  # ranking bonus for notebook-level match
        if True:
            results.append((
                score,
                SearchResult(
                    type="notebook",
                    id=nb.id,
                    title=nb.title,
                    snippet=_snippet(nb.description or nb.title, query),
                    score=score,
                ),
            ))

    # Score entries
    for entry in entries:
        plaintext = _extract_plaintext(entry.content_blocks)
        tags_str = " ".join(entry.tags or [])
        score, matched_field = _score_candidate(query, entry.title, tags_str, plaintext)

        if score == 0.0:
            continue

        nb = notebook_map.get(entry.notebook_id)
        if matched_field == "content":
            snip = _snippet(plaintext, query)
        elif matched_field == "tags":
            snip = _snippet(tags_str, query)
        else:
            snip = _snippet(entry.title, query)

        results.append((
            score,
            SearchResult(
                type="entry",
                id=entry.id,
                title=entry.title,
                notebook_id=entry.notebook_id,
                notebook_title=nb.title if nb else None,
                snippet=snip,
                score=score,
            ),
        ))

    # Sort descending by score and take top N
    results.sort(key=lambda r: r[0], reverse=True)
    return [r for _, r in results[:MAX_RESULTS]]
