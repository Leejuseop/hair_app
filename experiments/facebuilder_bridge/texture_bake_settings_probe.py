"""Bake FaceBuilder texture variants from an existing blend.

This diagnostic script is intended for parity checks against the FaceBuilder UI
"Create Texture" button. It runs inside Blender, changes TextureBuilder options,
bakes several textures, and compares them with an optional reference PNG.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import bpy


def _parse_args(argv: list[str]) -> argparse.Namespace:
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reference", type=Path, default=None)
    parser.add_argument("--headnum", type=int, default=0)
    return parser.parse_args(argv)


def _safe_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _load_reference(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    try:
        from PIL import Image
        import numpy as np
    except Exception:
        return None
    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA")).astype("int16")


def _compare_image_to_reference(image: Any, reference: Any) -> dict[str, Any] | None:
    if reference is None:
        return None
    try:
        import numpy as np
    except Exception:
        return None
    width, height = image.size
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    arr = np.clip(pixels.reshape((height, width, 4)) * 255.0, 0, 255).astype("int16")
    if arr.shape != reference.shape:
        return {"error": "shape_mismatch", "image_shape": list(arr.shape), "reference_shape": list(reference.shape)}
    diff = np.abs(arr[:, :, :3] - reference[:, :, :3])
    changed_gt20 = np.any(diff > 20, axis=2)
    nonblack_union = (arr[:, :, :3].sum(axis=2) > 8) | (reference[:, :, :3].sum(axis=2) > 8)
    return {
        "mean_abs_rgb_all": float(diff.mean()),
        "rms_rgb_all": float(math.sqrt(float((diff.astype("float32") ** 2).mean()))),
        "max_abs_rgb": int(diff.max()),
        "changed_rgb_gt20_ratio": float(changed_gt20.mean()),
        "mean_abs_rgb_union_nonblack": float(diff[nonblack_union].mean()) if bool(nonblack_union.any()) else None,
    }


def main() -> int:
    args = _parse_args(sys.argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    reference = _load_reference(args.reference)

    from bl_ext.user_default.keentools.addon_config import fb_settings
    from bl_ext.user_default.keentools.utils.materials import bake_tex

    settings = fb_settings()
    settings.current_headnum = args.headnum
    head = settings.get_head(args.headnum)
    if head is None:
        raise RuntimeError(f"Head {args.headnum} not found")

    variants = [
        {"name": "angle_0", "angle": 0.0, "equalize_brightness": False, "equalize_colour": False, "fill_gaps": False},
        {"name": "angle_10", "angle": 10.0, "equalize_brightness": False, "equalize_colour": False, "fill_gaps": False},
        {"name": "angle_35", "angle": 35.0, "equalize_brightness": False, "equalize_colour": False, "fill_gaps": False},
        {"name": "angle_70", "angle": 70.0, "equalize_brightness": False, "equalize_colour": False, "fill_gaps": False},
        {"name": "angle_100", "angle": 100.0, "equalize_brightness": False, "equalize_colour": False, "fill_gaps": False},
        {"name": "angle_100_equalized", "angle": 100.0, "equalize_brightness": True, "equalize_colour": True, "fill_gaps": False},
        {"name": "angle_100_fill", "angle": 100.0, "equalize_brightness": False, "equalize_colour": False, "fill_gaps": True},
    ]

    rows: list[dict[str, Any]] = []
    for variant in variants:
        settings.tex_width = 2048
        settings.tex_height = 2048
        settings.tex_face_angles_affection = variant["angle"]
        settings.tex_equalize_brightness = variant["equalize_brightness"]
        settings.tex_equalize_colour = variant["equalize_colour"]
        settings.tex_fill_gaps = variant["fill_gaps"]

        tex_name = f"HairAppProbe_{variant['name']}"
        status = bake_tex(args.headnum, tex_name)
        image = bpy.data.images.get(tex_name)
        texture_path = args.output_dir / f"{variant['name']}.png"
        row = {
            "variant": variant,
            "status_success": bool(status.success),
            "status_error_message": status.error_message,
            "image_exists": image is not None,
            "image_size": list(image.size) if image else None,
            "texture_path": _safe_path(texture_path) if image else None,
            "reference_metrics": None,
        }
        if image is not None:
            image.filepath_raw = str(texture_path)
            image.file_format = "PNG"
            image.save()
            row["reference_metrics"] = _compare_image_to_reference(image, reference)
        rows.append(row)

    report = {
        "schema_version": "hair_app_texture_bake_settings_probe_v1",
        "created_at_unix": time.time(),
        "blend_file": bpy.data.filepath,
        "reference": _safe_path(args.reference),
        "headnum": args.headnum,
        "head_object": head.headobj.name if head.headobj else None,
        "cameras": [
            {
                "index": index,
                "image_name": camera.cam_image.name if camera.cam_image else None,
                "has_pins": camera.has_pins(),
                "pins_count_prop": camera.pins_count,
                "use_in_tex_baking": bool(camera.use_in_tex_baking),
                "focal": camera.focal,
                "auto_focal_estimation": camera.auto_focal_estimation,
            }
            for index, camera in enumerate(head.cameras)
        ],
        "rows": rows,
    }
    (args.output_dir / "texture_bake_settings_probe_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"TEXTURE_BAKE_SETTINGS_PROBE_JSON {args.output_dir / 'texture_bake_settings_probe_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
