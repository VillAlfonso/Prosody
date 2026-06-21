"""Pydantic data models + the seed preset emotions.

An "emotion" bundles BOTH the base-TTS prosody (rate/pitch/volume that Edge-TTS
understands) AND the RVC voice-conversion params (transpose, index rate, etc.).
That single bundle is what an inline [Tag] in the editor refers to.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

F0Method = Literal["rmvpe", "harvest", "crepe", "pm"]


def slugify(name: str) -> str:
    """Tag-matching key for an emotion name. Case/space insensitive."""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


class TTSParams(BaseModel):
    """Maps directly onto Edge-TTS prosody controls."""
    rate: int = Field(0, ge=-90, le=200)     # speaking speed, percent
    pitch: int = Field(0, ge=-100, le=100)   # base pitch shift, Hz
    volume: int = Field(0, ge=-90, le=100)   # loudness, percent


class RVCParams(BaseModel):
    """Maps onto rvc-python / RVC-WebUI inference params."""
    transpose: int = Field(0, ge=-24, le=24)            # f0 key shift, semitones
    index_rate: float = Field(0.66, ge=0.0, le=1.0)     # timbre/accent strength
    protect: float = Field(0.33, ge=0.0, le=0.5)        # protect voiceless consonants
    rms_mix_rate: float = Field(0.25, ge=0.0, le=1.0)   # volume-envelope follow
    filter_radius: int = Field(3, ge=0, le=7)           # pitch median smoothing
    f0method: F0Method = "rmvpe"


class Emotion(BaseModel):
    id: str                                   # slug, stable key used by tags
    name: str                                 # display name shown in [Name]
    color: str = "#7c8cff"                    # highlight color (#hex)
    description: str = ""
    sample_text: str = "Hi there, welcome to my channel!"
    pause_after_ms: int = Field(0, ge=0, le=4000)   # silence appended after segment
    is_default: bool = False                  # the fallback used for untagged text
    tts: TTSParams = Field(default_factory=TTSParams)
    rvc: RVCParams = Field(default_factory=RVCParams)


class Settings(BaseModel):
    voice: str = "en-US-AriaNeural"
    rvc_enabled: bool = False
    active_model: Optional[str] = None        # basename of selected .pth
    output_format: Literal["mp3", "wav"] = "mp3"
    default_emotion: str = "neutral"          # emotion id for untagged text
    rvc_device: str = "cpu:0"


# ---- API payload shapes ----------------------------------------------------

class SynthRequest(BaseModel):
    text: str
    voice: Optional[str] = None               # override settings.voice
    rvc_enabled: Optional[bool] = None        # override settings.rvc_enabled
    format: Optional[Literal["mp3", "wav"]] = None


class PreviewRequest(BaseModel):
    """Live preview from the Prosody Lab - one ad-hoc emotion, no saving."""
    sample_text: str
    emotion: Emotion
    voice: Optional[str] = None
    rvc_enabled: Optional[bool] = None


class ColorMap(BaseModel):
    colors: dict[str, str]                    # emotion id -> #hex


# ---- Seed presets ----------------------------------------------------------

def _e(name, color, desc, sample, *, rate=0, pitch=0, volume=0,
       transpose=0, index_rate=0.66, protect=0.33, rms=0.25,
       default=False, pause=0) -> Emotion:
    return Emotion(
        id=slugify(name), name=name, color=color, description=desc,
        sample_text=sample, is_default=default, pause_after_ms=pause,
        tts=TTSParams(rate=rate, pitch=pitch, volume=volume),
        rvc=RVCParams(transpose=transpose, index_rate=index_rate,
                      protect=protect, rms_mix_rate=rms),
    )


DEFAULT_EMOTIONS: list[Emotion] = [
    _e("Neutral", "#8b93a7", "Calm, even narration. Used for untagged text.",
       "This is my normal speaking voice.", default=True),
    _e("Gleeful", "#ffd166", "Bright, upbeat and smiling.",
       "Hi there, welcome to my channel!",
       rate=12, pitch=28, volume=6, transpose=1, index_rate=0.7, rms=0.35),
    _e("Excited", "#ff7b54", "High energy, fast and loud.",
       "You are NOT going to believe what happened today!",
       rate=24, pitch=40, volume=12, transpose=2, index_rate=0.72, rms=0.45),
    _e("Sad", "#5b8def", "Slow, low and downcast.",
       "But today, I have some difficult news to share.",
       rate=-16, pitch=-30, volume=-6, transpose=-1, index_rate=0.6, rms=0.15),
    _e("Angry", "#ef476f", "Hard, intense and forceful.",
       "I have had absolutely enough of this.",
       rate=8, pitch=-8, volume=14, transpose=0, index_rate=0.75,
       protect=0.2, rms=0.5),
    _e("Whisper", "#9b8cff", "Soft, intimate, breathy and quiet.",
       "Come closer... I want to tell you a secret.",
       rate=-12, pitch=-6, volume=-40, transpose=0, index_rate=0.5,
       protect=0.45, rms=0.05),
    _e("Calm", "#06d6a0", "Relaxed, warm and reassuring.",
       "Take a deep breath. Everything is going to be alright.",
       rate=-8, pitch=4, volume=-2, transpose=0, index_rate=0.66, rms=0.2),
]
