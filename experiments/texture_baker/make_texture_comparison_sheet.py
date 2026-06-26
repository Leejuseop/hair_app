"""Create one large 8-view model comparison sheet for private texture previews."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from texture_baker_loader import MeshCandidate, default_private_root, load_person
from textured_mesh_preview import (
    DEFAULT_TEXTURE_RUNS,
    build_material_vertex_colors,
    estimate_skin_color,
    load_flame_masks,
    read_ply,
    render_mesh,
    resolve_flame_masks,
    resolve_uv_coords,
    resolve_valid_vertices,
    texture_path_for_run,
)


PERSON_LABELS = {
    "\uc8fc\uc12d": "Juseop",
    "\uc740\ucc44": "Eunchae",
}
DEFAULT_YAW_DEGREES = (0, 45, 90, 135, 180, 225, 270, 315)


def draw_label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fill: tuple[int, int, int]) -> None:
    draw.text(xy, text, fill=fill)


def render_cell(
    *,
    mesh: MeshCandidate,
    texture: np.ndarray,
    uv_coords: np.ndarray,
    valid_vertices: np.ndarray | None,
    yaw_degree: int,
    image_size: int,
    padding: int,
    uv_mode: str,
    depth_mode: str,
    mask_mode: str,
    flame_masks: dict[str, np.ndarray],
    material_fallback: bool,
    fallback_dark_threshold: int,
    confidence: np.ndarray | None,
    fallback_confidence_threshold: int,
    eye_overlay: bool,
) -> Image.Image:
    mesh_data = read_ply(Path(mesh.path))
    if mesh_data.vertices.shape[0] != uv_coords.shape[0]:
        raise ValueError(
            f"UV coordinate count does not match mesh vertices for {mesh.key}: "
            f"mesh={mesh_data.vertices.shape[0]}, uv={uv_coords.shape[0]}"
        )

    material_vertex_colors = None
    if material_fallback:
        material_vertex_colors = build_material_vertex_colors(
            mesh_data.vertices.shape[0],
            flame_masks,
            estimate_skin_color(texture),
        )

    image = render_mesh(
        mesh=mesh_data,
        uv_coords=uv_coords,
        texture=texture,
        image_size=image_size,
        padding=padding,
        uv_mode=uv_mode,
        depth_mode=depth_mode,
        view=f"yaw_{yaw_degree:03d}",
        valid_vertices=valid_vertices,
        mask_mode=mask_mode,
        material_vertex_colors=material_vertex_colors,
        fallback_dark_threshold=fallback_dark_threshold,
        confidence=confidence,
        fallback_confidence_threshold=fallback_confidence_threshold,
        flame_masks=flame_masks,
        eye_overlay=eye_overlay,
    )
    return Image.fromarray(image, mode="RGB")


def make_sheet(
    *,
    private_root: Path,
    people: list[str],
    texture_kind: str,
    uv_coords: np.ndarray,
    valid_vertices: np.ndarray | None,
    image_size: int,
    padding: int,
    uv_mode: str,
    depth_mode: str,
    mask_mode: str,
    flame_masks: dict[str, np.ndarray],
    material_fallback: bool,
    fallback_dark_threshold: int,
    fallback_confidence_threshold: int,
    eye_overlay: bool,
    yaw_degrees: tuple[int, ...],
    texture_name_override: str | None,
    output_path: Path,
) -> dict[str, Any]:
    rows: list[tuple[str, MeshCandidate, str, Path]] = []
    for person in people:
        texture_name = texture_name_override or DEFAULT_TEXTURE_RUNS[person]
        texture_dir = private_root / "output" / person / "texture_baker" / texture_name
        texture_path = texture_path_for_run(texture_dir, texture_kind)
        bundle = load_person(person, private_root=private_root)
        for mesh in bundle.meshes:
            if mesh.exists:
                rows.append((person, mesh, texture_name, texture_path))

    if not rows:
        raise ValueError("No mesh candidates found.")

    left_width = 330
    header_height = 92
    row_gap = 16
    col_gap = 10
    footer_height = 52
    cell = image_size
    width = left_width + (len(yaw_degrees) * cell) + ((len(yaw_degrees) - 1) * col_gap)
    height = header_height + (len(rows) * cell) + ((len(rows) - 1) * row_gap) + footer_height
    sheet = Image.new("RGB", (width, height), (28, 28, 28))
    draw = ImageDraw.Draw(sheet)

    title = "Observed Face Texture on Base Mesh Candidates - 8 yaw views"
    draw_label(draw, (18, 16), title, (245, 245, 245))
    subtitle = f"uv={uv_mode}, depth={depth_mode}, texture={texture_kind}, diagnostic orthographic preview"
    draw_label(draw, (18, 42), subtitle, (180, 180, 180))

    for col, yaw in enumerate(yaw_degrees):
        x = left_width + col * (cell + col_gap)
        draw_label(draw, (x + 8, 68), f"yaw {yaw:03d}", (235, 235, 235))

    rendered: list[dict[str, Any]] = []
    for row_index, (person, mesh, texture_name, texture_path) in enumerate(rows):
        y = header_height + row_index * (cell + row_gap)
        person_label = PERSON_LABELS.get(person, person)
        draw.rectangle((0, y, left_width - 12, y + cell), fill=(38, 38, 38))
        draw_label(draw, (18, y + 22), person_label, (255, 255, 255))
        draw_label(draw, (18, y + 50), mesh.key, (215, 215, 215))
        draw_label(draw, (18, y + 80), texture_name[:38], (150, 150, 150))

        texture = np.asarray(Image.open(texture_path).convert("RGB"), dtype=np.uint8)
        confidence_path = texture_path.parent / "confidence.png"
        confidence = None
        if fallback_confidence_threshold > 0 and confidence_path.exists():
            confidence = np.asarray(Image.open(confidence_path).convert("L"), dtype=np.uint8)
        mesh_outputs: list[str] = []
        for col, yaw in enumerate(yaw_degrees):
            cell_image = render_cell(
                mesh=mesh,
                texture=texture,
                uv_coords=uv_coords,
                valid_vertices=valid_vertices,
                yaw_degree=yaw,
                image_size=image_size,
                padding=padding,
                uv_mode=uv_mode,
                depth_mode=depth_mode,
                mask_mode=mask_mode,
                flame_masks=flame_masks,
                material_fallback=material_fallback,
                fallback_dark_threshold=fallback_dark_threshold,
                confidence=confidence,
                fallback_confidence_threshold=fallback_confidence_threshold,
                eye_overlay=eye_overlay,
            )
            x = left_width + col * (cell + col_gap)
            sheet.paste(cell_image, (x, y))
            mesh_outputs.append(f"sheet cell yaw_{yaw:03d}")

        rendered.append(
            {
                "person": person,
                "person_label": person_label,
                "mesh": asdict(mesh),
                "texture_name": texture_name,
                "texture_path": str(texture_path),
                "confidence_path": str(confidence_path) if confidence is not None else None,
                "outputs": mesh_outputs,
            }
        )

    footer_y = height - footer_height + 12
    draw_label(
        draw,
        (18, footer_y),
        "Private diagnostic runtime artifact. Not final lighting, eyes, mouth interior, scalp, or completion.",
        (190, 190, 190),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "output_path": str(output_path),
        "people": people,
        "texture_kind": texture_kind,
        "image_size": image_size,
        "padding": padding,
        "uv_mode": uv_mode,
        "depth_mode": depth_mode,
        "mask_mode": mask_mode,
        "material_fallback": material_fallback,
        "fallback_dark_threshold": fallback_dark_threshold,
        "fallback_confidence_threshold": fallback_confidence_threshold,
        "eye_overlay": eye_overlay,
        "yaw_degrees": list(yaw_degrees),
        "texture_name_override": texture_name_override,
        "rendered": rendered,
        "limitations": [
            "One-file visual comparison sheet for manual model selection.",
            "Diagnostic orthographic CPU rendering only.",
            "Does not use fitted tracking cameras, perspective intrinsics, production lighting, or validated texture completion.",
        ],
    }
    output_path.with_suffix(".json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create one private 8-view texture/model comparison sheet.")
    parser.add_argument("--private-root", type=Path, default=None)
    parser.add_argument("--person", action="append", default=None)
    parser.add_argument("--texture-kind", choices=["preview_filled", "visual_completed", "observed"], default="preview_filled")
    parser.add_argument("--texture-name", default=None)
    parser.add_argument("--uv-coords", type=Path, default=None)
    parser.add_argument("--valid-vertices", type=Path, default=None)
    parser.add_argument("--flame-masks", type=Path, default=None)
    parser.add_argument("--mask-mode", choices=["none", "any-valid", "all-valid"], default="none")
    parser.add_argument("--material-fallback", action="store_true")
    parser.add_argument("--fallback-dark-threshold", type=int, default=30)
    parser.add_argument("--fallback-confidence-threshold", type=int, default=0)
    parser.add_argument("--eye-overlay", action="store_true")
    parser.add_argument("--image-size", type=int, default=512)
    parser.add_argument("--padding", type=int, default=42)
    parser.add_argument("--uv-mode", default="flip_y")
    parser.add_argument("--depth-mode", default="max")
    parser.add_argument("--yaw-degree", action="append", type=int, default=None)
    parser.add_argument("--output-path", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    private_root = args.private_root or default_private_root()
    people = args.person or ["\uc8fc\uc12d", "\uc740\ucc44"]
    yaw_degrees = tuple(args.yaw_degree or DEFAULT_YAW_DEGREES)
    uv_path = resolve_uv_coords(private_root, args.uv_coords)
    valid_path = resolve_valid_vertices(private_root, args.valid_vertices)
    flame_masks_path = resolve_flame_masks(private_root, args.flame_masks)
    uv_coords = np.load(uv_path)
    valid_vertices = np.load(valid_path) if valid_path is not None else None
    flame_masks = load_flame_masks(flame_masks_path)

    output_path = args.output_path
    if output_path is None:
        output_path = (
            private_root
            / "output"
            / "_comparison"
            / "face_texture_model_comparison_8view.png"
        )

    manifest = make_sheet(
        private_root=private_root,
        people=people,
        texture_kind=args.texture_kind,
        uv_coords=uv_coords,
        valid_vertices=valid_vertices,
        image_size=args.image_size,
        padding=args.padding,
        uv_mode=args.uv_mode,
        depth_mode=args.depth_mode,
        mask_mode=args.mask_mode,
        flame_masks=flame_masks,
        material_fallback=args.material_fallback,
        fallback_dark_threshold=args.fallback_dark_threshold,
        fallback_confidence_threshold=args.fallback_confidence_threshold,
        eye_overlay=args.eye_overlay,
        yaw_degrees=yaw_degrees,
        texture_name_override=args.texture_name,
        output_path=output_path,
    )

    print(
        json.dumps(
            {
                "output_path": manifest["output_path"],
                "manifest": str(output_path.with_suffix(".json")),
                "rows": len(manifest["rendered"]),
                "yaw_degrees": manifest["yaw_degrees"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
