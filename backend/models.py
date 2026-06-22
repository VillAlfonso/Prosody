"""Pydantic data models + the seed preset emotions.

An "emotion" is a *delivery* + a *voice-conversion* recipe:

  prosody  -> how the line is performed (pace, energy, pitch inflection, and the
              all-important intonation RANGE / expressiveness). Pitch & range are
              applied with formant-preserving DSP (see prosody_dsp.py) so emotions
              never sound like a chipmunk/monster - the speaker identity holds.
  rvc      -> timbre controls for the optional voice conversion. The pitch of the
              RVC voice is a SINGLE global calibration (Settings.rvc_transpose),
              never per-emotion, so every block sounds like the same person.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

F0Method = Literal["rmvpe", "harvest", "crepe", "pm"]


def slugify(name: str) -> str:
    """Tag-matching key for an emotion name. Case/space insensitive."""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


class ProsodyParams(BaseModel):
    """How the line is delivered. rate/volume = Edge-TTS; pitch/range = Praat DSP."""
    rate: int = Field(0, ge=-60, le=60)        # pace, percent
    volume: int = Field(0, ge=-60, le=60)      # energy, percent
    pitch: float = Field(0.0, ge=-6.0, le=6.0) # median pitch, semitones (formant-safe)
    range: float = Field(1.0, ge=0.3, le=1.8)  # intonation range / expressiveness


class RVCParams(BaseModel):
    """Timbre controls for voice conversion. (Pitch is global, see Settings.)"""
    index_rate: float = Field(0.66, ge=0.0, le=1.0)     # timbre/accent strength
    protect: float = Field(0.33, ge=0.0, le=0.5)        # protect voiceless consonants
    rms_mix_rate: float = Field(0.25, ge=0.0, le=1.0)   # volume-envelope follow
    filter_radius: int = Field(3, ge=0, le=7)           # pitch median smoothing
    f0method: F0Method = "rmvpe"


class Emotion(BaseModel):
    id: str
    name: str
    color: str = "#7c8cff"
    description: str = ""
    sample_text: str = "Hi there, welcome to my channel!"
    pause_after_ms: int = Field(0, ge=0, le=4000)
    is_default: bool = False
    prosody: ProsodyParams = Field(default_factory=ProsodyParams)
    rvc: RVCParams = Field(default_factory=RVCParams)


class Settings(BaseModel):
    voice: str = "en-US-AriaNeural"
    rvc_enabled: bool = False
    active_model: Optional[str] = None
    output_format: Literal["mp3", "wav"] = "mp3"
    default_emotion: str = "neutral"
    rvc_device: str = "cpu:0"
    rvc_transpose: int = Field(0, ge=-12, le=12)  # GLOBAL voice-pitch calibration


# ---- API payload shapes ----------------------------------------------------

class SynthRequest(BaseModel):
    text: str
    voice: Optional[str] = None
    rvc_enabled: Optional[bool] = None
    format: Optional[Literal["mp3", "wav"]] = None


class PreviewRequest(BaseModel):
    sample_text: str
    emotion: Emotion
    voice: Optional[str] = None
    rvc_enabled: Optional[bool] = None


class ColorMap(BaseModel):
    colors: dict[str, str]


# ---- Seed presets ----------------------------------------------------------
# Emotion comes from PACE + ENERGY + intonation RANGE, with only tiny pitch moves.
# (range > 1 = livelier/melodic, < 1 = flatter/calmer.)

def _e(name, color, desc, sample, *, rate=0, volume=0, pitch=0.0, rng=1.0,
       index_rate=0.66, protect=0.33, rms=0.25, default=False, pause=0) -> Emotion:
    return Emotion(
        id=slugify(name), name=name, color=color, description=desc,
        sample_text=sample, is_default=default, pause_after_ms=pause,
        prosody=ProsodyParams(rate=rate, volume=volume, pitch=pitch, range=rng),
        rvc=RVCParams(index_rate=index_rate, protect=protect, rms_mix_rate=rms),
    )


DEFAULT_EMOTIONS: list[Emotion] = [
    _e("Neutral", "#8b93a7", "Even, natural narration. Used for untagged text.",
       "This is my normal speaking voice.", default=True),
    _e("Gleeful", "#ffd166", "Bright and smiling - livelier melody, a touch quicker.",
       "Hi there, welcome to my channel!",
       rate=6, volume=3, pitch=1.0, rng=1.35),
    _e("Excited", "#ff7b54", "High energy - fast, loud, very animated intonation.",
       "You are not going to believe what happened today!",
       rate=16, volume=8, pitch=1.5, rng=1.6),
    _e("Sad", "#5b8def", "Slow and subdued - flatter, downcast melody.",
       "But today, I have some difficult news to share.",
       rate=-14, volume=-4, pitch=-1.0, rng=0.6),
    _e("Angry", "#ef476f", "Hard and forceful - driven by loudness and pace, not pitch.",
       "I have had absolutely enough of this.",
       rate=6, volume=10, pitch=0.0, rng=1.15, protect=0.2),
    _e("Hushed", "#9b8cff", "Soft and intimate - quiet, gentle, slower.",
       "Come closer... I want to tell you something.",
       rate=-8, volume=-32, pitch=0.0, rng=0.8, protect=0.45),
    _e("Calm", "#06d6a0", "Relaxed and reassuring - gentle, even melody.",
       "Take a deep breath. Everything is going to be alright.",
       rate=-6, volume=-2, pitch=0.0, rng=0.85),
    _e("Curious", "#22d3ee", "Inquisitive lift - a little brighter and more varied.",
       "Hmm, now that is a really interesting question.",
       rate=2, volume=1, pitch=0.5, rng=1.3),
]
