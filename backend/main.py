from __future__ import annotations

import base64
import json
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from ai_engine.base_profile import build_base_profile


SCAN_STEPS = ("front", "left", "right", "hairline")
BACKEND_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BACKEND_DIR / "storage"
SCANS_DIR = STORAGE_DIR / "scans"

app = FastAPI(title="Hair App API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")


class StyleReferenceRequest(BaseModel):
    file_name: str | None = None


class GenerateRequest(BaseModel):
    scan_id: str | None = None
    style_reference_id: str | None = None


@app.post("/api/scan")
def create_scan(payload: dict[str, Any]) -> dict[str, Any]:
    steps = payload.get("steps")

    if not isinstance(steps, dict):
        raise HTTPException(status_code=400, detail="scan bundle steps are required")

    scan_id = str(uuid4())
    scan_dir = SCANS_DIR / scan_id
    scan_dir.mkdir(parents=True, exist_ok=False)

    stored_steps = _store_scan_steps(scan_id, scan_dir, steps)
    scan_record = {
        "scan_id": scan_id,
        "client_scan_session_id": payload.get("scanSessionId"),
        "client_completed_at": payload.get("completedAt"),
        "uploaded_at": _utc_now(),
        "steps": stored_steps,
    }
    base_profile = build_base_profile(scan_record)

    _write_json(scan_dir / "metadata.json", scan_record)
    _write_json(scan_dir / "base_profile.json", base_profile)

    return {
        "base_profile": base_profile,
        "base_profile_path": f"scans/{scan_id}/base_profile.json",
        "scan_id": scan_id,
        "status": "base_profile_ready",
        "storage_path": f"scans/{scan_id}",
    }


@app.get("/api/scan/{scan_id}")
def get_scan(scan_id: str) -> dict[str, Any]:
    scan_dir = _scan_dir(scan_id)
    metadata_path = scan_dir / "metadata.json"

    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="scan not found")

    return _read_json(metadata_path)


@app.get("/api/base-profile/{scan_id}")
def get_base_profile(scan_id: str) -> dict[str, Any]:
    scan_dir = _scan_dir(scan_id)
    profile_path = scan_dir / "base_profile.json"

    if not profile_path.exists():
        raise HTTPException(status_code=404, detail="base profile not found")

    return _read_json(profile_path)


@app.post("/api/style-reference")
def create_style_reference(payload: StyleReferenceRequest) -> dict[str, Any]:
    return {
        "style_reference_id": str(uuid4()),
        "status": "placeholder_uploaded",
        "file_name": payload.file_name,
    }


@app.post("/api/generate")
def generate_result(payload: GenerateRequest) -> dict[str, Any]:
    return {
        "result_id": str(uuid4()),
        "status": "placeholder_generation_queued",
        "scan_id": payload.scan_id,
        "style_reference_id": payload.style_reference_id,
    }


@app.get("/api/result/{result_id}")
def get_result(result_id: str) -> dict[str, Any]:
    return {
        "result_id": result_id,
        "status": "placeholder_ready",
        "image_url": None,
    }


def _store_scan_steps(
    scan_id: str,
    scan_dir: Path,
    steps: dict[str, Any],
) -> dict[str, Any]:
    stored_steps: dict[str, Any] = {}

    for step in SCAN_STEPS:
        step_payload = steps.get(step) or {}
        raw_samples = step_payload.get("samples") or []

        if not isinstance(raw_samples, list):
            raise HTTPException(status_code=400, detail=f"{step} samples must be a list")

        step_dir = scan_dir / step
        step_dir.mkdir(parents=True, exist_ok=True)
        stored_samples = [
            _store_sample(scan_id, step, step_dir, sample, index)
            for index, sample in enumerate(raw_samples)
        ]

        stored_steps[step] = {
            "progress": step_payload.get("progress", 0),
            "samples": stored_samples,
            "status": "complete" if stored_samples else "missing",
        }

    return stored_steps


def _store_sample(
    scan_id: str,
    step: str,
    step_dir: Path,
    sample: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    if not isinstance(sample, dict):
        raise HTTPException(status_code=400, detail=f"{step} sample must be an object")

    sample_data = deepcopy(sample)
    image_data_url = sample_data.pop("imageDataUrl", None)
    sample_id = _safe_name(str(sample_data.get("id") or f"{step}_{index + 1:03d}"))
    image_suffix = _image_suffix(image_data_url)
    image_filename = f"{sample_id}.{image_suffix}"
    image_path = step_dir / image_filename

    if image_data_url:
        image_path.write_bytes(_decode_data_url(image_data_url))

    relative_image_path = f"scans/{scan_id}/{step}/{image_filename}"
    sample_data.update(
        {
            "id": sample_id,
            "image_path": relative_image_path,
            "image_url": f"/storage/{relative_image_path}",
        }
    )

    _write_json(step_dir / f"{sample_id}.json", sample_data)
    return sample_data


def _decode_data_url(data_url: str) -> bytes:
    if "," not in data_url:
        raise HTTPException(status_code=400, detail="invalid image data url")

    _, encoded = data_url.split(",", 1)

    try:
        return base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid image payload") from exc


def _image_suffix(data_url: str | None) -> str:
    if not data_url:
        return "jpg"

    header = data_url.split(",", 1)[0]

    if "image/png" in header:
        return "png"

    if "image/webp" in header:
        return "webp"

    return "jpg"


def _scan_dir(scan_id: str) -> Path:
    scan_dir = SCANS_DIR / _safe_name(scan_id)

    if not scan_dir.resolve().is_relative_to(SCANS_DIR.resolve()):
        raise HTTPException(status_code=400, detail="invalid scan id")

    return scan_dir


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]", "_", value).strip("._")
    return cleaned or str(uuid4())


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
