"""Edge-TTS base-voice synthesis.

Edge-TTS speaks the text with Microsoft neural voices and applies the prosody
(rate/pitch/volume) that an emotion specifies. The resulting audio is then
optionally handed to RVC for voice conversion.
"""
from __future__ import annotations

from pathlib import Path

import edge_tts

from ..models import TTSParams

# A curated short-list surfaced first in the UI; the full list comes from the API.
FEATURED_VOICES = [
    "en-US-AriaNeural", "en-US-JennyNeural", "en-US-GuyNeural",
    "en-US-AnaNeural", "en-US-ChristopherNeural", "en-US-EricNeural",
    "en-US-MichelleNeural", "en-US-RogerNeural", "en-US-SteffanNeural",
    "en-GB-SoniaNeural", "en-GB-RyanNeural", "en-GB-LibbyNeural",
    "en-AU-NatashaNeural", "en-AU-WilliamNeural",
]

_voice_cache: list[dict] | None = None


def _signed_pct(v: int) -> str:
    return f"{v:+d}%"


def _signed_hz(v: int) -> str:
    return f"{v:+d}Hz"


async def synth(text: str, voice: str, tts: TTSParams, out_mp3: str | Path) -> Path:
    """Synthesize `text` to an mp3 with the given voice + prosody."""
    out_mp3 = Path(out_mp3)
    communicate = edge_tts.Communicate(
        text,
        voice,
        rate=_signed_pct(tts.rate),
        volume=_signed_pct(tts.volume),
        pitch=_signed_hz(tts.pitch),
    )
    await communicate.save(str(out_mp3))
    if not out_mp3.exists() or out_mp3.stat().st_size == 0:
        raise RuntimeError(
            "Edge-TTS produced no audio. Check your internet connection and "
            "that the selected voice is valid (Edge-TTS is an online service)."
        )
    return out_mp3


async def list_voices() -> list[dict]:
    """Return available voices, featured ones first. Cached after first call."""
    global _voice_cache
    if _voice_cache is None:
        try:
            raw = await edge_tts.list_voices()
        except Exception:
            # Offline fallback so the UI still has something usable.
            return [{"value": v, "label": v, "gender": "", "locale": v[:5]}
                    for v in FEATURED_VOICES]
        voices = [{
            "value": v["ShortName"],
            "label": v["ShortName"],
            "gender": v.get("Gender", ""),
            "locale": v.get("Locale", ""),
        } for v in raw]
        rank = {name: i for i, name in enumerate(FEATURED_VOICES)}
        voices.sort(key=lambda x: (rank.get(x["value"], 10_000), x["value"]))
        _voice_cache = voices
    return _voice_cache
