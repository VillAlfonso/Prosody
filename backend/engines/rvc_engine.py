"""RVC voice-conversion stage (pluggable).

Design goal: the whole app runs perfectly WITHOUT RVC installed. This module
detects whether the heavy stack (`rvc-python` + torch) is importable and either
performs real conversion or reports a clean "unavailable" status that the
pipeline and UI handle gracefully.

Model files live in data/models/ as pairs:  <name>.pth  (+ optional <name>.index)

--- Wiring note -------------------------------------------------------------
The conversion calls below target the `rvc-python` API (daswer123). The exact
method/kwarg names are confirmed at install time (see README -> "Enable RVC").
If a future version differs, only `_RVCManager.convert` needs adjusting.
"""
from __future__ import annotations

import threading
from pathlib import Path

from .. import config
from ..models import RVCParams

# Detect the optional dependency without crashing the app if it's missing.
try:  # pragma: no cover - depends on optional install
    from rvc_python.infer import RVCInference  # type: ignore
    _IMPORT_OK = True
    _IMPORT_ERR = ""
except Exception as e:  # ImportError or downstream torch/fairseq errors
    RVCInference = None  # type: ignore
    _IMPORT_OK = False
    _IMPORT_ERR = f"{type(e).__name__}: {e}"


class RVCUnavailable(RuntimeError):
    """Raised when conversion is requested but RVC can't run."""


def list_models() -> list[dict]:
    """Discover uploaded models (.pth) and pair each with its .index if present."""
    models = []
    for pth in sorted(config.MODELS_DIR.glob("*.pth")):
        sibling = pth.with_suffix(".index")
        index = sibling if sibling.exists() else None
        if index is None:  # fall back to any .index in the folder
            any_idx = sorted(config.MODELS_DIR.glob("*.index"))
            index = any_idx[0] if any_idx else None
        models.append({
            "name": pth.stem,
            "pth": pth.name,
            "index": index.name if index else None,
            "has_index": index is not None,
            "size_mb": round(pth.stat().st_size / 1e6, 1),
        })
    return models


def resolve_model(name: str | None) -> tuple[Path, Path | None] | None:
    """Map a model name (or .pth basename) to its (pth, index) paths."""
    if not name:
        return None
    stem = Path(name).stem
    pth = config.MODELS_DIR / f"{stem}.pth"
    if not pth.exists():
        return None
    for m in list_models():
        if m["name"] == stem:
            idx = config.MODELS_DIR / m["index"] if m["index"] else None
            return pth, idx
    return pth, None


def status(active_model: str | None = None) -> dict:
    return {
        "installed": _IMPORT_OK,
        "import_error": _IMPORT_ERR,
        "models": list_models(),
        "active_model": active_model,
        "active_resolved": bool(resolve_model(active_model)),
    }


class _RVCManager:
    """Loads a model once and reuses it across conversions (thread-safe)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._infer = None
        self._device = None
        self._loaded_pth: str | None = None

    def _ensure_engine(self, device: str) -> None:
        if self._infer is None or self._device != device:
            self._infer = RVCInference(device=device)  # type: ignore[call-arg]
            self._device = device
            self._loaded_pth = None

    def _ensure_model(self, pth: Path, index: Path | None) -> None:
        if self._loaded_pth != str(pth):
            self._infer.load_model(str(pth), index_path=str(index) if index else "")
            self._loaded_pth = str(pth)

    def convert(self, pth: Path, index: Path | None, src: Path, dst: Path,
                params: RVCParams, device: str) -> Path:
        if not _IMPORT_OK:
            raise RVCUnavailable(
                "RVC is not installed. See README -> 'Enable RVC'. "
                f"Import error: {_IMPORT_ERR}"
            )
        with self._lock:
            self._ensure_engine(device)
            self._ensure_model(pth, index)
            self._infer.set_params(
                f0up_key=params.transpose,
                index_rate=params.index_rate,
                protect=params.protect,
                rms_mix_rate=params.rms_mix_rate,
                filter_radius=params.filter_radius,
                f0method=params.f0method,
            )
            self._infer.infer_file(str(src), str(dst))
        if not dst.exists() or dst.stat().st_size == 0:
            raise RVCUnavailable("RVC conversion produced no output.")
        return dst


manager = _RVCManager()


def convert(model_name: str, src: Path, dst: Path, params: RVCParams,
            device: str = "cpu:0") -> Path:
    """Convert `src` -> `dst` using the named model. Raises RVCUnavailable."""
    resolved = resolve_model(model_name)
    if resolved is None:
        raise RVCUnavailable(f"Model '{model_name}' not found in data/models/.")
    pth, index = resolved
    return manager.convert(pth, index, src, dst, params, device)
