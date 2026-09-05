"""Session persistence for the chat package."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .models import Session, Turn


_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def validate_storage_id(value: str, *, field_name: str) -> str:
    """Reject separators, traversal tokens and ambiguous storage identifiers."""
    if not _SAFE_ID_RE.fullmatch(value or "") or value in {".", ".."}:
        raise ValueError(f"invalid {field_name}")
    return value


def _contained(root: Path, candidate: Path) -> Path:
    root_resolved = root.resolve()
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root_resolved):
        raise ValueError("session path escapes session root")
    return resolved


def _user_dir(session_dir: Path, user_id: str) -> Path:
    """Return the per-user directory used for session isolation."""
    uid = validate_storage_id(user_id, field_name="user_id")
    return _contained(session_dir, session_dir / uid)


def _session_path(session_dir: Path, session_id: str, user_id: str = "default") -> Path:
    """Return the on-disk JSON path for one session."""
    sid = validate_storage_id(session_id, field_name="session_id")
    return _contained(session_dir, _user_dir(session_dir, user_id) / f"{sid}.json")


def save_session(session: Session, session_dir: Path, *, user_id: str = "default") -> None:
    """Persist one session as a readable JSON file."""
    uid = user_id or session.user_id or "default"
    path = _session_path(session_dir, session.session_id, uid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_session(session_id: str, session_dir: Path, *, user_id: str = "default") -> Session | None:
    """Load one session from disk, returning `None` when it does not exist."""
    path = _session_path(session_dir, session_id, user_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    turns = [
        Turn(
            turn_id=t["turn_id"],
            user_message=t["user_message"],
            assistant_message=t["assistant_message"],
            timestamp=t["timestamp"],
            image_ids=t.get("image_ids", []),
            metadata=t.get("metadata", {}),
        )
        for t in data.get("turns", [])
    ]
    return Session(
        session_id=data["session_id"],
        user_id=data.get("user_id", user_id),
        turns=turns,
        summary=data.get("summary", ""),
        created_at=data.get("created_at", ""),
        metadata=data.get("metadata", {}),
    )


def list_sessions(session_dir: Path, *, user_id: str = "default") -> list[str]:
    """List stored session ids for one user."""
    user_path = _user_dir(session_dir, user_id)
    if not user_path.exists():
        return []
    return sorted(p.stem for p in user_path.glob("*.json"))


def list_users(session_dir: Path) -> list[str]:
    """List all user ids that currently have persisted sessions."""
    if not session_dir.exists():
        return []
    return sorted(d.name for d in session_dir.iterdir() if d.is_dir())
