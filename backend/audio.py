"""Audio plumbing built on ffmpeg + the stdlib `wave` module.

Pipeline stages exchange a single canonical PCM format (SAMPLE_RATE / mono /
16-bit) so segments can be stitched with the `wave` module - no re-encoding per
join, exact sample alignment, and silence is trivial to synthesize.
"""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

from . import config

_CREATE_NO_WINDOW = 0x08000000  # don't pop console windows on Windows


def _run(args: list[str]) -> None:
    proc = subprocess.run(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=_CREATE_NO_WINDOW,
    )
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "ignore")[-800:]
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}):\n{tail}")


def to_canonical_wav(src: str | Path, dst: str | Path) -> Path:
    """Decode any audio into SAMPLE_RATE / mono / s16le PCM wav."""
    dst = Path(dst)
    _run([
        config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-ac", str(config.CHANNELS), "-ar", str(config.SAMPLE_RATE),
        "-c:a", "pcm_s16le", str(dst),
    ])
    return dst


def make_silence(dst: str | Path, ms: int) -> Path:
    """Write `ms` of silence in the canonical format."""
    dst = Path(dst)
    n = int(config.SAMPLE_RATE * config.CHANNELS * ms / 1000)
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(config.CHANNELS)
        w.setsampwidth(2)
        w.setframerate(config.SAMPLE_RATE)
        w.writeframes(b"\x00\x00" * n)
    return dst


def stitch(parts: list[Path], dst: str | Path) -> Path:
    """Concatenate canonical wavs (and silences) into one wav."""
    dst = Path(dst)
    with wave.open(str(dst), "wb") as out:
        out.setnchannels(config.CHANNELS)
        out.setsampwidth(2)
        out.setframerate(config.SAMPLE_RATE)
        for p in parts:
            with wave.open(str(p), "rb") as w:
                out.writeframes(w.readframes(w.getnframes()))
    return dst


def export(src_wav: str | Path, dst: str | Path, fmt: str) -> Path:
    """Render the final wav to the requested delivery format."""
    dst = Path(dst)
    if fmt == "wav":
        if Path(src_wav) != dst:
            _run([
                config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(src_wav), "-c:a", "pcm_s16le", str(dst),
            ])
        return dst
    # mp3
    _run([
        config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src_wav), "-c:a", "libmp3lame", "-q:a", "2", str(dst),
    ])
    return dst


def duration_seconds(path: str | Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except (wave.Error, OSError):
        return 0.0
