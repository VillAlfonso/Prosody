"""JSON-file persistence for emotions and settings.

Deliberately tiny and dependency-free: the data is small and human-editable,
which also satisfies the "configure colors/emotions through JSON" requirement -
the files in data/ ARE the config, and the UI's JSON editor reads/writes them.
"""
from __future__ import annotations

import json
import threading
from typing import Optional

from . import config
from .models import DEFAULT_EMOTIONS, Emotion, Settings, slugify

_lock = threading.RLock()


def _read_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomic on the same volume


# ---- Emotions --------------------------------------------------------------

def load_emotions() -> list[Emotion]:
    with _lock:
        raw = _read_json(config.EMOTIONS_FILE, None)
        if raw is None:
            save_emotions(DEFAULT_EMOTIONS)
            return list(DEFAULT_EMOTIONS)
        return [Emotion(**e) for e in raw]


def save_emotions(emotions: list[Emotion]) -> None:
    with _lock:
        _write_json(config.EMOTIONS_FILE, [e.model_dump() for e in emotions])


def emotions_by_id() -> dict[str, Emotion]:
    return {e.id: e for e in load_emotions()}


def get_emotion(eid: str) -> Optional[Emotion]:
    return emotions_by_id().get(slugify(eid))


def upsert_emotion(emotion: Emotion) -> Emotion:
    """Create or update by id. Enforces a single default emotion."""
    with _lock:
        emotion.id = slugify(emotion.name) or emotion.id
        emotions = load_emotions()
        if emotion.is_default:
            for e in emotions:
                e.is_default = False
        idx = next((i for i, e in enumerate(emotions) if e.id == emotion.id), None)
        if idx is None:
            emotions.append(emotion)
        else:
            emotions[idx] = emotion
        if not any(e.is_default for e in emotions) and emotions:
            emotions[0].is_default = True
        save_emotions(emotions)
        return emotion


def delete_emotion(eid: str) -> bool:
    with _lock:
        eid = slugify(eid)
        emotions = load_emotions()
        target = next((e for e in emotions if e.id == eid), None)
        if target is None or target.is_default:
            return False  # never delete the default/fallback emotion
        emotions = [e for e in emotions if e.id != eid]
        save_emotions(emotions)
        return True


def default_emotion() -> Emotion:
    emotions = load_emotions()
    return next((e for e in emotions if e.is_default), emotions[0])


# ---- Settings --------------------------------------------------------------

def load_settings() -> Settings:
    with _lock:
        raw = _read_json(config.SETTINGS_FILE, None)
        if raw is None:
            s = Settings()
            save_settings(s)
            return s
        return Settings(**raw)


def save_settings(settings: Settings) -> None:
    with _lock:
        _write_json(config.SETTINGS_FILE, settings.model_dump())


def update_settings(**changes) -> Settings:
    """Partial update. Pass a key to change it; None is a valid value for
    nullable fields (e.g. active_model=None clears the selected model)."""
    with _lock:
        s = load_settings()
        data = s.model_dump()
        data.update(changes)
        s = Settings(**data)
        save_settings(s)
        return s
