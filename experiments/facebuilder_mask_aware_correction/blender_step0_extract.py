"""Extract Step 0 FaceBuilder scene data from an existing .blend file.

Run with Blender:

    blender --background scene.blend --python blender_step0_extract.py -- --output out.json --npz out.npz

This script is diagnostic only. It reads the FaceBuilder scene, summarizes the
head mesh, UVs, texture image references, camera image paths, pins, focal data,
projection matrices, and the same per-camera model/geo values that KeenTools
passes into its TextureBuilder.

Private paths and generated diagnostics should stay in Drive/local output, not
in Git.
"""

from __future__ import annotations

import argparse
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
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--npz", type=Path, default=None)
    parser.add_argument("--headnum", type=int, default=0)
    parser.add_argument("--max-camera-value-samples", type=int, default=12)
    return parser.parse_args(argv)


def _safe_path(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).replace("\\", "/")


def _matrix_to_list(value: Any) -> list[list[float]] | None:
    if value is None:
        return None
    try:
        arr = np.asarray(value, dtype=np.float64)
    except Exception:
        try:
            arr = np.asarray(value.transposed(), dtype=np.float64)
        except Exception:
            return None
    if arr.ndim != 2:
        return None
    return arr.tolist()


def _array_summary(value: Any, max_samples: int = 12) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "available": False,
        "python_type": type(value).__name__,
    }
    try:
        arr = np.asarray(value)
    except Exception as exc:  # noqa: BLE001 - diagnostic conversion.
        summary.update({
            "conversion_ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "dir_sample": [name for name in dir(value) if not name.startswith("_")][:60],
        })
        return summary

    summary.update({
        "available": True,
        "conversion_ok": True,
        "shape": list(arr.shape),
        "dtype": str(arr.dtype),
    })
    if arr.shape == () or arr.dtype == object:
        summary["array_usable_as_numeric_geometry"] = False
        summary["repr"] = repr(value)[:500]
        summary["dir_sample"] = [name for name in dir(value) if not name.startswith("_")][:80]
    else:
        summary["array_usable_as_numeric_geometry"] = True
    if arr.size:
        flat = arr.reshape(-1)
        sample = flat[:max_samples]
        try:
            summary["sample"] = [float(x) for x in sample]
            numeric = arr.astype(np.float64, copy=False)
            summary["min"] = float(np.nanmin(numeric))
            summary["max"] = float(np.nanmax(numeric))
        except Exception:
            summary["sample"] = [str(x) for x in sample]
    return summary


def _safe_call(label: str, func: Any) -> dict[str, Any]:
    try:
        value = func()
    except Exception as exc:  # noqa: BLE001 - diagnostic script.
        return {
            "label": label,
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=8),
        }
    return {"label": label, "ok": True, "value": value}


def _image_path(image: Any) -> str | None:
    if image is None or not image.filepath:
        return None
    return _safe_path(bpy.path.abspath(image.filepath))


def _image_info(image: Any) -> dict[str, Any] | None:
    if image is None:
        return None
    return {
        "name": image.name,
        "size": list(image.size),
        "filepath": _image_path(image),
        "packed": image.packed_file is not None,
        "source": str(getattr(image, "source", "")),
    }


