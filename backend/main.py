from __future__ import annotations

import base64
import json
import re
import shutil
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


SCAN_STEPS = (
    "front",
    "left_45",
    "right_45",
    "left_profile",
    "right_profile",
    "hairline",
)
RECONSTRUCTION_SELECTION_LIMITS = {
    "front": 2,
    "left_45": 2,
    "right_45": 2,
    "left_profile": 1,
    "right_profile": 1,
    "hairline": 2,
}
RECONSTRUCTION_TARGET_YAW = {
    "front": 0.0,
    "left_45": -0.34,
    "right_45": 0.34,
    "left_profile": -0.60,
    "right_profile": 0.60,
    "hairline": 0.0,
}
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
    reconstruction_bundle = _build_reconstruction_bundle(scan_id, scan_dir, stored_steps)
    scan_record = {
        "scan_id": scan_id,
        "scan_schema_version": "0.2",
        "client_scan_session_id": payload.get("scanSessionId"),
        "client_completed_at": payload.get("completedAt"),
        "reconstruction_bundle": reconstruction_bundle,
        "reconstruction_intent": payload.get("reconstructionIntent"),
        "uploaded_at": _utc_now(),
        "steps": stored_steps,
    }
    base_profile = build_base_profile(scan_record)

    _write_json(scan_dir / "metadata.json", scan_record)
    _write_json(scan_dir / "base_profile.json", base_profile)

    return {
        "base_profile": base_profile,
        "base_profile_path": f"scans/{scan_id}/base_profile.json",
        "reconstruction_bundle": reconstruction_bundle,
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
            "target_samples": step_payload.get("targetSamples"),
        }

    return stored_steps


def _build_reconstruction_bundle(
    scan_id: str,
    scan_dir: Path,
    stored_steps: dict[str, Any],
) -> dict[str, Any]:
    selected_dir = scan_dir / "selected_3dmm"
    selected_dir.mkdir(parents=True, exist_ok=True)

    images: list[dict[str, Any]] = []

    for step in SCAN_STEPS:
        samples = stored_steps.get(step, {}).get("samples", [])
        selected_samples = _select_3dmm_samples(step, samples)

        for sample in selected_samples:
            source_rel = sample.get("image_path")

            if not source_rel:
                continue

            source_path = STORAGE_DIR / source_rel

            if not source_path.exists():
                continue

            output_index = len(images)
            output_suffix = source_path.suffix or ".jpg"
            output_name = f"{output_index:05d}_{step}_{sample['id']}{output_suffix}"
            output_path = selected_dir / output_name
            shutil.copy2(source_path, output_path)

            selected_rel = f"scans/{scan_id}/selected_3dmm/{output_name}"
            images.append(
                {
                    "index": output_index,
                    "file_name": output_name,
                    "image_path": selected_rel,
                    "image_url": f"/storage/{selected_rel}",
                    "quality": sample.get("quality", {}),
                    "quality_score": _sample_quality_score(sample),
                    "selection_reason": _selection_reason(step, sample),
                    "source": "app_guided_scan",
                    "source_image_path": source_rel,
                    "source_sample_id": sample["id"],
                    "source_step": step,
                    "use_for": ["pixel3dmm_geometry_input", "texture_reference"],
                    "view_role": (sample.get("geometry") or {}).get("viewRole", step),
                }
            )

    manifest = {
        "version": "0.1",
        "purpose": "pixel3dmm_reconstruction_input",
        "privacy": "private biometric scan frames; do not commit to git",
        "scan_id": scan_id,
        "selected_count": len(images),
        "selection_limits": RECONSTRUCTION_SELECTION_LIMITS,
        "created_at": _utc_now(),
        "images": images,
    }

    _write_json(scan_dir / "selected_3dmm_manifest.json", manifest)
    _write_json(selected_dir / "manifest.json", manifest)

    return {
        "manifest_path": f"scans/{scan_id}/selected_3dmm_manifest.json",
        "manifest_url": f"/storage/scans/{scan_id}/selected_3dmm_manifest.json",
        "selected_count": len(images),
        "selected_dir": f"scans/{scan_id}/selected_3dmm",
        "selected_images": images,
        "version": "0.1",
    }


def _select_3dmm_samples(
    step: str,
    samples: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    limit = RECONSTRUCTION_SELECTION_LIMITS.get(step, 1)
    ranked = sorted(
        samples,
        key=lambda sample: _reconstruction_score(step, sample),
        reverse=True,
    )
    return ranked[:limit]


def _reconstruction_score(step: str, sample: dict[str, Any]) -> float:
    quality = sample.get("quality") or {}
    base_score = _sample_quality_score(sample)
    yaw_score = _yaw_score(step, quality)
    sharpness = _float_or_zero(quality.get("sharpness"))
    brightness = _brightness_score(_float_or_zero(quality.get("brightness")))
    size = _face_size_score(_float_or_zero(quality.get("faceHeight")))
    top_margin = _hairline_top_score(_float_or_zero(quality.get("faceTop")))

    score = (
        base_score * 0.48
        + yaw_score * 0.22
        + sharpness * 0.12
        + brightness * 0.08
        + size * 0.08
    )

    if step == "hairline":
        score = score * 0.78 + top_margin * 0.22

    return score


def _sample_quality_score(sample: dict[str, Any]) -> float:
    return _float_or_zero((sample.get("quality") or {}).get("score"))


def _yaw_score(step: str, quality: dict[str, Any]) -> float:
    target = RECONSTRUCTION_TARGET_YAW.get(step, 0.0)
    yaw = _float_or_zero(quality.get("yawProxy"))
    tolerance = 0.18 if step in {"left_profile", "right_profile"} else 0.14
    return max(0.0, 1.0 - abs(yaw - target) / tolerance)


def _brightness_score(value: float) -> float:
    if value <= 0.18 or value >= 0.95:
        return 0.0
    if 0.32 <= value <= 0.78:
        return 1.0
    if value < 0.32:
        return (value - 0.18) / (0.32 - 0.18)
    return 1.0 - (value - 0.78) / (0.95 - 0.78)


def _face_size_score(value: float) -> float:
    if value <= 0.32 or value >= 0.86:
        return 0.0
    if 0.44 <= value <= 0.74:
        return 1.0
    if value < 0.44:
        return (value - 0.32) / (0.44 - 0.32)
    return 1.0 - (value - 0.74) / (0.86 - 0.74)


def _hairline_top_score(value: float) -> float:
    if value <= 0.03 or value >= 0.28:
        return 0.0
    if 0.07 <= value <= 0.18:
        return 1.0
    if value < 0.07:
        return (value - 0.03) / (0.07 - 0.03)
    return 1.0 - (value - 0.18) / (0.28 - 0.18)


def _selection_reason(step: str, sample: dict[str, Any]) -> str:
    quality = sample.get("quality") or {}
    return (
        f"step={step}; quality={_sample_quality_score(sample):.3f}; "
        f"yaw={_float_or_zero(quality.get('yawProxy')):.3f}; "
        f"sharpness={_float_or_zero(quality.get('sharpness')):.3f}"
    )


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


def _float_or_zero(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
