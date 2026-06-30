"""Project an existing FaceBuilder head mesh onto each FaceBuilder camera image.

Run with Blender:

    blender --background scene.blend --python blender_step1_project.py -- --output projection.json

This is Step 1 of the mask-aware correction path: it creates a reprojection
smoke-test dataset, not a new model. The host runner draws the returned
wireframe segments over the private input images.
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
from bpy_extras.object_utils import world_to_camera_view


def _parse_args(argv: list[str]) -> argparse.Namespace:
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--headnum", type=int, default=0)
    parser.add_argument("--max-edges-per-camera", type=int, default=7000)
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


def _matrix_to_list(value: Any) -> list[list[float]] | None:
    if value is None:
        return None
    try:
        return [[float(cell) for cell in row] for row in value]
    except Exception:
        return None


def _project_camera(head: Any, cam_index: int, max_edges: int) -> dict[str, Any]:
    scene = bpy.context.scene
    cam_item = head.cameras[cam_index]
    camobj = cam_item.camobj
    image = cam_item.cam_image
    headobj = head.headobj

    if camobj is None or image is None or headobj is None:
        return {
            "camera_index": cam_index,
            "ok": False,
            "reason": "missing_camera_image_or_head",
        }

    keyframe = cam_item.get_keyframe()
    scene.frame_set(keyframe)
    scene.camera = camobj

    width, height = [int(v) for v in image.size]
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.pixel_aspect_x = 1.0
    scene.render.pixel_aspect_y = 1.0

    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = headobj.evaluated_get(depsgraph)
    mesh = obj_eval.to_mesh()
    matrix_world = obj_eval.matrix_world.copy()
    normal_matrix = matrix_world.to_3x3()
    camera_location = camobj.matrix_world.translation.copy()

    try:
        projected: list[tuple[float, float, float]] = []
        inside_count = 0
        in_front_count = 0
        min_x = math.inf
        min_y = math.inf
        max_x = -math.inf
        max_y = -math.inf

        world_vertices = [matrix_world @ vertex.co for vertex in mesh.vertices]
        for world in world_vertices:
            co = world_to_camera_view(scene, camobj, world)
            px = float(co.x) * width
            py = (1.0 - float(co.y)) * height
            depth = float(co.z)
            projected.append((px, py, depth))
            if depth > 0:
                in_front_count += 1
                if 0 <= px < width and 0 <= py < height:
                    inside_count += 1
                    min_x = min(min_x, px)
                    min_y = min(min_y, py)
                    max_x = max(max_x, px)
                    max_y = max(max_y, py)

        candidate_edges: list[tuple[int, int, int, int]] = []
        candidate_edges_set: set[tuple[int, int]] = set()
        front_poly_count = 0
        for poly in mesh.polygons:
            vertices = list(poly.vertices)
            if len(vertices) < 3:
                continue
            center = sum((world_vertices[index] for index in vertices), world_vertices[vertices[0]] * 0.0) / len(vertices)
            normal_world = normal_matrix @ poly.normal
            try:
                normal_world.normalize()
            except Exception:
                pass
            to_camera = camera_location - center
            front_facing = normal_world.dot(to_camera) > 0.0
            if not front_facing:
                continue
            front_poly_count += 1
            for offset, vertex_a in enumerate(vertices):
                vertex_b = vertices[(offset + 1) % len(vertices)]
                edge_key = (min(vertex_a, vertex_b), max(vertex_a, vertex_b))
                if edge_key in candidate_edges_set:
                    continue
                pa = projected[vertex_a]
                pb = projected[vertex_b]
                if pa[2] <= 0 or pb[2] <= 0:
                    continue
                margin = max(width, height) * 0.08
                if (
                    (pa[0] < -margin and pb[0] < -margin)
                    or (pa[0] > width + margin and pb[0] > width + margin)
                    or (pa[1] < -margin and pb[1] < -margin)
                    or (pa[1] > height + margin and pb[1] > height + margin)
                ):
                    continue
                candidate_edges_set.add(edge_key)
                candidate_edges.append((
                    int(round(pa[0])),
                    int(round(pa[1])),
                    int(round(pb[0])),
                    int(round(pb[1])),
                ))

        edge_stride = 1
        if max_edges > 0 and len(candidate_edges) > max_edges:
            edge_stride = max(1, math.ceil(len(candidate_edges) / max_edges))
            draw_edges = candidate_edges[::edge_stride][:max_edges]
        else:
            draw_edges = candidate_edges

        bbox = None
        if inside_count > 0:
            bbox = [int(round(min_x)), int(round(min_y)), int(round(max_x)), int(round(max_y))]

        coverage_ratio = 0.0
        if bbox:
            coverage_ratio = max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1]) / max(1, width * height)

        return {
            "camera_index": cam_index,
            "ok": True,
            "keyframe": keyframe,
            "image_path": _image_path(image),
            "image_name": image.name,
            "image_size": [width, height],
            "pins_count": int(cam_item.pins_count),
            "has_pins": bool(cam_item.has_pins()),
            "use_in_tex_baking": bool(cam_item.use_in_tex_baking),
            "focal": float(cam_item.focal),
            "auto_focal_estimation": bool(cam_item.auto_focal_estimation),
            "projection_matrix": _matrix_to_list(cam_item.get_projection_matrix()),
            "camera_matrix_world": _matrix_to_list(camobj.matrix_world),
            "head_matrix_world": _matrix_to_list(headobj.matrix_world),
            "vertex_count": len(mesh.vertices),
            "polygon_count": len(mesh.polygons),
            "front_polygon_count": front_poly_count,
            "vertices_in_front_ratio": in_front_count / max(1, len(mesh.vertices)),
            "vertices_inside_image_ratio": inside_count / max(1, len(mesh.vertices)),
            "projected_bbox": bbox,
            "projected_bbox_coverage_ratio": coverage_ratio,
            "candidate_edge_count": len(candidate_edges),
            "draw_edge_count": len(draw_edges),
            "edge_stride": edge_stride,
            "draw_edges": draw_edges,
        }
    finally:
        obj_eval.to_mesh_clear()


def main() -> int:
    args = _parse_args(sys.argv)
    result: dict[str, Any] = {
        "schema_version": "facebuilder_mask_aware_step1_projection_v1",
        "ok": True,
        "blend_file": _safe_path(bpy.data.filepath),
        "blender": {
            "version": bpy.app.version_string,
            "background": bool(bpy.app.background),
        },
        "headnum": args.headnum,
        "cameras": [],
    }

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

        result["head"] = {
            "headobj": head.headobj.name,
            "cameras_count": len(head.cameras),
            "selected_cameras_count": len(camera_indices),
        }
        for camera_index in camera_indices:
            result["cameras"].append(_project_camera(head, camera_index, args.max_edges_per_camera))
    except Exception as exc:  # noqa: BLE001 - diagnostic script.
        result["ok"] = False
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc(limit=12)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
