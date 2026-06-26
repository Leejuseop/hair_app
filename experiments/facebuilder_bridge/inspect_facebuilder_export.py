"""Inspect a private FaceBuilder OBJ + texture export.

This is a lightweight bridge tool for Hair App research. It does not call
KeenTools internals and does not write private assets into Git. It parses a
FaceBuilder OBJ, checks material/texture linkage, renders a CPU front/side
review sheet, and writes summary metrics for quick comparison between exports.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


@dataclass
class ObjData:
    vertices: np.ndarray
    texcoords: np.ndarray
    normals: np.ndarray
    faces: list[list[tuple[int, int | None, int | None]]]
    face_materials: list[str | None]
    mtllib: str | None


def _parse_index(value: str, count: int) -> int:
    index = int(value)
    if index < 0:
        return count + index
    return index - 1


def load_obj(path: Path) -> ObjData:
    vertices: list[list[float]] = []
    texcoords: list[list[float]] = []
    normals: list[list[float]] = []
    faces: list[list[tuple[int, int | None, int | None]]] = []
    face_materials: list[str | None] = []
    current_material: str | None = None
    mtllib: str | None = None

    with path.open("r", encoding="utf-8", errors="replace") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            tag = parts[0]
            if tag == "mtllib" and len(parts) > 1:
                mtllib = " ".join(parts[1:])
            elif tag == "usemtl" and len(parts) > 1:
                current_material = " ".join(parts[1:])
            elif tag == "v" and len(parts) >= 4:
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif tag == "vt" and len(parts) >= 3:
                texcoords.append([float(parts[1]), float(parts[2])])
            elif tag == "vn" and len(parts) >= 4:
                normals.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif tag == "f" and len(parts) >= 4:
                face: list[tuple[int, int | None, int | None]] = []
                for token in parts[1:]:
                    comps = token.split("/")
                    vertex_index = _parse_index(comps[0], len(vertices))
                    tex_index = (
                        _parse_index(comps[1], len(texcoords))
                        if len(comps) > 1 and comps[1]
                        else None
                    )
                    normal_index = (
                        _parse_index(comps[2], len(normals))
                        if len(comps) > 2 and comps[2]
                        else None
                    )
                    face.append((vertex_index, tex_index, normal_index))
                if len(face) == 3:
                    faces.append(face)
                    face_materials.append(current_material)
                else:
                    for index in range(1, len(face) - 1):
                        faces.append([face[0], face[index], face[index + 1]])
                        face_materials.append(current_material)

    return ObjData(
        vertices=np.asarray(vertices, dtype=np.float32),
        texcoords=np.asarray(texcoords, dtype=np.float32),
        normals=np.asarray(normals, dtype=np.float32),
        faces=faces,
        face_materials=face_materials,
        mtllib=mtllib,
    )


def parse_mtl_texture(mtl_path: Path | None) -> str | None:
    if mtl_path is None or not mtl_path.exists():
        return None
    with mtl_path.open("r", encoding="utf-8", errors="replace") as file:
        for raw_line in file:
            line = raw_line.strip()
            if line.startswith("map_Kd "):
                return line.split(maxsplit=1)[1]
    return None


def rotate_y(points: np.ndarray, degrees: float) -> np.ndarray:
    radians = math.radians(degrees)
    c = math.cos(radians)
    s = math.sin(radians)
    matrix = np.asarray([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]], dtype=np.float32)
    return points @ matrix.T


def render_obj(
    obj: ObjData,
    texture: np.ndarray,
    *,
    yaw_degrees: float,
    image_size: int,
    background: tuple[int, int, int] = (18, 18, 18),
) -> Image.Image:
    vertices = obj.vertices
    bbox_min = vertices.min(axis=0)
    bbox_max = vertices.max(axis=0)
    center = (bbox_min + bbox_max) * 0.5
    scale = float(np.max(bbox_max[:2] - bbox_min[:2]))
    if scale <= 0:
        scale = 1.0

    normalized = (vertices - center[None, :]) / scale
    rotated = rotate_y(normalized, yaw_degrees)
    width = height = image_size
    x = (rotated[:, 0] * 0.9 + 0.5) * (width - 1)
    y = (0.5 - rotated[:, 1] * 0.9) * (height - 1)
    z = rotated[:, 2]
    screen = np.stack([x, y, z], axis=1)

    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :] = np.asarray(background, dtype=np.uint8)
    depth = np.full((height, width), -np.inf, dtype=np.float32)
    tex_h, tex_w = texture.shape[:2]

    for face in obj.faces:
        vertex_indices = [item[0] for item in face]
        tex_indices = [item[1] for item in face]
        if any(index is None for index in tex_indices):
            continue
        if any(index < 0 or index >= len(vertices) for index in vertex_indices):
            continue
        if any(index is None or index < 0 or index >= len(obj.texcoords) for index in tex_indices):
            continue

        pts = screen[vertex_indices]
        uvs = obj.texcoords[[int(index) for index in tex_indices]]
        min_x = max(0, int(math.floor(float(pts[:, 0].min()))))
        max_x = min(width - 1, int(math.ceil(float(pts[:, 0].max()))))
        min_y = max(0, int(math.floor(float(pts[:, 1].min()))))
        max_y = min(height - 1, int(math.ceil(float(pts[:, 1].max()))))
        if min_x > max_x or min_y > max_y:
            continue

        x0, y0 = pts[0, 0], pts[0, 1]
        x1, y1 = pts[1, 0], pts[1, 1]
        x2, y2 = pts[2, 0], pts[2, 1]
        denominator = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(float(denominator)) < 1e-8:
            continue

        grid_y, grid_x = np.mgrid[min_y : max_y + 1, min_x : max_x + 1]
        w0 = ((y1 - y2) * (grid_x - x2) + (x2 - x1) * (grid_y - y2)) / denominator
        w1 = ((y2 - y0) * (grid_x - x2) + (x0 - x2) * (grid_y - y2)) / denominator
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
        if not np.any(inside):
            continue

        interpolated_depth = w0 * pts[0, 2] + w1 * pts[1, 2] + w2 * pts[2, 2]
        patch_depth = depth[min_y : max_y + 1, min_x : max_x + 1]
        update = inside & (interpolated_depth > patch_depth)
        if not np.any(update):
            continue

        u = w0 * uvs[0, 0] + w1 * uvs[1, 0] + w2 * uvs[2, 0]
        v = 1.0 - (w0 * uvs[0, 1] + w1 * uvs[1, 1] + w2 * uvs[2, 1])
        tex_x = np.clip(np.rint(u * (tex_w - 1)).astype(np.int32), 0, tex_w - 1)
        tex_y = np.clip(np.rint(v * (tex_h - 1)).astype(np.int32), 0, tex_h - 1)
        sampled = texture[tex_y, tex_x]
        colors = sampled[:, :, :3].copy()
        if sampled.shape[2] == 4:
            empty = sampled[:, :, 3] < 10
            colors[empty] = np.asarray([54, 54, 58], dtype=np.uint8)

        image_patch = image[min_y : max_y + 1, min_x : max_x + 1]
        image_patch[update] = colors[update]
        patch_depth[update] = interpolated_depth[update]

    return Image.fromarray(image)


def make_texture_preview(texture: Image.Image, output_path: Path, max_size: int = 900) -> None:
    preview = texture.convert("RGBA")
    preview.thumbnail((max_size, max_size))
    canvas = Image.new("RGBA", preview.size, (0, 0, 0, 255))
    canvas.alpha_composite(preview)
    canvas.convert("RGB").save(output_path)


def write_render_sheet(
    obj: ObjData,
    texture: Image.Image,
    output_dir: Path,
    yaw_degrees: list[int],
    image_size: int,
) -> Path:
    tex_np = np.asarray(texture.convert("RGBA"))
    tiles: list[Image.Image] = []
    for yaw in yaw_degrees:
        rendered = render_obj(obj, tex_np, yaw_degrees=yaw, image_size=image_size)
        rendered.save(output_dir / f"render_yaw_{yaw:+04d}.png")
        thumb = rendered.copy()
        thumb.thumbnail((image_size, image_size))
        tile = Image.new("RGB", (image_size, image_size + 30), (8, 8, 8))
        tile.paste(thumb, ((image_size - thumb.width) // 2, 0))
        draw = ImageDraw.Draw(tile)
        draw.text((8, image_size + 8), f"yaw {yaw}", fill=(245, 245, 245))
        tiles.append(tile)

    columns = min(5, len(tiles))
    rows = int(math.ceil(len(tiles) / columns))
    sheet = Image.new("RGB", (columns * image_size, rows * (image_size + 30)), (5, 5, 5))
    for index, tile in enumerate(tiles):
        sheet.paste(tile, ((index % columns) * image_size, (index // columns) * (image_size + 30)))

    output_path = output_dir / "render_contact_sheet.png"
    sheet.save(output_path)
    return output_path


def summarize(obj: ObjData, obj_path: Path, texture_path: Path, texture: Image.Image) -> dict[str, Any]:
    vertices = obj.vertices
    bbox_min = vertices.min(axis=0)
    bbox_max = vertices.max(axis=0)
    rgba = np.asarray(texture.convert("RGBA"))
    alpha = rgba[:, :, 3]
    nonempty = alpha > 10
    nonempty_count = int(np.count_nonzero(nonempty))
    near_black = (
        nonempty
        & (rgba[:, :, 0] < 8)
        & (rgba[:, :, 1] < 8)
        & (rgba[:, :, 2] < 8)
    )
    ys, xs = np.where(nonempty)
    alpha_bbox = None
    if xs.size:
        alpha_bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]

    mtl_path = obj_path.with_name(obj.mtllib) if obj.mtllib else None
    return {
        "obj": str(obj_path),
        "texture": str(texture_path),
        "mtllib": obj.mtllib,
        "mtl_texture": parse_mtl_texture(mtl_path),
        "vertices": int(len(obj.vertices)),
        "uv_vertices": int(len(obj.texcoords)),
        "normals": int(len(obj.normals)),
        "triangles": int(len(obj.faces)),
        "materials": sorted({item for item in obj.face_materials if item}),
        "bbox_min": bbox_min.round(6).tolist(),
        "bbox_max": bbox_max.round(6).tolist(),
        "dimensions_xyz": (bbox_max - bbox_min).round(6).tolist(),
        "texture_size": list(texture.size),
        "texture_alpha_nonempty_ratio": round(float(nonempty_count / alpha.size), 4),
        "texture_near_black_ratio_within_alpha": round(
            float(np.count_nonzero(near_black) / max(nonempty_count, 1)),
            4,
        ),
        "texture_alpha_bbox": alpha_bbox,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--obj", required=True, type=Path)
    parser.add_argument("--texture", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--yaw-degree",
        action="append",
        type=int,
        default=None,
        help="Yaw degrees for the review sheet. Can be provided multiple times.",
    )
    parser.add_argument("--image-size", type=int, default=360)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    yaws = args.yaw_degree or [-90, -60, -45, -30, 0, 30, 45, 60, 90, 180]

    obj = load_obj(args.obj)
    texture = Image.open(args.texture)
    summary = summarize(obj, args.obj, args.texture, texture)

    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    make_texture_preview(texture, args.output_dir / "texture_preview.png")
    sheet_path = write_render_sheet(obj, texture, args.output_dir, yaws, args.image_size)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"render_contact_sheet={sheet_path}")


if __name__ == "__main__":
    main()
