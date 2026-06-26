"""Smoke-test KeenTools FaceBuilder automation inside headless Blender.

Run this script with Blender, not plain Python:

    blender --background --python experiments/facebuilder_bridge/blender_facebuilder_smoke.py -- --output private_outputs/facebuilder_bridge/headless_smoke.json

The test does not use private photos. It verifies that Blender can load the
KeenTools extension, import the local pykeentools core, construct a FaceBuilder
object, and call a no-face detection path on a generated blank image.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import traceback
from pathlib import Path
from typing import Any

import bpy
import numpy as np


def _parse_args(argv: list[str]) -> argparse.Namespace:
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("private_outputs/facebuilder_bridge/headless_smoke.json"),
        help="Where to write the JSON smoke-test result.",
    )
    parser.add_argument(
        "--skip-blank-detect",
        action="store_true",
        help="Skip calling FaceBuilder.detect_faces on a generated blank image.",
    )
    return parser.parse_args(argv)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return {
            "type": "ndarray",
            "shape": list(value.shape),
            "dtype": str(value.dtype),
        }
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return str(value)


def _safe_call(label: str, func: Any, result: dict[str, Any]) -> Any:
    try:
        value = func()
    except Exception as exc:  # noqa: BLE001 - this is a diagnostic tool.
        result[label] = {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=4),
        }
        return None

    result[label] = {"ok": True, "value": _jsonable(value)}
    return value


def _len_or_repr(value: Any) -> dict[str, Any]:
    try:
        length = len(value)
    except Exception:
        length = None
    return {
        "type": type(value).__name__,
        "length": length,
        "repr": repr(value)[:500],
    }


def main() -> int:
    args = _parse_args(sys.argv)
    result: dict[str, Any] = {
        "ok": False,
        "blender": {
            "version": bpy.app.version_string,
            "background": bpy.app.background,
            "python": sys.version,
        },
        "steps": {},
        "automation_assessment": {},
    }

    kt_module = _safe_call(
        "import_keentools_addon",
        lambda: importlib.import_module("bl_ext.user_default.keentools"),
        result["steps"],
    )
    if kt_module is not None:
        result["keentools_addon"] = {
            "module": getattr(kt_module, "__name__", None),
            "file": getattr(kt_module, "__file__", None),
        }

    loader_mod = _safe_call(
        "import_pykeentools_loader",
        lambda: importlib.import_module(
            "bl_ext.user_default.keentools."
            "blender_independent_packages.pykeentools_loader"
        ),
        result["steps"],
    )
    if loader_mod is None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"FACEBUILDER_SMOKE_JSON {args.output}")
        return 2

    result["pykeentools_loader"] = {
        "is_installed": _safe_call(
            "pykeentools_is_installed",
            lambda: loader_mod.is_installed(True),
            result["steps"],
        ),
        "installation_status": _safe_call(
            "pykeentools_installation_status",
            lambda: loader_mod.installation_status(True),
            result["steps"],
        ),
    }

    pkt = _safe_call("load_pykeentools_core", loader_mod.module, result["steps"])
    if pkt is None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"FACEBUILDER_SMOKE_JSON {args.output}")
        return 3

    result["pykeentools_core"] = {
        "file": getattr(pkt, "__file__", None),
        "version": str(getattr(pkt, "__version__", None)),
        "build_time": str(getattr(pkt, "build_time", None)),
        "has_facebuilder": hasattr(pkt, "FaceBuilder"),
        "has_camera_input_interface": hasattr(pkt, "FaceBuilderCameraInputI"),
        "has_texture_builder": hasattr(pkt, "texture_builder"),
        "has_progress_callback": hasattr(pkt, "ProgressCallback"),
    }

    class SmokeCameraInput(pkt.FaceBuilderCameraInputI):
        def projection(self, keyframe: int) -> Any:
            return np.eye(4, dtype=np.float32)

        def view(self, keyframe: int) -> Any:
            return np.eye(4, dtype=np.float32)

        def image_size(self, keyframe: int) -> Any:
            return (256, 256)

    fb = _safe_call(
        "create_facebuilder_instance",
        lambda: pkt.FaceBuilder(SmokeCameraInput()),
        result["steps"],
    )
    if fb is not None:
        _safe_call(
            "facebuilder_set_use_emotions_false",
            lambda: fb.set_use_emotions(False),
            result["steps"],
        )
        _safe_call("facebuilder_keyframes_initial", fb.keyframes, result["steps"])
        _safe_call(
            "facebuilder_set_centered_geo_keyframe_0",
            lambda: fb.set_centered_geo_keyframe(0),
            result["steps"],
        )
        _safe_call("facebuilder_keyframes_after_set", fb.keyframes, result["steps"])
        _safe_call(
            "facebuilder_pixel_aspect_ratio_0",
            lambda: fb.pixel_aspect_ratio(0),
            result["steps"],
        )

        if not args.skip_blank_detect:

            def detect_blank() -> Any:
                image = np.zeros((128, 128, 4), dtype=np.float32)
                image[:, :, 3] = 1.0
                faces = fb.detect_faces(image, 1.0)
                return _len_or_repr(faces)

            _safe_call(
                "facebuilder_detect_faces_blank_rgba",
                detect_blank,
                result["steps"],
            )

    if hasattr(pkt, "texture_builder"):
        texture_builder = pkt.texture_builder
        result["texture_builder"] = {
            "has_frame_data": hasattr(texture_builder, "FrameData"),
            "has_build_texture": hasattr(texture_builder, "build_texture"),
        }
        if hasattr(texture_builder, "FrameData"):
            _safe_call(
                "texture_builder_create_frame_data",
                texture_builder.FrameData,
                result["steps"],
            )

    result["automation_assessment"] = {
        "headless_blender_loads_keentools": result["steps"]
        .get("import_keentools_addon", {})
        .get("ok", False),
        "headless_pykeentools_core_ok": result["steps"]
        .get("load_pykeentools_core", {})
        .get("ok", False),
        "facebuilder_object_constructible": result["steps"]
        .get("create_facebuilder_instance", {})
        .get("ok", False),
        "blank_detect_faces_callable": result["steps"]
        .get("facebuilder_detect_faces_blank_rgba", {})
        .get("ok", False),
        "texture_builder_api_visible": result.get("texture_builder", {}).get(
            "has_build_texture", False
        ),
        "next_risk": (
            "Photo import and auto-align still need a real image/keyframe test. "
            "This smoke test proves the local headless API is reachable."
        ),
    }
    result["ok"] = all(
        [
            result["automation_assessment"]["headless_blender_loads_keentools"],
            result["automation_assessment"]["headless_pykeentools_core_ok"],
            result["automation_assessment"]["facebuilder_object_constructible"],
            result["automation_assessment"]["texture_builder_api_visible"],
        ]
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"FACEBUILDER_SMOKE_OK {result['ok']}")
    print(f"FACEBUILDER_SMOKE_JSON {args.output}")
    return 0 if result["ok"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
