"""Word / syllable / letter alignment for the Tone Editor.

Word timings come straight from the synthesizer (edge-tts WordBoundary), so they
are exact. Sub-word levels are interpolated *within* each exact word span - an
honest approximation, good enough to place edit handles and labels.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

try:
    import pyphen
    _DIC = pyphen.Pyphen(lang="en_US")
except Exception:  # pragma: no cover - optional dep
    _DIC = None

_VOWELS = set("aeiouyAEIOUY")


@dataclass
class Mark:
    label: str
    t0: float
    t1: float

    def as_dict(self) -> dict:
        return {"label": self.label, "t0": round(self.t0, 4), "t1": round(self.t1, 4)}


def _fallback_syllables(core: str) -> list[str]:
    """Crude vowel-group split, used only if pyphen is unavailable."""
    sylls, cur, seen_vowel = [], "", False
    for ch in core:
        if seen_vowel and ch not in _VOWELS:
            sylls.append(cur)
            cur, seen_vowel = ch, False
        else:
            cur += ch
            seen_vowel = seen_vowel or ch in _VOWELS
    if cur:
        if sylls and not seen_vowel:
            sylls[-1] += cur          # trailing consonants join the last syllable
        else:
            sylls.append(cur)
    return sylls or [core]


def _syllables(word: str) -> list[str]:
    core = re.sub(r"[^A-Za-z']", "", word)
    if not core:
        return [word]
    if _DIC is not None:
        parts = [p for p in _DIC.inserted(core).split("-") if p]
        if parts:
            return parts
    return _fallback_syllables(core)


def _split_span(t0: float, t1: float, weights: list[float]) -> list[tuple[float, float]]:
    total = sum(weights) or 1.0
    span = t1 - t0
    out, cur = [], t0
    for w in weights:
        nxt = cur + span * (w / total)
        out.append((cur, nxt))
        cur = nxt
    if out:
        out[-1] = (out[-1][0], t1)    # pin the end exactly
    return out


def subdivide(words: list[dict], level: str) -> list[Mark]:
    """`words`: ordered [{text, t0, t1}]. Returns marks at the requested level."""
    if level == "word":
        return [Mark(w["text"], w["t0"], w["t1"]) for w in words]

    marks: list[Mark] = []
    if level == "letter":
        for w in words:
            chars = list(w["text"]) or [" "]
            weights = [1.0 if c.strip() else 0.3 for c in chars]
            for c, (a, b) in zip(chars, _split_span(w["t0"], w["t1"], weights)):
                marks.append(Mark(c, a, b))
        return marks

    # syllable (default)
    for w in words:
        sylls = _syllables(w["text"])
        weights = [max(1, len(s)) for s in sylls]
        for s, (a, b) in zip(sylls, _split_span(w["t0"], w["t1"], weights)):
            marks.append(Mark(s, a, b))
    return marks


def all_levels(words: list[dict]) -> dict:
    """All three granularities at once, ready for the UI."""
    return {
        "words": [m.as_dict() for m in subdivide(words, "word")],
        "syllables": [m.as_dict() for m in subdivide(words, "syllable")],
        "letters": [m.as_dict() for m in subdivide(words, "letter")],
    }


def remap_words(words: list[dict], time_segments: list[dict] | None) -> list[dict]:
    """Shift word timings to a new timeline after pacing (duration) edits.

    The duration factor is 1.0 everywhere except inside each stretched region, so
    new_time(t) = t + sum over regions of overlap([0,t],[a,b]) * (scale - 1). This
    matches Praat's duration-tier integration, so marks stay aligned to the audio
    without re-running the synthesizer.
    """
    if not time_segments:
        return words
    segs = sorted(
        (max(0.0, float(s["t0"])), float(s["t1"]),
         max(0.5, min(2.0, float(s["value"]))))
        for s in time_segments
    )

    def remap(t: float) -> float:
        nt = t
        for a, b, sc in segs:
            nt += max(0.0, min(t, b) - a) * (sc - 1.0)
        return nt

    return [{"text": w["text"], "t0": remap(w["t0"]), "t1": remap(w["t1"])}
            for w in words]
