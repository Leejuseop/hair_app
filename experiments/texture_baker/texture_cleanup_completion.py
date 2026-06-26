"""Clean and complete private v2 face texture atlases for review.

This post-process keeps the observed v2 atlas intact and writes a separate
cleanup/completion texture. It removes low-confidence or color-outlier skin
texels from review use, fills them from trusted neighboring skin where possible,
and falls back to simple FLAME-region material colors for unobserved areas.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from observed_texture_baker import fill_preview_holes
from texture_baker_loader import default_private_root, load_person
from textured_mesh_preview import (
    load_flame_masks,
    read_ply,
    resolve_flame_masks,
    resolve_uv_coords,
)


DEFAULT_PEOPLE = ("\uc8fc\uc12d", "\uc740\ucc44")
DEFAULT_TEXTURE_NAME = "observed_v2_camera_visibility_front45_preview"
FEATURE_MASKS = ("lips", "eye_region", "left_eye_region", "right_eye_region", "left_eyeball", "right_eyeball")
SKIN_MASKS = ("face", "forehead", "nose", "neck", "left_ear", "right_ear", "boundary")
SCALP_MASKS = ("scalp",)


def dilate_binary_mask(mask: np.ndarray, iterations: int) -> np.ndarray:
    result = mask.astype(bool, copy=True)
    height, width = result.shape
    for _ in range(max(iterations, 0)):
        padded = np.pad(result, ((1, 1), (1, 1)), mode="constant", constant_values=False)
        neighbors = [padded[dy : dy + height, dx : dx + width] for dy in range(3) for dx in range(3)]
        result = np.logical_or.reduce(neighbors)
    return result


def erode_binary_mask(mask: np.ndarray, iterations: int) -> np.ndarray:
    result = mask.astype(bool, copy=True)
    height, width = result.shape
    for _ in range(max(iterations, 0)):
        padded = np.pad(result, ((1, 1), (1, 1)), mode="constant", constant_values=False)
        neighbors = [padded[dy : dy + height, dx : dx + width] for dy in range(3) for dx in range(3)]
        result = np.logical_and.reduce(neighbors)
        if not np.any(result):
            break
    return result


def rasterize_triangle_mask(mask: np.ndarray, points: np.ndarray) -> None:
    height, width = mask.shape
    min_x = max(int(np.floor(points[:, 0].min())), 0)
    max_x = min(int(np.ceil(points[:, 0].max())), width - 1)
    min_y = max(int(np.floor(points[:, 1].min())), 0)
    max_y = min(int(np.ceil(points[:, 1].max())), height - 1)
    if max_x < min_x or max_y < min_y:
        return

    p0, p1, p2 = points.astype(np.float32)
    area = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
    if abs(float(area)) < 1e-8:
        return

    xs = np.arange(min_x, max_x + 1, dtype=np.float32)
    ys = np.arange(min_y, max_y + 1, dtype=np.float32)
    grid_x, grid_y = np.meshgrid(xs, ys)
    w0 = ((p1[1] - p2[1]) * (grid_x - p2[0]) + (p2[0] - p1[0]) * (grid_y - p2[1])) / area
    w1 = ((p2[1] - p0[1]) * (grid_x - p2[0]) + (p0[0] - p2[0]) * (grid_y - p2[1])) / area
    w2 = 1.0 - w0 - w1
    inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
    if np.any(inside):
        mask[min_y : max_y + 1, min_x : max_x + 1][inside] = True


def uv_points(uv_coords: np.ndarray, atlas_size: int) -> np.ndarray:
    points = np.zeros((uv_coords.shape[0], 2), dtype=np.float32)
    points[:, 0] = np.clip(uv_coords[:, 0], 0.0, 1.0) * (atlas_size - 1)
    # The current preview renderer samples v2 atlases with --uv-mode flip_y.
    points[:, 1] = (1.0 - np.clip(uv_coords[:, 1], 0.0, 1.0)) * (atlas_size - 1)
    return points


def region_mask(
    *,
    faces: np.ndarray,
    uv_screen: np.ndarray,
    vertex_count: int,
    vertex_indices: np.ndarray,
    atlas_size: int,
    min_vertices: int,
) -> np.ndarray:
    vertex_mask = np.zeros((vertex_count,), dtype=bool)
    valid = vertex_indices[(vertex_indices >= 0) & (vertex_indices < vertex_count)]
    vertex_mask[valid] = True
    output = np.zeros((atlas_size, atlas_size), dtype=bool)
    for face in faces:
        if int(vertex_mask[face].sum()) >= min_vertices:
            rasterize_triangle_mask(output, uv_screen[face])
    return output


def build_region_masks(
    *,
    faces: np.ndarray,
    uv_coords: np.ndarray,
    flame_masks: dict[str, np.ndarray],
    atlas_size: int,
) -> dict[str, np.ndarray]:
    uv_screen = uv_points(uv_coords, atlas_size)
    masks: dict[str, np.ndarray] = {}
    vertex_count = uv_coords.shape[0]
    for name, indices in flame_masks.items():
        minimum = 2 if name in {"face", "forehead", "scalp", "neck", "lips", "eye_region"} else 1
        masks[name] = region_mask(
            faces=faces,
            uv_screen=uv_screen,
            vertex_count=vertex_count,
            vertex_indices=indices,
            atlas_size=atlas_size,
            min_vertices=minimum,
        )
    return masks


def union_masks(masks: dict[str, np.ndarray], names: tuple[str, ...], shape: tuple[int, int]) -> np.ndarray:
    output = np.zeros(shape, dtype=bool)
    for name in names:
        value = masks.get(name)
        if value is not None:
            output |= value
    return output


def ycbcr_like(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    y = (0.299 * rgb[..., 0]) + (0.587 * rgb[..., 1]) + (0.114 * rgb[..., 2])
    cb = rgb[..., 2] - y
    cr = rgb[..., 0] - y
    return y, cb, cr


def blend_color(a: np.ndarray, b: tuple[int, int, int], alpha: float) -> np.ndarray:
    return np.clip((a * (1.0 - alpha)) + (np.asarray(b, dtype=np.float32) * alpha), 0, 255)


def material_canvas(
    *,
    reference_skin: np.ndarray,
    region_masks: dict[str, np.ndarray],
    shape: tuple[int, int],
) -> np.ndarray:
    skin = np.clip(reference_skin, 45, 235).astype(np.float32)
    canvas = np.tile(skin[None, None, :], (shape[0], shape[1], 1))

    scalp = blend_color(skin, (186, 146, 122), 0.18)
    neck = blend_color(skin, (150, 118, 104), 0.16)
    ear = blend_color(skin, (205, 126, 112), 0.20)
    lip = blend_color(skin, (144, 56, 68), 0.54)
    eye_shadow = blend_color(skin, (95, 70, 66), 0.24)
    eyeball = np.asarray([226, 220, 208], dtype=np.float32)

    for name in SCALP_MASKS:
        mask = region_masks.get(name)
        if mask is not None:
            canvas[mask] = scalp
    for name, color in (("neck", neck), ("boundary", neck), ("left_ear", ear), ("right_ear", ear), ("lips", lip)):
        mask = region_masks.get(name)
        if mask is not None:
            canvas[mask] = color
    for name in ("eye_region", "left_eye_region", "right_eye_region"):
        mask = region_masks.get(name)
        if mask is not None:
            canvas[mask] = eye_shadow
    for name in ("left_eyeball", "right_eyeball"):
        mask = region_masks.get(name)
        if mask is not None:
            canvas[mask] = eyeball
    return np.clip(canvas, 0, 255).astype(np.uint8)


def load_manifest(texture_dir: Path) -> dict[str, Any]:
    path = texture_dir / "texture_manifest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def reference_skin_color(observed: np.ndarray, confidence: np.ndarray, manifest: dict[str, Any]) -> np.ndarray:
    if manifest.get("reference_skin_rgb") is not None:
        return np.asarray(manifest["reference_skin_rgb"], dtype=np.float32)
    valid = (confidence > 20) & (np.sum(observed, axis=2) > 30)
    if int(valid.sum()) < 50:
        return np.asarray([168, 132, 118], dtype=np.float32)
    return np.median(observed[valid].astype(np.float32), axis=0)


def make_cleanup_masks(
    *,
    observed: np.ndarray,
    confidence: np.ndarray,
    region_masks: dict[str, np.ndarray],
    reference_skin: np.ndarray,
    low_confidence_threshold: int,
    face_chroma_threshold: float,
    face_luma_threshold: float,
    forehead_chroma_threshold: float,
    forehead_luma_threshold: float,
) -> dict[str, np.ndarray]:
    shape = observed.shape[:2]
    covered = np.sum(observed, axis=2) > 24
    skin = union_masks(region_masks, SKIN_MASKS, shape)
    scalp = union_masks(region_masks, SCALP_MASKS, shape)
    features = union_masks(region_masks, FEATURE_MASKS, shape)
    forehead = union_masks(region_masks, ("forehead", "scalp"), shape)
    cleanup_region = (skin | scalp) & ~features

    y, cb, cr = ycbcr_like(observed.astype(np.float32))
    ref_rgb = reference_skin.astype(np.float32)
    ref_y = float((0.299 * ref_rgb[0]) + (0.587 * ref_rgb[1]) + (0.114 * ref_rgb[2]))
    ref_cb = float(ref_rgb[2] - ref_y)
    ref_cr = float(ref_rgb[0] - ref_y)
    chroma_distance = np.sqrt((cb - ref_cb) ** 2 + (cr - ref_cr) ** 2)
    luma_distance = np.abs(y - ref_y)

    low_conf = cleanup_region & (confidence <= low_confidence_threshold)
    skin_outlier = cleanup_region & covered & (
        (chroma_distance > face_chroma_threshold) | (luma_distance > face_luma_threshold)
    )
    forehead_outlier = forehead & covered & (
        (chroma_distance > forehead_chroma_threshold) | (luma_distance > forehead_luma_threshold)
    )
    extreme = cleanup_region & covered & ((y < 35) | (y > 242) | (chroma_distance > face_chroma_threshold * 1.65))

    remove = low_conf | extreme | forehead_outlier | (skin_outlier & (confidence <= max(low_confidence_threshold * 3, 24)))
    remove = dilate_binary_mask(remove, 1) & cleanup_region
    trusted = covered & ~remove

    material_only = (skin | scalp | features) & ~trusted
    return {
        "covered": covered,
        "skin": skin,
        "scalp": scalp,
        "features": features,
        "cleanup_region": cleanup_region,
        "low_confidence": low_conf,
        "skin_outlier": skin_outlier,
        "forehead_outlier": forehead_outlier,
        "extreme": extreme,
        "remove": remove,
        "trusted": trusted,
        "material_only": material_only,
    }


def complete_texture(
    *,
    observed: np.ndarray,
    confidence: np.ndarray,
    material: np.ndarray,
    masks: dict[str, np.ndarray],
    fill_iterations: int,
    blend_low_confidence: bool,
) -> np.ndarray:
    trusted = masks["trusted"]
    completed = fill_preview_holes(observed, trusted, fill_iterations, 1)
    remaining_empty = np.sum(completed, axis=2) < 12
    completed[remaining_empty] = material[remaining_empty]

    completed[masks["material_only"]] = material[masks["material_only"]]
    removed = masks["remove"]
    if np.any(removed):
        blended_removed = (completed[removed].astype(np.float32) * 0.55) + (material[removed].astype(np.float32) * 0.45)
        completed[removed] = np.clip(blended_removed, 0, 255).astype(np.uint8)

    if blend_low_confidence:
        low = masks["cleanup_region"] & (confidence <= 32)
        alpha = np.clip((32.0 - confidence.astype(np.float32)) / 32.0, 0.0, 0.75)
        alpha = alpha[..., None]
        blended = (completed.astype(np.float32) * (1.0 - alpha)) + (material.astype(np.float32) * alpha)
        completed[low] = np.clip(blended[low], 0, 255).astype(np.uint8)

    return completed


def pick_mesh_faces(private_root: Path, person: str) -> tuple[np.ndarray, dict[str, Any]]:
    bundle = load_person(person, private_root=private_root)
    for mesh in bundle.meshes:
        if mesh.exists:
            mesh_data = read_ply(Path(mesh.path))
            return mesh_data.faces, {"mesh": asdict(mesh)}
    raise FileNotFoundError(f"No mesh candidate found for {person}")


def process_person(
    *,
    private_root: Path,
    person: str,
    texture_name: str,
    low_confidence_threshold: int,
    face_chroma_threshold: float,
    face_luma_threshold: float,
    forehead_chroma_threshold: float,
    forehead_luma_threshold: float,
    fill_iterations: int,
    blend_low_confidence: bool,
    save_debug_masks: bool,
) -> dict[str, Any]:
    texture_dir = private_root / "output" / person / "texture_baker" / texture_name
    observed_path = texture_dir / "base_color_observed.png"
    confidence_path = texture_dir / "confidence.png"
    if not observed_path.exists() or not confidence_path.exists():
        raise FileNotFoundError(f"Missing observed texture or confidence under {texture_dir}")

    observed = np.asarray(Image.open(observed_path).convert("RGB"), dtype=np.uint8)
    confidence = np.asarray(Image.open(confidence_path).convert("L"), dtype=np.uint8)
    manifest = load_manifest(texture_dir)
    reference_skin = reference_skin_color(observed, confidence, manifest)

    uv_coords = np.load(resolve_uv_coords(private_root, None)).astype(np.float32)
    flame_masks = load_flame_masks(resolve_flame_masks(private_root, None))
    faces, mesh_info = pick_mesh_faces(private_root, person)
    region_masks = build_region_masks(
        faces=faces,
        uv_coords=uv_coords,
        flame_masks=flame_masks,
        atlas_size=observed.shape[0],
    )
    cleanup_masks = make_cleanup_masks(
        observed=observed,
        confidence=confidence,
        region_masks=region_masks,
        reference_skin=reference_skin,
        low_confidence_threshold=low_confidence_threshold,
        face_chroma_threshold=face_chroma_threshold,
        face_luma_threshold=face_luma_threshold,
        forehead_chroma_threshold=forehead_chroma_threshold,
        forehead_luma_threshold=forehead_luma_threshold,
    )
    material = material_canvas(
        reference_skin=reference_skin,
        region_masks=region_masks,
        shape=observed.shape[:2],
    )
    completed = complete_texture(
        observed=observed,
        confidence=confidence,
        material=material,
        masks=cleanup_masks,
        fill_iterations=fill_iterations,
        blend_low_confidence=blend_low_confidence,
    )

    output_path = texture_dir / "base_color_cleanup_completed.png"
    Image.fromarray(completed, mode="RGB").save(output_path)
    Image.fromarray(material, mode="RGB").save(texture_dir / "base_color_material_reference.png")
    Image.fromarray((cleanup_masks["remove"].astype(np.uint8) * 255), mode="L").save(texture_dir / "cleanup_removed_mask.png")
    Image.fromarray((cleanup_masks["material_only"].astype(np.uint8) * 255), mode="L").save(texture_dir / "completion_replaced_mask.png")

    debug_outputs: dict[str, str] = {}
    if save_debug_masks:
        for name, mask in region_masks.items():
            path = texture_dir / f"region_{name}.png"
            Image.fromarray(mask.astype(np.uint8) * 255, mode="L").save(path)
            debug_outputs[f"region_{name}"] = str(path)

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "person": person,
        "texture_name": texture_name,
        "privacy": "Private biometric runtime artifact. Do not commit generated textures or masks.",
        "input_observed": str(observed_path),
        "input_confidence": str(confidence_path),
        "output_cleanup_completed": str(output_path),
        "output_material_reference": str(texture_dir / "base_color_material_reference.png"),
        "output_cleanup_removed_mask": str(texture_dir / "cleanup_removed_mask.png"),
        "output_completion_replaced_mask": str(texture_dir / "completion_replaced_mask.png"),
        "reference_skin_rgb": [float(value) for value in reference_skin],
        "settings": {
            "low_confidence_threshold": low_confidence_threshold,
            "face_chroma_threshold": face_chroma_threshold,
            "face_luma_threshold": face_luma_threshold,
            "forehead_chroma_threshold": forehead_chroma_threshold,
            "forehead_luma_threshold": forehead_luma_threshold,
            "fill_iterations": fill_iterations,
            "blend_low_confidence": blend_low_confidence,
            "save_debug_masks": save_debug_masks,
        },
        "counts": {
            "covered_texels": int(cleanup_masks["covered"].sum()),
            "trusted_texels": int(cleanup_masks["trusted"].sum()),
            "removed_texels": int(cleanup_masks["remove"].sum()),
            "material_replaced_texels": int(cleanup_masks["material_only"].sum()),
            "cleanup_region_texels": int(cleanup_masks["cleanup_region"].sum()),
            "low_confidence_texels": int(cleanup_masks["low_confidence"].sum()),
            "skin_outlier_texels": int(cleanup_masks["skin_outlier"].sum()),
            "forehead_outlier_texels": int(cleanup_masks["forehead_outlier"].sum()),
            "extreme_texels": int(cleanup_masks["extreme"].sum()),
        },
        "region_mask_names": sorted(region_masks.keys()),
        "debug_outputs": debug_outputs,
        **mesh_info,
    }
    (texture_dir / "cleanup_completion_manifest.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean and complete v2 face texture atlases for review.")
    parser.add_argument("--private-root", type=Path, default=None)
    parser.add_argument("--person", action="append", default=None)
    parser.add_argument("--texture-name", default=DEFAULT_TEXTURE_NAME)
    parser.add_argument("--low-confidence-threshold", type=int, default=8)
    parser.add_argument("--face-chroma-threshold", type=float, default=34.0)
    parser.add_argument("--face-luma-threshold", type=float, default=64.0)
    parser.add_argument("--forehead-chroma-threshold", type=float, default=24.0)
    parser.add_argument("--forehead-luma-threshold", type=float, default=44.0)
    parser.add_argument("--fill-iterations", type=int, default=96)
    parser.add_argument("--no-blend-low-confidence", action="store_true")
    parser.add_argument("--save-debug-masks", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    private_root = args.private_root or default_private_root()
    people = args.person or list(DEFAULT_PEOPLE)
    reports = [
        process_person(
            private_root=private_root,
            person=person,
            texture_name=args.texture_name,
            low_confidence_threshold=args.low_confidence_threshold,
            face_chroma_threshold=args.face_chroma_threshold,
            face_luma_threshold=args.face_luma_threshold,
            forehead_chroma_threshold=args.forehead_chroma_threshold,
            forehead_luma_threshold=args.forehead_luma_threshold,
            fill_iterations=args.fill_iterations,
            blend_low_confidence=not args.no_blend_low_confidence,
            save_debug_masks=args.save_debug_masks,
        )
        for person in people
    ]
    print(
        json.dumps(
            {
                "private_root": str(private_root),
                "people": [
                    {
                        "person": report["person"],
                        "output_cleanup_completed": report["output_cleanup_completed"],
                        "removed_texels": report["counts"]["removed_texels"],
                        "material_replaced_texels": report["counts"]["material_replaced_texels"],
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
