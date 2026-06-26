"""Render private FLAME mesh candidates with an observed UV atlas.

This is a diagnostic preview renderer, not the final product renderer. It uses
the Pixel3DMM/FLAME per-vertex UV coordinates and writes private renders beside
the private texture-baker output. It never writes meshes, textures, or renders
into the Git repository.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import pickle
import struct
from zipfile import ZipFile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from texture_baker_loader import MeshCandidate, default_private_root, load_person


DEFAULT_TEXTURE_RUNS = {
    "\uc8fc\uc12d": "observed_v2_camera_visibility_front45_preview",
    "\uc740\ucc44": "observed_v2_camera_visibility_front45_preview",
}
DEFAULT_UV_ASSET = "shared/models/pixel3dmm_assets/flame_uv_coords.npy"
DEFAULT_VALID_VERTS_ASSET = (
    "shared/models/pixel3dmm_assets/uv_valid_verty_noEyes_noEyeRegion_debug_wEars.npy"
)
DEFAULT_FLAME_MASKS_ASSET = "shared/models/FLAME_masks.zip"
UV_MODES = ("direct", "flip_y", "flip_x", "flip_xy")
DEPTH_MODES = ("max", "min")


@dataclass(frozen=True)
class PlyMesh:
    vertices: np.ndarray
    faces: np.ndarray


def read_ply(path: Path) -> PlyMesh:
    with path.open("rb") as file:
        vertex_count: int | None = None
        face_count: int | None = None
        ply_format: str | None = None
        while True:
            raw_line = file.readline()
            line = raw_line.decode("utf-8", errors="replace")
            if not line:
                raise ValueError(f"PLY header ended unexpectedly: {path}")
            line = line.strip()
            if line.startswith("format "):
                ply_format = line.split()[1]
            elif line.startswith("element vertex "):
                vertex_count = int(line.rsplit(" ", 1)[-1])
            elif line.startswith("element face "):
                face_count = int(line.rsplit(" ", 1)[-1])
            elif line == "end_header":
                break

        if vertex_count is None or face_count is None:
            raise ValueError(f"PLY is missing vertex or face count: {path}")

        if ply_format == "ascii":
            body = file.read().decode("utf-8", errors="replace").splitlines()
            vertices = np.zeros((vertex_count, 3), dtype=np.float32)
            for index, line in enumerate(body[:vertex_count]):
                values = line.strip().split()
                vertices[index] = [float(values[0]), float(values[1]), float(values[2])]

            faces: list[list[int]] = []
            for line in body[vertex_count : vertex_count + face_count]:
                values = line.strip().split()
                count = int(values[0])
                if count != 3:
                    continue
                faces.append([int(values[1]), int(values[2]), int(values[3])])
            return PlyMesh(vertices=vertices, faces=np.asarray(faces, dtype=np.int32))

        if ply_format == "binary_little_endian":
            vertices = np.fromfile(file, dtype="<f4", count=vertex_count * 3).reshape(vertex_count, 3)
            faces: list[list[int]] = []
            for _ in range(face_count):
                raw_count = file.read(1)
                if not raw_count:
                    break
                count = struct.unpack("<B", raw_count)[0]
                raw_indices = file.read(4 * count)
                indices = struct.unpack("<" + ("i" * count), raw_indices)
                if count == 3:
                    faces.append([int(indices[0]), int(indices[1]), int(indices[2])])
            return PlyMesh(vertices=vertices.astype(np.float32), faces=np.asarray(faces, dtype=np.int32))

    raise ValueError(f"Unsupported PLY format {ply_format!r}: {path}")


def resolve_uv_coords(private_root: Path, explicit_path: Path | None) -> Path:
    candidates = []
    if explicit_path is not None:
        candidates.append(explicit_path)
    candidates.append(private_root / DEFAULT_UV_ASSET)

    temp_root = Path(os.environ.get("TEMP", "")) / "pixel3dmm-src" / "assets" / "flame_uv_coords.npy"
    candidates.append(temp_root)

    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        "Could not find flame_uv_coords.npy. Pass --uv-coords or copy the "
        "Pixel3DMM asset into private_root/shared/models/pixel3dmm_assets/."
    )


def resolve_valid_vertices(private_root: Path, explicit_path: Path | None) -> Path | None:
    candidates = []
    if explicit_path is not None:
        candidates.append(explicit_path)
    candidates.append(private_root / DEFAULT_VALID_VERTS_ASSET)

    for path in candidates:
        if path.exists():
            return path
    return None


def resolve_flame_masks(private_root: Path, explicit_path: Path | None) -> Path | None:
    candidates = []
    if explicit_path is not None:
        candidates.append(explicit_path)
    candidates.append(private_root / DEFAULT_FLAME_MASKS_ASSET)

    for path in candidates:
        if path.exists():
            return path
    return None


def load_flame_masks(path: Path | None) -> dict[str, np.ndarray]:
    if path is None:
        return {}

    if path.suffix.lower() == ".zip":
        with ZipFile(path) as archive:
            data = archive.read("FLAME_masks.pkl")
        masks = pickle.load(io.BytesIO(data), encoding="latin1")
    else:
        with path.open("rb") as file:
            masks = pickle.load(file, encoding="latin1")

    return {str(key): np.asarray(value, dtype=np.int64) for key, value in masks.items()}


def estimate_skin_color(texture: np.ndarray) -> np.ndarray:
    nonblack = texture[np.sum(texture, axis=2) > 30]
    if nonblack.size == 0:
        return np.asarray([168, 132, 118], dtype=np.float32)
    color = np.median(nonblack.astype(np.float32), axis=0)
    return np.clip(color, 45, 235).astype(np.float32)


def blend_color(a: np.ndarray, b: tuple[int, int, int], alpha: float) -> np.ndarray:
    return np.clip((a * (1.0 - alpha)) + (np.asarray(b, dtype=np.float32) * alpha), 0, 255)


def build_material_vertex_colors(
    vertex_count: int,
    masks: dict[str, np.ndarray],
    skin_color: np.ndarray,
) -> np.ndarray:
    colors = np.tile(skin_color[None, :], (vertex_count, 1)).astype(np.float32)

    def paint(mask_name: str, color: np.ndarray | tuple[int, int, int]) -> None:
        indices = masks.get(mask_name)
        if indices is None:
            return
        valid = indices[(indices >= 0) & (indices < vertex_count)]
        colors[valid] = np.asarray(color, dtype=np.float32)

    scalp_color = blend_color(skin_color, (72, 56, 46), 0.78)
    neck_color = blend_color(skin_color, (150, 118, 104), 0.18)
    ear_color = blend_color(skin_color, (196, 118, 104), 0.24)
    lip_color = blend_color(skin_color, (154, 68, 78), 0.55)
    eyeball_color = np.asarray([226, 220, 208], dtype=np.float32)

    paint("scalp", scalp_color)
    paint("neck", neck_color)
    paint("left_ear", ear_color)
    paint("right_ear", ear_color)
    paint("lips", lip_color)
    paint("left_eyeball", eyeball_color)
    paint("right_eyeball", eyeball_color)
    return np.clip(colors, 0, 255).astype(np.uint8)


def draw_disk(
    image: np.ndarray,
    center: tuple[float, float],
    radius: float,
    color: tuple[int, int, int],
) -> None:
    height, width = image.shape[:2]
    cx, cy = center
    min_x = max(int(np.floor(cx - radius)), 0)
    max_x = min(int(np.ceil(cx + radius)), width - 1)
    min_y = max(int(np.floor(cy - radius)), 0)
    max_y = min(int(np.ceil(cy + radius)), height - 1)
    if max_x < min_x or max_y < min_y:
        return

    yy, xx = np.mgrid[min_y : max_y + 1, min_x : max_x + 1]
    mask = ((xx - cx) ** 2) + ((yy - cy) ** 2) <= radius * radius
    patch = image[min_y : max_y + 1, min_x : max_x + 1]
    patch[mask] = np.asarray(color, dtype=np.uint8)


def draw_ellipse(
    image: np.ndarray,
    center: tuple[float, float],
    radius_x: float,
    radius_y: float,
    color: tuple[int, int, int],
    *,
    alpha: float = 1.0,
) -> None:
    height, width = image.shape[:2]
    cx, cy = center
    min_x = max(int(np.floor(cx - radius_x)), 0)
    max_x = min(int(np.ceil(cx + radius_x)), width - 1)
    min_y = max(int(np.floor(cy - radius_y)), 0)
    max_y = min(int(np.ceil(cy + radius_y)), height - 1)
    if max_x < min_x or max_y < min_y:
        return

    yy, xx = np.mgrid[min_y : max_y + 1, min_x : max_x + 1]
    mask = (((xx - cx) / max(radius_x, 1e-6)) ** 2) + (((yy - cy) / max(radius_y, 1e-6)) ** 2) <= 1.0
    patch = image[min_y : max_y + 1, min_x : max_x + 1]
    color_array = np.asarray(color, dtype=np.float32)
    if alpha >= 1.0:
        patch[mask] = color_array.astype(np.uint8)
    else:
        patch_values = patch[mask].astype(np.float32)
        patch[mask] = np.clip((patch_values * (1.0 - alpha)) + (color_array * alpha), 0, 255).astype(np.uint8)


def draw_eye_overlays(
    image: np.ndarray,
    zbuffer: np.ndarray,
    points: np.ndarray,
    depth: np.ndarray,
    masks: dict[str, np.ndarray],
    depth_mode: str,
) -> None:
    if not masks:
        return

    height, width = zbuffer.shape
    for mask_name in ("left_eyeball", "right_eyeball"):
        indices = masks.get(mask_name)
        if indices is None:
            continue
        valid_indices = indices[(indices >= 0) & (indices < points.shape[0])]
        if valid_indices.size == 0:
            continue

        eye_points = points[valid_indices]
        eye_depth = depth[valid_indices]
        x = np.rint(eye_points[:, 0]).astype(np.int32)
        y = np.rint(eye_points[:, 1]).astype(np.int32)
        in_bounds = (x >= 0) & (x < width) & (y >= 0) & (y < height)
        if not np.any(in_bounds):
            continue

        x = x[in_bounds]
        y = y[in_bounds]
        eye_points = eye_points[in_bounds]
        eye_depth = eye_depth[in_bounds]
        surface_depth = zbuffer[y, x]
        finite = np.isfinite(surface_depth)
        if depth_mode == "max":
            visible = finite & (eye_depth >= surface_depth - 0.003)
        else:
            visible = finite & (eye_depth <= surface_depth + 0.003)
        if int(visible.sum()) < 12:
            continue

        visible_points = eye_points[visible]
        center = np.median(visible_points, axis=0)
        span = np.ptp(visible_points, axis=0)
        radius_x = float(np.clip(span[0] * 0.26, 3.0, 10.0))
        radius_y = float(np.clip(span[1] * 0.18, 1.6, 5.2))
        center_xy = (float(center[0]), float(center[1]))
        draw_ellipse(image, center_xy, radius_x * 0.92, radius_y * 0.95, (198, 190, 178), alpha=0.42)
        draw_ellipse(
            image,
            (center_xy[0], center_xy[1] - radius_y * 0.42),
            radius_x * 0.9,
            radius_y * 0.42,
            (116, 86, 76),
            alpha=0.34,
        )
        iris_radius = float(np.clip(max(radius_y * 1.45, radius_x * 0.58), 3.2, 7.0))
        pupil_radius = max(iris_radius * 0.52, 1.25)
        draw_disk(image, center_xy, iris_radius, (67, 47, 36))
        draw_disk(image, center_xy, pupil_radius, (9, 7, 6))
        draw_disk(
            image,
            (center_xy[0] - iris_radius * 0.30, center_xy[1] - iris_radius * 0.30),
            max(iris_radius * 0.15, 0.65),
            (235, 230, 218),
        )


def texture_path_for_run(texture_dir: Path, texture_kind: str) -> Path:
    preferred = {
        "preview_filled": "base_color_preview_filled.png",
        "visual_completed": "base_color_visual_completed.png",
        "cleanup_completed": "base_color_cleanup_completed.png",
        "selfie_optimized": "base_color_selfie_optimized_preview.png",
        "observed": "base_color_observed.png",
    }[texture_kind]
    preferred_path = texture_dir / preferred
    if preferred_path.exists():
        return preferred_path

    fallback = texture_dir / "base_color_observed.png"
    if fallback.exists():
        return fallback
    raise FileNotFoundError(f"No texture image found under: {texture_dir}")


def apply_uv_mode(uv: np.ndarray, mode: str) -> np.ndarray:
    transformed = uv.astype(np.float32, copy=True)
    if "flip_x" in mode or mode == "flip_xy":
        transformed[:, 0] = 1.0 - transformed[:, 0]
    if "flip_y" in mode or mode == "flip_xy":
        transformed[:, 1] = 1.0 - transformed[:, 1]
    return np.clip(transformed, 0.0, 1.0)


def rotate_vertices(vertices: np.ndarray, view: str) -> np.ndarray:
    angles = {
        "front": 0.0,
        "left_35": np.deg2rad(35.0),
        "right_35": np.deg2rad(-35.0),
    }
    if view.startswith("yaw_"):
        angle = np.deg2rad(float(view.removeprefix("yaw_")))
    else:
        angle = angles[view]
    cos_a = float(np.cos(angle))
    sin_a = float(np.sin(angle))
    rotation = np.asarray(
        [
            [cos_a, 0.0, sin_a],
            [0.0, 1.0, 0.0],
            [-sin_a, 0.0, cos_a],
        ],
        dtype=np.float32,
    )
    return vertices @ rotation.T


def project_orthographic(vertices: np.ndarray, image_size: int, padding: int) -> tuple[np.ndarray, np.ndarray]:
    xy = vertices[:, :2].copy()
    min_xy = xy.min(axis=0)
    max_xy = xy.max(axis=0)
    center = (min_xy + max_xy) * 0.5
    extent = max(max_xy - min_xy)
    scale = (image_size - (padding * 2)) / max(float(extent), 1e-6)

    screen = np.zeros((vertices.shape[0], 2), dtype=np.float32)
    screen[:, 0] = (xy[:, 0] - center[0]) * scale + (image_size * 0.5)
    screen[:, 1] = (center[1] - xy[:, 1]) * scale + (image_size * 0.5)
    return screen, vertices[:, 2]


def sample_texture(texture: np.ndarray, uv_values: np.ndarray) -> np.ndarray:
    height, width = texture.shape[:2]
    x = np.clip(np.rint(uv_values[:, 0] * (width - 1)).astype(np.int32), 0, width - 1)
    y = np.clip(np.rint(uv_values[:, 1] * (height - 1)).astype(np.int32), 0, height - 1)
    return texture[y, x]


def rasterize_triangle(
    *,
    image: np.ndarray,
    zbuffer: np.ndarray,
    texture: np.ndarray,
    points: np.ndarray,
    depth: np.ndarray,
    uv: np.ndarray,
    depth_mode: str,
    fallback_color: np.ndarray | None = None,
    fallback_dark_threshold: int = 30,
    confidence: np.ndarray | None = None,
    fallback_confidence_threshold: int = 0,
) -> None:
    height, width = zbuffer.shape
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
    if not np.any(inside):
        return

    interpolated_depth = (w0 * depth[0]) + (w1 * depth[1]) + (w2 * depth[2])
    current = zbuffer[min_y : max_y + 1, min_x : max_x + 1]
    if depth_mode == "max":
        update = inside & (interpolated_depth > current)
    else:
        update = inside & (interpolated_depth < current)
    if not np.any(update):
        return

    uv_grid = (
        (w0[..., None] * uv[0])
        + (w1[..., None] * uv[1])
        + (w2[..., None] * uv[2])
    )
    colors = sample_texture(texture, uv_grid.reshape(-1, 2)).reshape(uv_grid.shape[0], uv_grid.shape[1], 3)
    if fallback_color is not None:
        dark = np.sum(colors, axis=2) < fallback_dark_threshold
        fallback_mask = dark
        if confidence is not None and fallback_confidence_threshold > 0:
            sampled_confidence = sample_texture(confidence, uv_grid.reshape(-1, 2)).reshape(uv_grid.shape[:2])
            fallback_mask |= sampled_confidence <= fallback_confidence_threshold
        if np.any(fallback_mask):
            colors[fallback_mask] = fallback_color
    patch = image[min_y : max_y + 1, min_x : max_x + 1]
    patch[update] = colors[update]
    current[update] = interpolated_depth[update]


def render_mesh(
    *,
    mesh: PlyMesh,
    uv_coords: np.ndarray,
    texture: np.ndarray,
    image_size: int,
    padding: int,
    uv_mode: str,
    depth_mode: str,
    view: str,
    valid_vertices: np.ndarray | None,
    mask_mode: str,
    material_vertex_colors: np.ndarray | None = None,
    fallback_dark_threshold: int = 30,
    confidence: np.ndarray | None = None,
    fallback_confidence_threshold: int = 0,
    flame_masks: dict[str, np.ndarray] | None = None,
    eye_overlay: bool = False,
) -> np.ndarray:
    vertices = rotate_vertices(mesh.vertices, view)
    points, depth = project_orthographic(vertices, image_size, padding)
    uv = apply_uv_mode(uv_coords, uv_mode)

    image = np.full((image_size, image_size, 3), 18, dtype=np.uint8)
    z_init = -np.inf if depth_mode == "max" else np.inf
    zbuffer = np.full((image_size, image_size), z_init, dtype=np.float32)

    faces = mesh.faces
    if valid_vertices is not None and mask_mode != "none":
        valid_mask = np.zeros((mesh.vertices.shape[0],), dtype=bool)
        valid_mask[valid_vertices] = True
        face_valid = valid_mask[faces]
        if mask_mode == "all-valid":
            faces = faces[np.all(face_valid, axis=1)]
        elif mask_mode == "any-valid":
            faces = faces[np.any(face_valid, axis=1)]

    for face in faces:
        fallback_color = None
        if material_vertex_colors is not None:
            fallback_color = np.rint(material_vertex_colors[face].mean(axis=0)).astype(np.uint8)
        rasterize_triangle(
            image=image,
            zbuffer=zbuffer,
            texture=texture,
            points=points[face],
            depth=depth[face],
            uv=uv[face],
            depth_mode=depth_mode,
            fallback_color=fallback_color,
            fallback_dark_threshold=fallback_dark_threshold,
            confidence=confidence,
            fallback_confidence_threshold=fallback_confidence_threshold,
        )

    if eye_overlay:
        draw_eye_overlays(image, zbuffer, points, depth, flame_masks or {}, depth_mode)

    return image


def write_obj_preview(
    *,
    output_path: Path,
    mesh: PlyMesh,
    uv_coords: np.ndarray,
    uv_mode: str,
    texture_path: Path,
) -> None:
    material_path = output_path.with_suffix(".mtl")
    texture_relative = os.path.relpath(texture_path, material_path.parent).replace("\\", "/")

    material_path.write_text(
        "\n".join(
            [
                "newmtl observed_face",
                "Ka 1.000 1.000 1.000",
                "Kd 1.000 1.000 1.000",
                "Ks 0.000 0.000 0.000",
                f"map_Kd {texture_relative}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    uv = apply_uv_mode(uv_coords, uv_mode)
    with output_path.open("w", encoding="utf-8", newline="\n") as file:
        file.write(f"mtllib {material_path.name}\n")
        file.write("usemtl observed_face\n")
        for vertex in mesh.vertices:
            file.write(f"v {vertex[0]:.8f} {vertex[1]:.8f} {vertex[2]:.8f}\n")
        for coord in uv:
            file.write(f"vt {coord[0]:.8f} {1.0 - coord[1]:.8f}\n")
        for face in mesh.faces:
            a, b, c = face + 1
            file.write(f"f {a}/{a} {b}/{b} {c}/{c}\n")


def make_contact_sheet(image_paths: list[Path], output_path: Path, thumb_size: int = 256) -> None:
    if not image_paths:
        return
    columns = min(4, len(image_paths))
    rows = int(np.ceil(len(image_paths) / columns))
    label_height = 26
    sheet = Image.new("RGB", (columns * thumb_size, rows * (thumb_size + label_height)), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(image_paths):
        row = index // columns
        col = index % columns
        image = Image.open(path).convert("RGB").resize((thumb_size, thumb_size))
        x = col * thumb_size
        y = row * (thumb_size + label_height)
        sheet.paste(image, (x, y + label_height))
        draw.rectangle((x, y, x + thumb_size, y + label_height), fill=(20, 20, 20))
        draw.text((x + 4, y + 6), path.stem[:38], fill=(255, 255, 255))
    sheet.save(output_path)


def render_candidate(
    *,
    person: str,
    mesh: MeshCandidate,
    private_root: Path,
    texture_name: str,
    texture_kind: str,
    uv_coords: np.ndarray,
    valid_vertices: np.ndarray | None,
    flame_masks: dict[str, np.ndarray],
    image_size: int,
    padding: int,
    uv_modes: list[str],
    depth_modes: list[str],
    views: list[str],
    mask_mode: str,
    material_fallback: bool,
    fallback_dark_threshold: int,
    fallback_confidence_threshold: int,
    eye_overlay: bool,
    write_obj: bool,
) -> dict[str, Any]:
    texture_dir = private_root / "output" / person / "texture_baker" / texture_name
    output_dir = texture_dir / "mesh_texture_preview" / mesh.key
    output_dir.mkdir(parents=True, exist_ok=True)

    mesh_data = read_ply(Path(mesh.path))
    if mesh_data.vertices.shape[0] != uv_coords.shape[0]:
        raise ValueError(
            f"UV coordinate count does not match mesh vertices for {person}:{mesh.key}: "
            f"mesh={mesh_data.vertices.shape[0]}, uv={uv_coords.shape[0]}"
        )

    texture_path = texture_path_for_run(texture_dir, texture_kind)
    texture = np.asarray(Image.open(texture_path).convert("RGB"), dtype=np.uint8)
    confidence_path = texture_dir / "confidence.png"
    confidence = None
    if fallback_confidence_threshold > 0 and confidence_path.exists():
        confidence = np.asarray(Image.open(confidence_path).convert("L"), dtype=np.uint8)
    material_vertex_colors = None
    if material_fallback:
        skin_color = estimate_skin_color(texture)
        material_vertex_colors = build_material_vertex_colors(
            mesh_data.vertices.shape[0],
            flame_masks,
            skin_color,
        )

    image_paths: list[Path] = []
    for view in views:
        for uv_mode in uv_modes:
            for depth_mode in depth_modes:
                image = render_mesh(
                    mesh=mesh_data,
                    uv_coords=uv_coords,
                    texture=texture,
                    image_size=image_size,
                    padding=padding,
                    uv_mode=uv_mode,
                    depth_mode=depth_mode,
                    view=view,
                    valid_vertices=valid_vertices,
                    mask_mode=mask_mode,
                    material_vertex_colors=material_vertex_colors,
                    fallback_dark_threshold=fallback_dark_threshold,
                    confidence=confidence,
                    fallback_confidence_threshold=fallback_confidence_threshold,
                    flame_masks=flame_masks,
                    eye_overlay=eye_overlay,
                )
                output_path = output_dir / f"{view}_{uv_mode}_depth_{depth_mode}.png"
                Image.fromarray(image, mode="RGB").save(output_path)
                image_paths.append(output_path)

    if write_obj:
        write_obj_preview(
            output_path=output_dir / f"{mesh.key}_uv_direct.obj",
            mesh=mesh_data,
            uv_coords=uv_coords,
            uv_mode="direct",
            texture_path=texture_path,
        )

    contact_sheet = output_dir / "contact_sheet.png"
    make_contact_sheet(image_paths, contact_sheet)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "person": person,
        "mesh": asdict(mesh),
        "texture_name": texture_name,
        "texture_kind": texture_kind,
        "texture_path": str(texture_path),
        "output_dir": str(output_dir),
        "image_size": image_size,
        "padding": padding,
        "uv_modes": uv_modes,
        "depth_modes": depth_modes,
        "views": views,
        "mask_mode": mask_mode,
        "material_fallback": material_fallback,
        "fallback_dark_threshold": fallback_dark_threshold,
        "fallback_confidence_threshold": fallback_confidence_threshold,
        "confidence_path": str(confidence_path) if confidence is not None else None,
        "eye_overlay": eye_overlay,
        "valid_vertices_count": int(valid_vertices.shape[0]) if valid_vertices is not None else None,
        "outputs": [str(path) for path in image_paths],
        "contact_sheet": str(contact_sheet),
        "limitations": [
            "Diagnostic CPU orthographic preview only; not a final renderer.",
            "Uses Pixel3DMM per-vertex FLAME UV coordinates and tests UV/depth orientation variants.",
            "Does not use fitted tracking cameras, lighting, normals, or perspective intrinsics yet.",
        ],
    }
    (output_dir / "mesh_texture_preview_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview observed UV textures on FLAME mesh candidates.")
    parser.add_argument("--private-root", type=Path, default=None)
    parser.add_argument("--person", action="append", default=None)
    parser.add_argument("--mesh-key", action="append", default=None)
    parser.add_argument("--texture-name", default=None)
    parser.add_argument(
        "--texture-kind",
        choices=["preview_filled", "visual_completed", "cleanup_completed", "selfie_optimized", "observed"],
        default="preview_filled",
    )
    parser.add_argument("--uv-coords", type=Path, default=None)
    parser.add_argument("--valid-vertices", type=Path, default=None)
    parser.add_argument("--flame-masks", type=Path, default=None)
    parser.add_argument("--mask-mode", choices=["none", "any-valid", "all-valid"], default="none")
    parser.add_argument("--material-fallback", action="store_true")
    parser.add_argument("--fallback-dark-threshold", type=int, default=30)
    parser.add_argument("--fallback-confidence-threshold", type=int, default=0)
    parser.add_argument("--eye-overlay", action="store_true")
    parser.add_argument("--image-size", type=int, default=768)
    parser.add_argument("--padding", type=int, default=60)
    parser.add_argument("--uv-mode", action="append", choices=UV_MODES, default=None)
    parser.add_argument("--depth-mode", action="append", choices=DEPTH_MODES, default=None)
    parser.add_argument(
        "--view",
        action="append",
        default=None,
        help='View name. Supports front, left_35, right_35, or yaw degrees such as "yaw_045".',
    )
    parser.add_argument("--write-obj", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    private_root = args.private_root or default_private_root()
    people = args.person or list(DEFAULT_TEXTURE_RUNS)
    uv_path = resolve_uv_coords(private_root, args.uv_coords)
    valid_path = resolve_valid_vertices(private_root, args.valid_vertices)
    flame_masks_path = resolve_flame_masks(private_root, args.flame_masks)
    uv_coords = np.load(uv_path)
    valid_vertices = np.load(valid_path) if valid_path is not None else None
    flame_masks = load_flame_masks(flame_masks_path)

    uv_modes = args.uv_mode or ["direct", "flip_y"]
    depth_modes = args.depth_mode or ["max", "min"]
    views = args.view or ["front"]

    reports = []
    for person in people:
        texture_name = args.texture_name or DEFAULT_TEXTURE_RUNS.get(person)
        if texture_name is None:
            raise ValueError(f"No default texture run for person {person}. Pass --texture-name.")

        bundle = load_person(person, private_root=private_root)
        meshes = [mesh for mesh in bundle.meshes if mesh.exists]
        if args.mesh_key is not None:
            wanted = set(args.mesh_key)
            meshes = [mesh for mesh in meshes if mesh.key in wanted]
        if not meshes:
            raise ValueError(f"No matching meshes found for {person}")

        for mesh in meshes:
            reports.append(
                render_candidate(
                    person=person,
                    mesh=mesh,
                    private_root=private_root,
                    texture_name=texture_name,
                    texture_kind=args.texture_kind,
                    uv_coords=uv_coords,
                    valid_vertices=valid_vertices,
                    flame_masks=flame_masks,
                    image_size=args.image_size,
                    padding=args.padding,
                    uv_modes=uv_modes,
                    depth_modes=depth_modes,
                    views=views,
                    mask_mode=args.mask_mode,
                    material_fallback=args.material_fallback,
                    fallback_dark_threshold=args.fallback_dark_threshold,
                    fallback_confidence_threshold=args.fallback_confidence_threshold,
                    eye_overlay=args.eye_overlay,
                    write_obj=args.write_obj,
                )
            )

    print(
        json.dumps(
            {
                "private_root": str(private_root),
                "uv_coords": str(uv_path),
                "valid_vertices": str(valid_path) if valid_path is not None else None,
                "flame_masks": str(flame_masks_path) if flame_masks_path is not None else None,
                "renders": [
                    {
                        "person": report["person"],
                        "mesh_key": report["mesh"]["key"],
                        "output_dir": report["output_dir"],
                        "contact_sheet": report["contact_sheet"],
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
