"""Parse the main editor text into emotion-tagged segments.

Syntax (ElevenLabs-v3 style):  [EmotionName] some text  [Another] more text
A tag applies to everything after it until the next tag. Text before the first
tag (and text under an unknown tag) falls back to the default emotion.

The SAME regex is mirrored in frontend/js/editor.js so live highlighting and
server-side synthesis always segment identically.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Emotion, slugify

# [Name] - no nested brackets, no newlines inside the tag.
TAG_RE = re.compile(r"\[([^\[\]\n]+)\]")


@dataclass
class Segment:
    index: int
    text: str                # spoken text (trimmed); may be ""
    emotion: Emotion
    tag_raw: str             # the tag name as typed, "" if untagged
    known: bool              # False when a [Tag] didn't match any emotion
    char_start: int          # offset of spoken text in the original string
    char_end: int

    def to_public(self) -> dict:
        return {
            "index": self.index,
            "text": self.text,
            "emotion_id": self.emotion.id,
            "emotion_name": self.emotion.name,
            "color": self.emotion.color,
            "tag_raw": self.tag_raw,
            "known": self.known,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "prosody": self.emotion.prosody.model_dump(),
            "rvc": self.emotion.rvc.model_dump(),
            "pause_after_ms": self.emotion.pause_after_ms,
        }


def parse_segments(
    text: str,
    emotions: dict[str, Emotion],
    default: Emotion,
) -> list[Segment]:
    """Split `text` into ordered segments keyed by their active emotion."""
    segments: list[Segment] = []
    cursor = 0                 # position in text we've consumed up to
    current = default          # active emotion for the chunk being read
    current_tag = ""
    current_known = True

    def emit(chunk_start: int, chunk_end: int):
        nonlocal cursor
        raw = text[chunk_start:chunk_end]
        stripped = raw.strip()
        if not stripped:
            return
        # recompute trimmed offsets so highlight ranges stay tight
        lead = len(raw) - len(raw.lstrip())
        start = chunk_start + lead
        segments.append(Segment(
            index=len(segments),
            text=stripped,
            emotion=current,
            tag_raw=current_tag,
            known=current_known,
            char_start=start,
            char_end=start + len(stripped),
        ))

    for m in TAG_RE.finditer(text):
        emit(cursor, m.start())            # flush text before this tag
        name = m.group(1).strip()
        resolved = emotions.get(slugify(name))
        current = resolved or default
        current_tag = name
        current_known = resolved is not None
        cursor = m.end()

    emit(cursor, len(text))                 # trailing chunk after last tag
    return segments


def validate_text(text: str, emotions: dict[str, Emotion]) -> list[str]:
    """Return the list of unknown tag names found in `text` (for UI warnings)."""
    unknown: list[str] = []
    for m in TAG_RE.finditer(text):
        name = m.group(1).strip()
        if slugify(name) not in emotions and name not in unknown:
            unknown.append(name)
    return unknown
