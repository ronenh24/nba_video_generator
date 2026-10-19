"""
Remember which games already have a finished short (processed_shorts.json).
"""
import json
import os
from datetime import datetime
from pathlib import Path


def load_processed(path) -> dict:
    """{game_id: {"title", "video", "processed_at"}}. Missing file -> {}.

    A plain JSON list of game IDs is accepted too. A corrupt file is moved
    aside to <name>.bak so it is never silently overwritten.
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {str(g): {} for g in data}
        if isinstance(data, dict):
            return data
        raise ValueError("unexpected JSON structure")
    except (ValueError, OSError) as e:
        bak = p.with_name(p.name + ".bak")
        print(
            f"Warning: {p} unreadable ({e}); moved to {bak} and "
            "starting fresh."
        )
        try:
            os.replace(p, bak)
        except OSError:
            pass
        return {}


def is_processed(path, game_id: str) -> bool:
    return game_id in load_processed(path)


def mark_processed(path, game_id: str, title: str = "", video=None) -> None:
    """Add a game ID to the file (atomic write)."""
    p = Path(path)
    data = load_processed(p)
    data[game_id] = {
        "title": title,
        "video": str(video) if video else "",
        "processed_at": datetime.now().isoformat(timespec="seconds"),
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    os.replace(tmp, p)
