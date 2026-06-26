"""Create visual-review texture completions from sparse observed UV atlases.

This script makes private diagnostic textures easier to inspect by filling
unobserved UV texels. It does not create validated production textures: the
output is a review aid so humans can compare mesh candidates without large
black holes dominating the view.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage

from texture_baker_loader import default_private_root
from textured_mesh_preview import DEFAULT_TEXTURE_RUNS, estimate_skin_color


def source_texture_path(texture_dir: Path) -> Path:
    for name in ("base_color_preview_filled.png", "base_color_observed.png"):
        path = texture_dir / name
        if path.exists():
            return path
    raise FileNotFoundError(f"No observed texture found under: {texture_dir}")


def complete_texture(
    source: np.ndarray,
    *,
    near_distance: float,
    far_distance: float,
    smooth_sigma: float,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    observed = np.sum(source, axis=2) > 30
    skin_color = estimate_skin_color(source).astype(np.float32)

    if not np.any(observed):
        completed = np.zeros_like(source, dtype=np.uint8)
        completed[:] = np.rint(skin_color).astype(np.uint8)
        completion_mask = np.full(source.shape[:2], 255, dtype=np.uint8)
        return completed, completion_mask, {"observed_fraction": 0.0, "skin_color": skin_color.tolist()}

    distance, indices = ndimage.distance_transform_edt(~observed, return_indices=True)
    nearest = source[indices[0], indices[1]].astype(np.float32)
    smoothed = ndimage.gaussian_filter(nearest, sigma=(smooth_sigma, smooth_sigma, 0.0))

    blend = np.clip((distance - near_distance) / max(far_distance - near_distance, 1.0), 0.0, 1.0)
    filled = (smoothed * (1.0 - blend[..., None])) + (skin_color[None, None, :] * blend[..., None])

    completed = source.astype(np.float32, copy=True)
    completed[~observed] = filled[~observed]
    completed = np.clip(completed, 0, 255).astype(np.uint8)

    completion_mask = np.zeros(source.shape[:2], dtype=np.uint8)
    completion_mask[~observed] = 255
    stats = {
        "observed_fraction": float(observed.mean()),
        "completed_fraction": float((~observed).mean()),
        "skin_color": [float(value) for value in skin_color],
        "near_distance": near_distance,
        "far_distance": far_distance,
        "smooth_sigma": smooth_sigma,
        "max_hole_distance": float(distance.max()),
    }
    return completed, completion_mask, stats


def complete_person(
    *,
    private_root: Path,
    person: str,
    texture_name: str,
    near_distance: float,
    far_distance: float,
    smooth_sigma: float,
) -> dict[str, Any]:
    texture_dir = private_root / "output" / person / "texture_baker" / texture_name
    source_path = source_texture_path(texture_dir)
    source = np.asarray(Image.open(source_path).convert("RGB"), dtype=np.uint8)
    completed, completion_mask, stats = complete_texture(
        source,
        near_distance=near_distance,
        far_distance=far_distance,
        smooth_sigma=smooth_sigma,
    )

    output_path = texture_dir / "base_color_visual_completed.png"
    mask_path = texture_dir / "visual_completion_mask.png"
    manifest_path = texture_dir / "visual_completion_manifest.json"
    Image.fromarray(completed, mode="RGB").save(output_path)
    Image.fromarray(completion_mask, mode="L").save(mask_path)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "person": person,
        "texture_name": texture_name,
        "purpose": "Visual-review completion to reduce black holes for mesh candidate selection.",
        "privacy": "Private biometric/runtime artifact. Do not commit generated textures or manifests.",
        "source_texture": str(source_path),
        "outputs": {
            "base_color_visual_completed": str(output_path),
            "visual_completion_mask": str(mask_path),
            "visual_completion_manifest": str(manifest_path),
        },
        "stats": stats,
        "limitations": [
            "Nearest-observation plus skin-color fallback, not AI or production texture completion.",
            "Preserves observed nonblack texels and fills unobserved texels for visual comparison only.",
            "Does not infer true rear head, hair, teeth, mouth cavity, lighting, or albedo.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create visual-review completed UV textures.")
    parser.add_argument("--private-root", type=Path, default=None)
    parser.add_argument("--person", action="append", default=None)
    parser.add_argument("--texture-name", default=None)
    parser.add_argument("--near-distance", type=float, default=24.0)
    parser.add_argument("--far-distance", type=float, default=180.0)
    parser.add_argument("--smooth-sigma", type=float, default=2.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    private_root = args.private_root or default_private_root()
    people = args.person or list(DEFAULT_TEXTURE_RUNS)
    reports = []
    for person in people:
        texture_name = args.texture_name or DEFAULT_TEXTURE_RUNS[person]
        reports.append(
            complete_person(
                private_root=private_root,
                person=person,
                texture_name=texture_name,
                near_distance=args.near_distance,
                far_distance=args.far_distance,
                smooth_sigma=args.smooth_sigma,
            )
        )

    print(
        json.dumps(
            {
                "private_root": str(private_root),
                "reports": [
                    {
                        "person": report["person"],
                        "texture_name": report["texture_name"],
                        "output": report["outputs"]["base_color_visual_completed"],
                        "observed_fraction": report["stats"]["observed_fraction"],
                    }
                    for report in reports
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
