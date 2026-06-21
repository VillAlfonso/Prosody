"""Central configuration: filesystem paths and a few global constants.

Everything is anchored to the project root so the app is fully portable -
move the C:\\Prosody folder anywhere and it still works.
"""
from __future__ import annotations

import shutil
from pathlib import Path

# backend/config.py -> backend/ -> project root
ROOT = Path(__file__).resolve().parent.parent

FRONTEND_DIR = ROOT / "frontend"
DATA_DIR = ROOT / "data"
MODELS_DIR = DATA_DIR / "models"      # uploaded RVC .pth / .index live here
OUTPUT_DIR = DATA_DIR / "output"      # rendered audio
CACHE_DIR = DATA_DIR / "cache"        # temp per-segment wavs

EMOTIONS_FILE = DATA_DIR / "emotions.json"
SETTINGS_FILE = DATA_DIR / "settings.json"

# Make sure the writable dirs exist on import.
for _d in (DATA_DIR, MODELS_DIR, OUTPUT_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Audio working format used between pipeline stages.
SAMPLE_RATE = 44100
CHANNELS = 1

# ffmpeg / ffprobe discovery. Prefer PATH; fall back to the known install spot.
FFMPEG = shutil.which("ffmpeg") or r"C:\ffmpeg\ffmpeg.exe"
FFPROBE = shutil.which("ffprobe") or r"C:\ffmpeg\ffprobe.exe"