def _material_texture_refs(obj: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if obj is None:
        return refs
    for slot_index, slot in enumerate(obj.material_slots):
        material = slot.material
        if material is None:
            continue
        entry: dict[str, Any] = {
            "slot_index": slot_index,
            "material_name": material.name,
            "use_nodes": bool(material.use_nodes),
            "images": [],
        }
        if material.use_nodes and material.node_tree is not None:
            for node in material.node_tree.nodes:
                image = getattr(node, "image", None)
                if image is not None:
                    entry["images"].append({
                        "node_name": node.name,
                        "node_type": node.type,
                        "image": _image_info(image),
                    })
        refs.append(entry)
    return refs


def _mesh_summary(obj: Any) -> dict[str, Any]:
    if obj is None or obj.type != "MESH":
        return {"available": False, "reason": "head object missing or not mesh"}

    mesh = obj.data
    vertices = np.asarray([obj.matrix_world @ v.co for v in mesh.vertices], dtype=np.float64)
    bbox = {
        "min": vertices.min(axis=0).tolist() if vertices.size else None,
        "max": vertices.max(axis=0).tolist() if vertices.size else None,
    }

    uv_layers = []
    for layer in mesh.uv_layers:
        sample = []
        for uv_data in layer.data[:12]:
            sample.append([float(uv_data.uv.x), float(uv_data.uv.y)])
        uv_layers.append({
            "name": layer.name,
            "data_count": len(layer.data),
            "sample": sample,
        })

    polygons_sample = []
    for poly in mesh.polygons[:8]:
        polygons_sample.append({
            "index": poly.index,
            "vertices": list(poly.vertices),
            "loop_indices": list(poly.loop_indices),
            "material_index": int(poly.material_index),
        })

    return {
        "available": True,
        "object_name": obj.name,
        "mesh_name": mesh.name,
        "vertex_count": len(mesh.vertices),
        "edge_count": len(mesh.edges),
        "polygon_count": len(mesh.polygons),
        "loop_count": len(mesh.loops),
        "uv_layer_count": len(mesh.uv_layers),
        "active_uv": mesh.uv_layers.active.name if mesh.uv_layers.active else None,
        "uv_layers": uv_layers,
        "bbox_world": bbox,
        "matrix_world": _matrix_to_list(obj.matrix_world),
        "polygons_sample": polygons_sample,
        "material_texture_refs": _material_texture_refs(obj),
    }


def _camera_summary(camera: Any, index: int) -> dict[str, Any]:
    image = camera.cam_image
    camobj = camera.camobj
    camdata = camobj.data if camobj else None
    projection = _safe_call("camera.get_projection_matrix", camera.get_projection_matrix)
    projection_value = projection.get("value") if projection.get("ok") else None
    return {
        "index": index,
        "keyframe": camera.get_keyframe(),
        "camobj": camobj.name if camobj else None,
        "image": _image_info(image),
        "image_width_prop": int(camera.image_width),
        "image_height_prop": int(camera.image_height),
        "oriented_image_size": list(camera.get_oriented_image_size()),
        "orientation": int(camera.orientation),
        "pins_count_prop": int(camera.pins_count),
        "has_pins": bool(camera.has_pins()),
        "use_in_tex_baking": bool(camera.use_in_tex_baking),
        "focal": float(camera.focal),
        "auto_focal_estimation": bool(camera.auto_focal_estimation),
        "focal_length_in_pixels_coef": float(camera.get_focal_length_in_pixels_coef()),
        "projection_matrix": _matrix_to_list(projection_value),
        "projection_matrix_ok": bool(projection.get("ok") and projection_value is not None),
        "camobj_matrix_world": _matrix_to_list(camobj.matrix_world) if camobj else None,
        "camobj_matrix_world_inverted": _matrix_to_list(camobj.matrix_world.inverted()) if camobj else None,
        "blender_camera_data": {
            "lens": float(camdata.lens) if camdata else None,
            "sensor_width": float(camdata.sensor_width) if camdata else None,
            "sensor_height": float(camdata.sensor_height) if camdata else None,
            "shift_x": float(camdata.shift_x) if camdata else None,
            "shift_y": float(camdata.shift_y) if camdata else None,
            "type": str(camdata.type) if camdata else None,
            "clip_start": float(camdata.clip_start) if camdata else None,
            "clip_end": float(camdata.clip_end) if camdata else None,
        },
    }


def _head_probe(headnum: int, max_samples: int) -> tuple[dict[str, Any], dict[str, Any]]:
    from bl_ext.user_default.keentools.addon_config import fb_settings
    from bl_ext.user_default.keentools.facebuilder.fbloader import FBLoader

    settings = fb_settings()
    head = settings.get_head(headnum)
    if head is None:
        return {"exists": False, "headnum": headnum}, {}

    FBLoader.load_model(headnum)
    fb = FBLoader.get_builder()
    try:
        FBLoader.select_uv_set(fb, head.tex_uv_shape)
    except Exception:
        pass

    mesh_info = _mesh_summary(head.headobj)
    camera_infos = [_camera_summary(cam, idx) for idx, cam in enumerate(head.cameras)]

    fb_methods = [
        name for name in dir(fb)
        if not name.startswith("_")
        and any(token in name.lower() for token in ("model", "geo", "uv", "pin", "projection", "focal"))
    ]

    per_camera_values: list[dict[str, Any]] = []
    npz_arrays: dict[str, Any] = {}
    for cam_index, cam in enumerate(head.cameras):
        keyframe = cam.get_keyframe()
        entry: dict[str, Any] = {
            "camera_index": cam_index,
            "keyframe": keyframe,
            "eligible_for_texture_builder": bool(cam.use_in_tex_baking and cam.has_pins() and cam.cam_image is not None),
        }
        model_probe = _safe_call("fb.model_mat", lambda keyframe=keyframe: fb.model_mat(keyframe))
        geo_probe = _safe_call("fb.applied_args_model_at", lambda keyframe=keyframe: fb.applied_args_model_at(keyframe))
        pins_probe = _safe_call("fb.pins_count", lambda keyframe=keyframe: fb.pins_count(keyframe))
        pixel_aspect_probe = _safe_call("fb.pixel_aspect_ratio", lambda keyframe=keyframe: fb.pixel_aspect_ratio(keyframe))

        model_value = model_probe.get("value") if model_probe.get("ok") else None
        geo_value = geo_probe.get("value") if geo_probe.get("ok") else None

        entry["model_mat"] = {
            "ok": bool(model_probe.get("ok")),
            "matrix": _matrix_to_list(model_value),
            "summary": _array_summary(model_value, max_samples) if model_value is not None else None,
        }
        entry["applied_args_model_at"] = {
            "ok": bool(geo_probe.get("ok")),
            "summary": _array_summary(geo_value, max_samples) if geo_value is not None else None,
        }
        entry["pins_count_builder"] = pins_probe
        entry["pixel_aspect_ratio"] = pixel_aspect_probe

        try:
            if model_value is not None:
                npz_arrays[f"camera_{cam_index:03d}_model_mat"] = np.asarray(model_value, dtype=np.float32)
        except Exception:
            pass
        try:
            if geo_value is not None:
                geo_arr = np.asarray(geo_value, dtype=np.float32)
                if geo_arr.size and geo_arr.ndim in (2, 3):
                    npz_arrays[f"camera_{cam_index:03d}_geo"] = geo_arr
        except Exception:
            pass
        projection = camera_infos[cam_index].get("projection_matrix")
        if projection is not None:
            npz_arrays[f"camera_{cam_index:03d}_projection"] = np.asarray(projection, dtype=np.float32)

        per_camera_values.append(entry)

    if head.headobj is not None and head.headobj.type == "MESH":
        mesh = head.headobj.data
        npz_arrays["mesh_vertices_world"] = np.asarray(
            [head.headobj.matrix_world @ v.co for v in mesh.vertices], dtype=np.float32
        )
        npz_arrays["mesh_vertices_local"] = np.asarray([v.co for v in mesh.vertices], dtype=np.float32)
        npz_arrays["mesh_loop_vertex_indices"] = np.asarray([loop.vertex_index for loop in mesh.loops], dtype=np.int32)
        npz_arrays["mesh_polygon_loop_start"] = np.asarray([poly.loop_start for poly in mesh.polygons], dtype=np.int32)
        npz_arrays["mesh_polygon_loop_total"] = np.asarray([poly.loop_total for poly in mesh.polygons], dtype=np.int32)
        npz_arrays["mesh_polygon_material_indices"] = np.asarray([poly.material_index for poly in mesh.polygons], dtype=np.int32)

        tri_vertex_indices = []
        tri_loop_indices = []
        for poly in mesh.polygons:
            vertices = list(poly.vertices)
            loops = list(poly.loop_indices)
            for item_index in range(1, len(vertices) - 1):
                tri_vertex_indices.append([vertices[0], vertices[item_index], vertices[item_index + 1]])
                tri_loop_indices.append([loops[0], loops[item_index], loops[item_index + 1]])
        if tri_vertex_indices:
            npz_arrays["mesh_tri_vertex_indices"] = np.asarray(tri_vertex_indices, dtype=np.int32)
            npz_arrays["mesh_tri_loop_indices"] = np.asarray(tri_loop_indices, dtype=np.int32)
        if mesh.uv_layers.active is not None:
            npz_arrays["active_uv_loop_data"] = np.asarray(
                [[uv.uv.x, uv.uv.y] for uv in mesh.uv_layers.active.data], dtype=np.float32
            )

    result = {
        "exists": True,
        "headnum": headnum,
        "headobj": head.headobj.name if head.headobj else None,
        "model_type": str(getattr(head, "model_type", "")),
        "tex_uv_shape": str(getattr(head, "tex_uv_shape", "")),
        "cameras_count": len(head.cameras),
        "pinned_cameras_count": sum(1 for cam in head.cameras if cam.has_pins()),
        "texture_enabled_cameras_count": sum(1 for cam in head.cameras if cam.use_in_tex_baking),
        "texture_builder_eligible_cameras_count": sum(
            1 for cam in head.cameras if cam.use_in_tex_baking and cam.has_pins() and cam.cam_image is not None
        ),
        "has_cameras": bool(head.has_cameras()),
        "has_pins": bool(head.has_pins()),
        "mesh": mesh_info,
        "cameras": camera_infos,
        "fb_method_names_relevant_sample": fb_methods[:180],
        "per_camera_builder_values": per_camera_values,
    }
    return result, npz_arrays


def main() -> int:
    args = _parse_args(sys.argv)
    result: dict[str, Any] = {
        "schema_version": "facebuilder_mask_aware_step0_probe_v1",
        "ok": True,
        "blend_file": _safe_path(bpy.data.filepath),
        "blender": {
            "version": bpy.app.version_string,
            "background": bool(bpy.app.background),
        },
        "scene_images": [_image_info(image) for image in bpy.data.images],
        "heads": [],
    }
    npz_arrays: dict[str, Any] = {}

    try:
        from bl_ext.user_default.keentools.addon_config import fb_settings

        settings = fb_settings()
        result["settings"] = {
            "heads_count": len(settings.heads),
            "current_headnum": int(settings.current_headnum),
            "tex_width": int(settings.tex_width),
            "tex_height": int(settings.tex_height),
            "tex_face_angles_affection": float(settings.tex_face_angles_affection),
            "tex_uv_expand_percents": float(settings.tex_uv_expand_percents),
            "tex_back_face_culling": bool(settings.tex_back_face_culling),
            "tex_equalize_brightness": bool(settings.tex_equalize_brightness),
            "tex_equalize_colour": bool(settings.tex_equalize_colour),
            "tex_fill_gaps": bool(settings.tex_fill_gaps),
        }
        headnums = [args.headnum] if args.headnum >= 0 else list(range(len(settings.heads)))
        for headnum in headnums:
            head_result, arrays = _head_probe(headnum, args.max_camera_value_samples)
            result["heads"].append(head_result)
            for key, value in arrays.items():
                npz_arrays[f"head_{headnum}_{key}"] = value
    except Exception as exc:  # noqa: BLE001 - diagnostic script.
        result["ok"] = False
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc(limit=12)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")

    if args.npz is not None and npz_arrays:
        args.npz.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(args.npz, **npz_arrays)

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
