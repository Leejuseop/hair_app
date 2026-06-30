"""Render a FaceBuilder head with a supplied diagnostic texture."""

from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from pathlib import Path
from typing import Any

import bpy


DEFAULT_YAWS = [-45, -30, -15, 0, 15, 30, 45]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser()
    parser.add_argument("--texture", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--headnum", type=int, default=0)
    parser.add_argument("--yaw", action="append", type=int, default=None)
    return parser.parse_args(argv)


def _safe_path(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).replace("\\", "/")


def _mesh_bbox(obj: Any) -> dict[str, Any]:
    import mathutils

    coords = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
    mins = [min(float(c[i]) for c in coords) for i in range(3)]
    maxs = [max(float(c[i]) for c in coords) for i in range(3)]
    center = [(mins[i] + maxs[i]) * 0.5 for i in range(3)]
    size = [maxs[i] - mins[i] for i in range(3)]
    return {"min": mins, "max": maxs, "center": center, "size": size}


def _head_object(headnum: int) -> Any:
    try:
        from bl_ext.user_default.keentools.addon_config import fb_settings

        settings = fb_settings()
        head = settings.get_head(headnum)
        if head is not None and head.headobj is not None:
            return head.headobj
    except Exception:
        pass
    obj = bpy.data.objects.get("FBHead")
    if obj is not None:
        return obj
    for candidate in bpy.context.scene.objects:
        if candidate.type == "MESH":
            return candidate
    raise RuntimeError("Could not find FaceBuilder head mesh")


def _assign_texture(head_obj: Any, texture_path: Path) -> dict[str, Any]:
    image = bpy.data.images.load(str(texture_path), check_existing=True)
    if not head_obj.data.materials:
        material = bpy.data.materials.new("HairApp_Step4_Texture")
        head_obj.data.materials.append(material)
    else:
        material = head_obj.data.materials[0]
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    tex_node = None
    for node in nodes:
        if node.type == "TEX_IMAGE":
            tex_node = node
            break
    if tex_node is None:
        tex_node = nodes.new(type="ShaderNodeTexImage")
    tex_node.image = image
    try:
        links.new(tex_node.outputs["Color"], bsdf.inputs["Base Color"])
    except Exception:
        pass
    material.diffuse_color = (1.0, 1.0, 1.0, 1.0)
    return {"material": material.name, "image": image.name, "texture": _safe_path(texture_path)}


def _setup_review_scene(head_obj: Any) -> dict[str, Any]:
    import mathutils

    for obj in bpy.context.scene.objects:
        if obj != head_obj:
            obj.hide_render = True

    bbox = _mesh_bbox(head_obj)
    center = bbox["center"]
    size = bbox["size"]
    largest = max(size) if max(size) > 0 else 2.0

    bpy.ops.object.light_add(type="AREA", location=(center[0], center[1] - largest * 2.5, center[2] + largest * 1.5))
    light = bpy.context.object
    light.name = "HairApp_Step4_AreaLight"
    light.data.energy = 500
    light.data.size = largest * 2.2

    bpy.ops.object.camera_add(location=(center[0], center[1] - largest * 3.0, center[2] + largest * 0.05))
    camera = bpy.context.object
    camera.name = "HairApp_Step4_Camera"
    direction = mathutils.Vector((center[0], center[1], center[2])) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = largest * 1.25
    bpy.context.scene.camera = camera

    bpy.context.scene.render.resolution_x = 900
    bpy.context.scene.render.resolution_y = 1100
    bpy.context.scene.render.film_transparent = False
    bpy.context.scene.world.color = (0.03, 0.03, 0.03)
    try:
        bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        try:
            bpy.context.scene.render.engine = "BLENDER_EEVEE"
        except Exception:
            pass
    return {"bbox": bbox, "camera": camera.name, "light": light.name}


def main() -> int:
    args = _parse_args(sys.argv)
    result: dict[str, Any] = {
        "schema_version": "facebuilder_mask_aware_step4_render_texture_v1",
        "ok": True,
        "blend_file": _safe_path(bpy.data.filepath),
        "texture": _safe_path(args.texture),
        "output_dir": _safe_path(args.output_dir),
        "renders": [],
    }
    try:
        head_obj = _head_object(args.headnum)
        result["head_object"] = head_obj.name
        result["material"] = _assign_texture(head_obj, args.texture)
        result["setup"] = _setup_review_scene(head_obj)
        yaws = args.yaw or DEFAULT_YAWS
        original_rotation = head_obj.rotation_euler.copy()
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for yaw in yaws:
            head_obj.rotation_euler = original_rotation.copy()
            head_obj.rotation_euler.rotate_axis("Z", math.radians(yaw))
            bpy.context.view_layer.update()
            path = args.output_dir / f"render_yaw_{yaw:+03d}.png"
            bpy.context.scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            result["renders"].append({"yaw": yaw, "path": _safe_path(path)})
        head_obj.rotation_euler = original_rotation
    except Exception as exc:  # noqa: BLE001 - diagnostic script.
        result["ok"] = False
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc(limit=12)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
