"""
Global configuration API — read and update config.json from the dashboard.
"""

import json
from pathlib import Path

from auth import TokenData, get_current_user
from fastapi import APIRouter, Depends, HTTPException
from logging_config import logger

router = APIRouter(prefix="/api/config", tags=["config"])

# Resolve config.json path (same logic as config.py)
_CONFIG_PATHS = [
    Path(__file__).parent.parent.parent / "config.json",  # project root
    Path(__file__).parent.parent / "config.json",  # backend/
    Path("config.json"),  # cwd
]

def _find_config_path() -> Path:
    for p in _CONFIG_PATHS:
        if p.exists():
            return p
    return _CONFIG_PATHS[0]


def _read_config() -> dict:
    path = _find_config_path()
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _write_config(data: dict) -> None:
    path = _find_config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    f.close()
    logger.info("Config updated", path=str(path))


# Keys that should never be returned or modified via API
_SECRET_KEYS = {"auth"}

# Whitelist of allowed top-level config sections
_ALLOWED_SECTIONS = {
    "llm", "ollama", "embedding", "database", "vector_store",
    "rag", "server", "rate_limit", "crawl", "agent",
}


@router.get("")
async def get_config(_user: TokenData = Depends(get_current_user)):
    """Return the current config.json (excluding secrets)."""
    config = _read_config()
    # Strip auth section (passwords)
    return {k: v for k, v in config.items() if k not in _SECRET_KEYS}


@router.put("")
async def update_config(body: dict, _user: TokenData = Depends(get_current_user)):
    """Merge partial updates into config.json. Requires server restart for most changes."""
    current = _read_config()

    # Prevent overwriting secret sections
    for key in _SECRET_KEYS:
        body.pop(key, None)

    # Reject keys not in the allowed whitelist
    invalid_keys = set(body.keys()) - _ALLOWED_SECTIONS
    if invalid_keys:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid config sections: {', '.join(sorted(invalid_keys))}. Allowed: {', '.join(sorted(_ALLOWED_SECTIONS))}",
        )

    # Deep merge: update section by section
    for section, values in body.items():
        if isinstance(values, dict) and isinstance(current.get(section), dict):
            current[section].update(values)
        else:
            current[section] = values

    _write_config(current)
    return {"status": "ok", "message": "Config updated. Some changes require a server restart."}
