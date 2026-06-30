"""Build UV texel -> input-image sample coordinate maps for Step 4.

This Blender-side script does not read private RGB/mask pixels. It only uses
FaceBuilder's solved cameras and mesh to answer:

    "For this UV texel, which pixel coordinate in camera N would sample it?"

The host runner then applies parser/object masks and chooses clean RGB pixels.
Keeping pixel trust logic outside Blender makes the review/debug loop easier.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from pathlib import Path
from typing import Any

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view


def _parse_args(argv: list[str]) -> argparse.Namespace:
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-npz", type=Path, required=True)
    parser.add_argument("--headnum", type=int, default=0)
    parser.add_argument("--atlas-size", type=int, default=1024)
    parser.add_argument("--texture-only", action="store_true")
    parser.add_argument("--camera", action="append", type=int, default=None)
    return parser.parse_args(argv)


def _safe_path(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).replace("\\", "/")


def _image_path(image: Any) -> str | None:
    if image is None or not image.filepath:
        return None
    return _safe_path(bpy.path.abspath(image.filepath))


def _edge(a: np.ndarray, b: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return (x - a[0]) * (b[1] - a[1]) - (y - a[1]) * (b[0] - a[0])


def _triangle_area_2d(points: np.ndarray) -> float:
    return float(abs(
        (points[1, 0] - points[0, 0]) * (points[2, 1] - points[0, 1])
        - (points[2, 0] - points[0, 0]) * (points[1, 1] - points[0, 1])
    ) * 0.5)


def _project_vertex(scene: Any, camobj: Any, world: Any, width: int, height: int) -> tuple[float, float, float]:
    co = world_to_camera_view(scene, camobj, world)
    camera_local = camobj.matrix_world.inverted() @ world
    z_distance = -float(camera_local.z)
    return float(co.x) * width, (1.0 - float(co.y)) * height, z_distance


def _rasterize_zbuffer(
    triangles_screen: list[np.ndarray],
    image_width: int,
    image_height: int,
) -> tuple[np.ndarray, np.ndarray]:
    zbuf = np.full((image_height, image_width), np.inf, dtype=np.float32)
    idbuf = np.full((image_height, image_width), -1, dtype=np.int32)

    for tri_index, tri in enumerate(triangles_screen):
        xy = tri[:, :2]
        z = tri[:, 2]
        if np.any(~np.isfinite(tri)) or np.any(z <= 0):
            continue
        if _triangle_area_2d(xy) < 0.35:
            continue

        min_x = max(0, int(math.floor(float(np.min(xy[:, 0])))))
        max_x = min(image_width - 1, int(math.ceil(float(np.max(xy[:, 0])))))
        min_y = max(0, int(math.floor(float(np.min(xy[:, 1])))))
        max_y = min(image_height - 1, int(math.ceil(float(np.max(xy[:, 1])))))
        if min_x > max_x or min_y > max_y:
            continue

        xs = np.arange(min_x, max_x + 1, dtype=np.float32) + 0.5
        ys = np.arange(min_y, max_y + 1, dtype=np.float32) + 0.5
        grid_x, grid_y = np.meshgrid(xs, ys)
        area = _edge(xy[0], xy[1], xy[2, 0], xy[2, 1])
        if abs(float(area)) < 1e-6:
            continue

        w0 = _edge(xy[1], xy[2], grid_x, grid_y) / area
        w1 = _edge(xy[2], xy[0], grid_x, grid_y) / area
        w2 = _edge(xy[0], xy[1], grid_x, grid_y) / area
        inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
        if not np.any(inside):
            continue

        depth = w0 * z[0] + w1 * z[1] + w2 * z[2]
        region = zbuf[min_y:max_y + 1, min_x:max_x + 1]
        update = inside & (depth < region)
        if not np.any(update):
            continue
        region[update] = depth[update]
        id_region = idbuf[min_y:max_y + 1, min_x:max_x + 1]
        id_region[update] = tri_index

    return zbuf, idbuf


def _rasterize_uv_samples(
    uv_points: np.ndarray,
    screen_points: np.ndarray,
    confidence: float,
    sample_x: np.ndarray,
    sample_y: np.ndarray,
    confidence_map: np.ndarray,
    coverage_map: np.ndarray,
) -> int:
    size = confidence_map.shape[0]
    xy = uv_points
    if np.any(~np.isfinite(xy)) or _triangle_area_2d(xy) < 0.05:
        return 0

    min_x = max(0, int(math.floor(float(np.min(xy[:, 0])))))
    max_x = min(size - 1, int(math.ceil(float(np.max(xy[:, 0])))))
    min_y = max(0, int(math.floor(float(np.min(xy[:, 1])))))
    max_y = min(size - 1, int(math.ceil(float(np.max(xy[:, 1])))))
    if min_x > max_x or min_y > max_y:
        return 0

    xs = np.arange(min_x, max_x + 1, dtype=np.float32) + 0.5
    ys = np.arange(min_y, max_y + 1, dtype=np.float32) + 0.5
    grid_x, grid_y = np.meshgrid(xs, ys)
    area = _edge(xy[0], xy[1], xy[2, 0], xy[2, 1])
    if abs(float(area)) < 1e-6:
        return 0

    w0 = _edge(xy[1], xy[2], grid_x, grid_y) / area
    w1 = _edge(xy[2], xy[0], grid_x, grid_y) / area
    w2 = _edge(xy[0], xy[1], grid_x, grid_y) / area
    inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
    if not np.any(inside):
        return 0

    conf_byte = np.uint8(max(0, min(255, int(round(confidence * 255.0)))))
    region_conf = confidence_map[min_y:max_y + 1, min_x:max_x + 1]
    update = inside & (conf_byte > region_conf)
    if not np.any(update):
        coverage_map[min_y:max_y + 1, min_x:max_x + 1][inside] = 1
        return 0

    sx = w0 * screen_points[0, 0] + w1 * screen_points[1, 0] + w2 * screen_points[2, 0]
    sy = w0 * screen_points[0, 1] + w1 * screen_points[1, 1] + w2 * screen_points[2, 1]

    region_x = sample_x[min_y:max_y + 1, min_x:max_x + 1]
    region_y = sample_y[min_y:max_y + 1, min_x:max_x + 1]
    region_cov = coverage_map[min_y:max_y + 1, min_x:max_x + 1]
    region_x[update] = sx[update]
    region_y[update] = sy[update]
    region_conf[update] = conf_byte
    region_cov[inside] = 1
    return int(update.sum())


def _process_camera(head: Any, cam_index: int, atlas_size: int) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    scene = bpy.context.scene
    cam_item = head.cameras[cam_index]
    camobj = cam_item.camobj
    image = cam_item.cam_image
    headobj = head.headobj
    arrays: dict[str, np.ndarray] = {}

    if camobj is None or image is None or headobj is None:
        return {"camera_index": cam_index, "ok": False, "reason": "missing_camera_image_or_head"}, arrays

    keyframe = cam_item.get_keyframe()
    scene.frame_set(keyframe)
    scene.camera = camobj
    source_width, source_height = [int(v) for v in image.size]
    scene.render.resolution_x = source_width
    scene.render.resolution_y = source_height
    scene.render.pixel_aspect_x = 1.0
    scene.render.pixel_aspect_y = 1.0

    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = headobj.evaluated_get(depsgraph)
    mesh = obj_eval.to_mesh()
    matrix_world = obj_eval.matrix_world.copy()
    normal_matrix = matrix_world.to_3x3()
    camera_location = camobj.matrix_world.translation.copy()

    try:
        uv_layer = mesh.uv_layers.active
        if uv_layer is None:
            return {"camera_index": cam_index, "ok": False, "reason": "missing_uv_layer"}, arrays

        world_vertices = [matrix_world @ vertex.co for vertex in mesh.vertices]
        projected_vertices = [
            _project_vertex(scene, camobj, world, source_width, source_height)
            for world in world_vertices
        ]

        triangles_screen: list[np.ndarray] = []
        triangles_uv: list[np.ndarray] = []
        triangle_confidence: list[float] = []
        skipped_backface = 0
        skipped_degenerate = 0

        for poly in mesh.polygons:
            vertices = list(poly.vertices)
            loops = list(poly.loop_indices)
            if len(vertices) < 3:
                continue

            center = sum((world_vertices[index] for index in vertices), world_vertices[vertices[0]] * 0.0) / len(vertices)
            normal_world = normal_matrix @ poly.normal
            try:
                normal_world.normalize()
            except Exception:
                pass
            to_camera = camera_location - center
            try:
                to_camera.normalize()
            except Exception:
                pass
            view_conf = float(max(0.0, min(1.0, normal_world.dot(to_camera))))
            if view_conf <= 0.0:
                skipped_backface += 1
                continue

            for item_index in range(1, len(vertices) - 1):
                tri_vertex_indices = [vertices[0], vertices[item_index], vertices[item_index + 1]]
                tri_loop_indices = [loops[0], loops[item_index], loops[item_index + 1]]
                tri_screen = np.asarray([projected_vertices[index] for index in tri_vertex_indices], dtype=np.float32)
                tri_uv_raw = []
                for loop_index in tri_loop_indices:
                    uv = uv_layer.data[loop_index].uv
                    tri_uv_raw.append([
                        float(uv.x) * (atlas_size - 1),
                        (1.0 - float(uv.y)) * (atlas_size - 1),
                    ])
                tri_uv = np.asarray(tri_uv_raw, dtype=np.float32)
                if _triangle_area_2d(tri_screen[:, :2]) < 0.35 or _triangle_area_2d(tri_uv) < 0.05:
                    skipped_degenerate += 1
                    continue
                triangles_screen.append(tri_screen)
                triangles_uv.append(tri_uv)
                triangle_confidence.append(float(view_conf ** 1.35))

        _, idbuf = _rasterize_zbuffer(triangles_screen, source_width, source_height)
        visible_ids = np.unique(idbuf[idbuf >= 0])

        sample_x = np.full((atlas_size, atlas_size), -1.0, dtype=np.float32)
        sample_y = np.full((atlas_size, atlas_size), -1.0, dtype=np.float32)
        confidence_map = np.zeros((atlas_size, atlas_size), dtype=np.uint8)
        coverage_map = np.zeros((atlas_size, atlas_size), dtype=np.uint8)
        written_texels = 0
        for tri_index in visible_ids.tolist():
            tri_i = int(tri_index)
            written_texels += _rasterize_uv_samples(
                triangles_uv[tri_i],
                triangles_screen[tri_i],
                triangle_confidence[tri_i],
                sample_x,
                sample_y,
                confidence_map,
                coverage_map,
            )

        prefix = f"camera_{cam_index:03d}"
        arrays[f"{prefix}_sample_x"] = sample_x
        arrays[f"{prefix}_sample_y"] = sample_y
        arrays[f"{prefix}_confidence"] = confidence_map
        arrays[f"{prefix}_coverage"] = coverage_map

        covered = coverage_map > 0
        confidence_values = confidence_map[covered]
        return {
            "camera_index": cam_index,
            "ok": True,
            "keyframe": keyframe,
            "image_path": _image_path(image),
            "image_name": image.name,
            "source_image_size": [source_width, source_height],
            "pins_count": int(cam_item.pins_count),
            "has_pins": bool(cam_item.has_pins()),
            "use_in_tex_baking": bool(cam_item.use_in_tex_baking),
            "focal": float(cam_item.focal),
            "front_candidate_triangles": len(triangles_screen),
            "visible_triangles": int(len(visible_ids)),
            "visible_triangle_ratio": float(len(visible_ids) / max(1, len(triangles_screen))),
            "skipped_backface_polygons": skipped_backface,
            "skipped_degenerate_triangles": skipped_degenerate,
            "uv_covered_pixels": int(covered.sum()),
            "uv_coverage_ratio": float(covered.sum() / max(1, atlas_size * atlas_size)),
            "mean_view_confidence": float(np.mean(confidence_values) / 255.0) if confidence_values.size else 0.0,
            "p75_view_confidence": float(np.percentile(confidence_values, 75) / 255.0) if confidence_values.size else 0.0,
            "written_texels": written_texels,
        }, arrays
    finally:
        obj_eval.to_mesh_clear()


def main() -> int:
    args = _parse_args(sys.argv)
    result: dict[str, Any] = {
        "schema_version": "facebuilder_mask_aware_step4_uv_sample_coords_v1",
        "ok": True,
        "blend_file": _safe_path(bpy.data.filepath),
        "blender": {
            "version": bpy.app.version_string,
            "background": bool(bpy.app.background),
        },
        "headnum": args.headnum,
        "atlas_size": args.atlas_size,
        "texture_only": bool(args.texture_only),
        "cameras": [],
    }
    arrays: dict[str, np.ndarray] = {}

    try:
        from bl_ext.user_default.keentools.addon_config import fb_settings

        settings = fb_settings()
        head = settings.get_head(args.headnum)
        if head is None:
            raise RuntimeError(f"FaceBuilder head not found: {args.headnum}")
        if head.headobj is None:
            raise RuntimeError("FaceBuilder head object is missing")

        if args.camera:
            camera_indices = [index for index in args.camera if 0 <= index < len(head.cameras)]
        else:
            camera_indices = list(range(len(head.cameras)))
        if args.texture_only:
            camera_indices = [
                index for index in camera_indices
                if bool(head.cameras[index].use_in_tex_baking)
            ]

        result["head"] = {
            "headobj": head.headobj.name,
            "cameras_count": len(head.cameras),
            "selected_cameras_count": len(camera_indices),
            "uv_layer": head.headobj.data.uv_layers.active.name if head.headobj.data.uv_layers.active else None,
        }

        for camera_index in camera_indices:
            metric, camera_arrays = _process_camera(head, camera_index, args.atlas_size)
            result["cameras"].append(metric)
            arrays.update(camera_arrays)

        ok_cameras = [camera for camera in result["cameras"] if camera.get("ok")]
        result["counts"] = {
            "selected_cameras": len(camera_indices),
            "ok_cameras": len(ok_cameras),
            "texture_enabled_ok_cameras": sum(1 for camera in ok_cameras if camera.get("use_in_tex_baking")),
        }
    except Exception as exc:  # noqa: BLE001 - diagnostic script.
        result["ok"] = False
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc(limit=12)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    if arrays:
        args.output_npz.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(args.output_npz, **arrays)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
