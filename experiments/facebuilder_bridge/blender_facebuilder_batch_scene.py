"""Build one FaceBuilder batch scene inside headless Blender.

This script is launched by `facebuilder_version_runner.py`. It consumes a
private input manifest, creates a FaceBuilder head, adds each selected image as
a camera, attempts auto-align, bakes a texture, applies a simple Hair App
material/post-process preparation, exports OBJ/GLB when possible, and renders
front-to-45 review images.

Run with Blender, not system Python.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import bpy


YAW_DEGREES = [0, 15, 30, 45, -15, -30, -45]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bake-texture", action="store_true")
    parser.add_argument("--save-blend", action="store_true")
    parser.add_argument("--export-obj", action="store_true")
    parser.add_argument("--export-glb", action="store_true")
    parser.add_argument("--render-review", action="store_true")
    return parser.parse_args(argv)


def _safe_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _ensure_dirs(output_dir: Path) -> dict[str, Path]:
    folders = {
        "alignment": output_dir / "02_alignment",
        "scene": output_dir / "03_facebuilder_scene",
        "exports": output_dir / "04_exports",
        "postprocess": output_dir / "05_postprocess",
        "glb": output_dir / "06_glb",
        "review": output_dir / "07_review_sheets",
        "logs": output_dir / "logs",
    }
    for path in folders.values():
        path.mkdir(parents=True, exist_ok=True)
    return folders


def _camera_info(camera: Any, index: int) -> dict[str, Any]:
    image = camera.cam_image
    return {
        "index": index,
        "keyframe": camera.get_keyframe(),
        "camobj": camera.camobj.name if camera.camobj else None,
        "image_name": image.name if image else None,
        "image_size": list(image.size) if image else None,
        "image_filepath": _safe_path(bpy.path.abspath(image.filepath)) if image and image.filepath else None,
        "pins_count_prop": camera.pins_count,
        "has_pins": camera.has_pins(),
        "use_in_tex_baking": camera.use_in_tex_baking,
        "focal": camera.focal,
        "auto_focal_estimation": camera.auto_focal_estimation,
    }


def _head_summary(settings: Any, headnum: int) -> dict[str, Any]:
    head = settings.get_head(headnum)
    if head is None:
        return {"headnum": headnum, "exists": False}
    return {
        "headnum": headnum,
        "exists": True,
        "headobj": head.headobj.name if head.headobj else None,
        "cameras_count": len(head.cameras),
        "pinned_cameras_count": sum(1 for camera in head.cameras if camera.has_pins()),
        "has_pins": head.has_pins(),
        "cameras": [_camera_info(camera, index) for index, camera in enumerate(head.cameras)],
    }


def _set_camera_bake_enabled(camera: Any, enabled: bool) -> None:
    try:
        camera.use_in_tex_baking = bool(enabled)
    except Exception:
        pass


def _align_camera(headnum: int, camnum: int) -> dict[str, Any]:
    from bl_ext.user_default.keentools.addon_config import fb_settings
    from bl_ext.user_default.keentools.facebuilder.fbloader import FBLoader
    from bl_ext.user_default.keentools.utils.coords import update_head_mesh_non_neutral
    from bl_ext.user_default.keentools.utils.focal_length import configure_focal_mode_and_fixes
    from bl_ext.user_default.keentools.utils.images import load_rgba

    settings = fb_settings()
    settings.current_headnum = headnum
    head = settings.get_head(headnum)
    if head is None:
        return {"ok": False, "reason": "head_not_found", "headnum": headnum}
    camera = head.get_camera(camnum)
    if camera is None:
        return {"ok": False, "reason": "camera_not_found", "camnum": camnum}

    image = load_rgba(camera)
    if image is None:
        _set_camera_bake_enabled(camera, False)
        return {"ok": False, "reason": "image_load_failed", "camnum": camnum}

    fb = FBLoader.get_builder()
    fb.set_use_emotions(head.should_use_emotions())

    keyframe = camera.get_keyframe()
    if not fb.is_key_at(keyframe):
        fb.set_centered_geo_keyframe(keyframe)

    configure_focal_mode_and_fixes(fb, head)

    before_pins = fb.pins_count(keyframe) if fb.is_key_at(keyframe) else 0
    pixel_aspect_ratio = fb.pixel_aspect_ratio(keyframe)
    faces = fb.detect_faces(image, pixel_aspect_ratio)
    faces_count = len(faces) if faces is not None else None
    if not faces:
        _set_camera_bake_enabled(camera, False)
        return {
            "ok": False,
            "reason": "no_faces_detected",
            "camnum": camnum,
            "keyframe": keyframe,
            "image_shape": list(image.shape),
            "before_pins": before_pins,
            "faces_count": faces_count,
        }

    pose_ok = fb.detect_face_pose(keyframe, faces[0])
    after_pose_pins = fb.pins_count(keyframe) if fb.is_key_at(keyframe) else 0
    if pose_ok:
        fb.remove_pins(keyframe)
        fb.add_preset_pins_and_solve(keyframe)
        update_head_mesh_non_neutral(fb, head)
        FBLoader.update_camera_pins_count(headnum, camnum)

    after_solve_pins = fb.pins_count(keyframe) if fb.is_key_at(keyframe) else 0
    ok = bool(pose_ok and after_solve_pins > 0)
    _set_camera_bake_enabled(camera, ok)
    return {
        "ok": ok,
        "reason": "aligned" if ok else "detect_face_pose_failed",
        "camnum": camnum,
        "keyframe": keyframe,
        "image_shape": list(image.shape),
        "before_pins": before_pins,
        "faces_count": faces_count,
        "detect_face_pose_ok": bool(pose_ok),
        "after_pose_pins": after_pose_pins,
        "after_solve_pins": after_solve_pins,
        "camera_pins_count_prop": camera.pins_count,
    }


def _bake_texture(headnum: int, output_path: Path) -> dict[str, Any]:
    from bl_ext.user_default.keentools.utils.materials import bake_tex

    texture_name = f"HairAppTexture_{headnum}"
    status = bake_tex(headnum, texture_name)
    image = bpy.data.images.get(texture_name)
    result = {
        "ok": bool(status.success and image is not None),
        "status_success": bool(status.success),
        "status_error_message": status.error_message,
        "texture_name": texture_name,
        "image_exists": image is not None,
        "image_size": list(image.size) if image else None,
        "saved_texture": None,
    }
    if image is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.filepath_raw = str(output_path)
        image.file_format = "PNG"
        image.save()
        result["saved_texture"] = _safe_path(output_path)
    return result


def _cleanup_baked_texture(raw_path: Path, cleanup_path: Path, report_path: Path) -> dict[str, Any]:
    import numpy as np

    def connected_component_mask(mask: Any, min_pixels: int, border_min_pixels: int) -> Any:
        try:
            import cv2  # type: ignore

            count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype("uint8"), connectivity=4)
            keep = np.zeros(mask.shape, dtype=bool)
            height_, width_ = mask.shape
            for label in range(1, count):
                area = int(stats[label, cv2.CC_STAT_AREA])
                x = int(stats[label, cv2.CC_STAT_LEFT])
                y = int(stats[label, cv2.CC_STAT_TOP])
                w = int(stats[label, cv2.CC_STAT_WIDTH])
                h = int(stats[label, cv2.CC_STAT_HEIGHT])
                touches_border = x <= 1 or y <= 1 or x + w >= width_ - 1 or y + h >= height_ - 1
                if area >= min_pixels or (touches_border and area >= border_min_pixels):
                    keep |= labels == label
            return keep
        except Exception:
            height_, width_ = mask.shape
            visited = np.zeros(mask.shape, dtype=bool)
            keep = np.zeros(mask.shape, dtype=bool)
            ys, xs = np.nonzero(mask)
            for start_y, start_x in zip(ys.tolist(), xs.tolist()):
                if visited[start_y, start_x]:
                    continue
                stack = [(start_y, start_x)]
                component: list[tuple[int, int]] = []
                touches_border = False
                visited[start_y, start_x] = True
                while stack:
                    y, x = stack.pop()
                    component.append((y, x))
                    if y <= 1 or x <= 1 or y >= height_ - 2 or x >= width_ - 2:
                        touches_border = True
                    for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                        if 0 <= ny < height_ and 0 <= nx < width_ and mask[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            stack.append((ny, nx))
                area = len(component)
                if area >= min_pixels or (touches_border and area >= border_min_pixels):
                    for y, x in component:
                        keep[y, x] = True
            return keep

    image = bpy.data.images.load(str(raw_path), check_existing=True)
    width, height = image.size
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    rgba = pixels.reshape((height, width, 4))
    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3]
    luma = rgb[:, :, 0] * 0.2126 + rgb[:, :, 1] * 0.7152 + rgb[:, :, 2] * 0.0722
    maxc = np.max(rgb, axis=2)
    minc = np.min(rgb, axis=2)
    saturation = (maxc - minc) / np.maximum(maxc, 1e-5)

    skin_mask = (
        (alpha > 0.1)
        & (luma > 0.22)
        & (luma < 0.86)
        & (rgb[:, :, 0] > rgb[:, :, 2] * 1.04)
        & (rgb[:, :, 1] > rgb[:, :, 2] * 0.82)
        & (saturation < 0.62)
    )
    if np.count_nonzero(skin_mask) > 64:
        skin_color = np.median(rgb[skin_mask], axis=0)
    else:
        skin_color = np.array([0.62, 0.46, 0.38], dtype=np.float32)

    # Heuristic bald-head cleanup. It targets only the most damaging non-skin
    # atlas texels: empty texels, large near-black blobs, and strongly colored
    # clothing/background leaks. Small dark details such as eyebrows and pupils
    # should survive this pass; semantic matting is still future work.
    raw_dark_mask = (alpha > 0.1) & (luma < 0.27) & (saturation < 0.92)
    dark_hair_mask = connected_component_mask(
        raw_dark_mask,
        min_pixels=max(120, int(width * height * 0.00018)),
        border_min_pixels=max(36, int(width * height * 0.000045)),
    )
    not_red_feature = rgb[:, :, 0] < np.maximum(rgb[:, :, 1], rgb[:, :, 2]) * 1.16
    raw_color_leak_mask = (
        (alpha > 0.1)
        & (luma < 0.72)
        & (saturation > 0.42)
        & ~skin_mask
        & not_red_feature
    )
    color_leak_mask = connected_component_mask(
        raw_color_leak_mask,
        min_pixels=max(90, int(width * height * 0.00012)),
        border_min_pixels=max(28, int(width * height * 0.000035)),
    )
    empty_mask = alpha < 0.05
    replace_mask = dark_hair_mask | color_leak_mask | empty_mask

    cleaned = rgba.copy()
    # Add a gentle luma ramp from the original texture so the fallback does not
    # become one flat sticker.
    tone = np.clip(luma[..., None] * 0.35 + 0.78, 0.68, 1.08)
    replacement = np.clip(skin_color.reshape((1, 1, 3)) * tone, 0.0, 1.0)
    cleaned[:, :, :3][replace_mask] = replacement[replace_mask]
    cleaned[:, :, 3][replace_mask] = 1.0

    out = bpy.data.images.new("HairApp_BaldCleanup_Texture", width=width, height=height, alpha=True)
    out.pixels.foreach_set(cleaned.reshape(-1))
    out.update()
    cleanup_path.parent.mkdir(parents=True, exist_ok=True)
    out.filepath_raw = str(cleanup_path)
    out.file_format = "PNG"
    out.save()

    report = {
        "schema_version": "hair_app_bald_texture_cleanup_v1",
        "raw_texture": _safe_path(raw_path),
        "cleanup_texture": _safe_path(cleanup_path),
        "width": width,
        "height": height,
        "skin_reference_rgb": [float(x) for x in skin_color],
        "skin_reference_pixels": int(np.count_nonzero(skin_mask)),
        "raw_dark_pixels": int(np.count_nonzero(raw_dark_mask)),
        "raw_color_leak_pixels": int(np.count_nonzero(raw_color_leak_mask)),
        "dark_hair_pixels": int(np.count_nonzero(dark_hair_mask)),
        "color_leak_pixels": int(np.count_nonzero(color_leak_mask)),
        "empty_pixels": int(np.count_nonzero(empty_mask)),
        "replaced_pixels": int(np.count_nonzero(replace_mask)),
        "replaced_ratio": float(np.mean(replace_mask)),
        "notes": [
            "heuristic_cleanup_not_final_semantic_matting",
            "preserves raw texture separately",
            "used for current review material and GLB export",
        ],
    }
    _write_json(report_path, report)
    return {"ok": cleanup_path.exists(), **report}


def _head_object(settings: Any, headnum: int) -> Any:
    head = settings.get_head(headnum)
    if head is not None and head.headobj is not None:
        return head.headobj
    return None


def _mesh_bbox(obj: Any) -> dict[str, Any]:
    import mathutils

    coords = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
    mins = [min(v[i] for v in coords) for i in range(3)]
    maxs = [max(v[i] for v in coords) for i in range(3)]
    center = [(mins[i] + maxs[i]) * 0.5 for i in range(3)]
    size = [maxs[i] - mins[i] for i in range(3)]
    return {"min": mins, "max": maxs, "center": center, "size": size}


def _apply_hair_app_material(head_obj: Any, texture_path: Path | None, output_dir: Path) -> dict[str, Any]:
    result = {
        "ok": head_obj is not None,
        "head_object": head_obj.name if head_obj else None,
        "texture_path": _safe_path(texture_path) if texture_path else None,
        "material_name": None,
        "bbox": None,
        "warnings": [],
    }
    if head_obj is None:
        result["warnings"].append("head_object_missing")
        return result

    material = bpy.data.materials.new("HairApp_BaldHead_Material")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf is not None:
        try:
            bsdf.inputs["Roughness"].default_value = 0.58
        except Exception:
            pass
        try:
            bsdf.inputs["Metallic"].default_value = 0.0
        except Exception:
            pass
    if texture_path and texture_path.exists() and bsdf is not None:
        try:
            image = bpy.data.images.load(str(texture_path), check_existing=True)
            tex = nodes.new(type="ShaderNodeTexImage")
            tex.image = image
            material.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        except Exception as exc:  # noqa: BLE001
            result["warnings"].append(f"texture_material_link_failed:{type(exc).__name__}")

    head_obj.data.materials.clear()
    head_obj.data.materials.append(material)
    result["material_name"] = material.name
    result["bbox"] = _mesh_bbox(head_obj)

    prep_manifest = {
        "schema_version": "hair_app_bald_head_prep_v1",
        "head_object": head_obj.name,
        "material": material.name,
        "bbox": result["bbox"],
        "hair_fitting_contract": {
            "status": "placeholder_contract",
            "goal": "prepare exported bald head for future scalp/hair fitting",
            "needs_future_work": [
                "semantic scalp mask",
                "hairline anchors",
                "ear/face/neck collision regions",
                "clean eye and mouth materials",
                "head scale/orientation normalization",
            ],
        },
    }
    _write_json(output_dir / "05_postprocess" / "hair_fitting_prep_manifest.json", prep_manifest)
    return result


def _select_only(obj: Any) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _export_obj(head_obj: Any, output_path: Path) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _select_only(head_obj)
    if hasattr(bpy.ops.wm, "obj_export"):
        value = bpy.ops.wm.obj_export(filepath=str(output_path), export_selected_objects=True)
    else:
        value = bpy.ops.export_scene.obj(filepath=str(output_path), use_selection=True)
    return {"ok": output_path.exists(), "path": _safe_path(output_path), "operator_result": str(value)}


def _export_glb(head_obj: Any, output_path: Path) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _select_only(head_obj)
    value = bpy.ops.export_scene.gltf(
        filepath=str(output_path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
    )
    return {"ok": output_path.exists(), "path": _safe_path(output_path), "operator_result": str(value)}


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
    light.name = "HairApp_Review_AreaLight"
    light.data.energy = 450
    light.data.size = largest * 2.0

    bpy.ops.object.camera_add(location=(center[0], center[1] - largest * 3.0, center[2] + largest * 0.05))
    camera = bpy.context.object
    camera.name = "HairApp_Review_Camera"
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


def _render_review(head_obj: Any, output_dir: Path) -> dict[str, Any]:
    review_dir = output_dir / "07_review_sheets"
    review_dir.mkdir(parents=True, exist_ok=True)
    setup = _setup_review_scene(head_obj)
    original_rotation = head_obj.rotation_euler.copy()
    rendered: list[str] = []
    for yaw in YAW_DEGREES:
        head_obj.rotation_euler = original_rotation.copy()
        head_obj.rotation_euler.rotate_axis("Z", math.radians(yaw))
        bpy.context.view_layer.update()
        path = review_dir / f"render_yaw_{yaw:+03d}.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        rendered.append(_safe_path(path))
    head_obj.rotation_euler = original_rotation
    return {"ok": bool(rendered), "setup": setup, "rendered": rendered}


def _add_camera_candidate(headnum: int, image_path: Path) -> Any:
    from bl_ext.user_default.keentools.facebuilder.fbloader import FBLoader

    return FBLoader.add_new_camera_with_image(headnum, str(image_path))


def main() -> int:
    args = _parse_args(sys.argv)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    folders = _ensure_dirs(output_dir)
    manifest = _read_json(args.input_manifest)

    result: dict[str, Any] = {
        "schema_version": "facebuilder_blender_batch_result_v1",
        "created_at_unix": time.time(),
        "ok": False,
        "version": manifest.get("version"),
        "person": manifest.get("person"),
        "input_manifest": _safe_path(args.input_manifest),
        "output_dir": _safe_path(output_dir),
        "blender": {
            "version": bpy.app.version_string,
            "background": bpy.app.background,
        },
        "steps": [],
        "alignment": [],
        "texture_bake": None,
        "texture_cleanup": None,
        "postprocess": None,
        "exports": {},
        "review": None,
        "summary": {},
    }

    from bl_ext.user_default.keentools.addon_config import fb_settings
    from bl_ext.user_default.keentools.facebuilder.fbloader import FBLoader

    add_head = _safe_call("add_facebuilder_head", lambda: str(bpy.ops.keentools_fb.add_head()))
    result["steps"].append(add_head)
    if not add_head.get("ok") or "FINISHED" not in str(add_head.get("value")):
        _write_json(output_dir / "run_manifest.json", result)
        return 3

    settings = fb_settings()
    headnum = settings.get_last_headnum()
    settings.current_headnum = headnum

    for item in manifest.get("items", []):
        item_result = {
            "image_id": item.get("image_id"),
            "source_path": item.get("source_path"),
            "attempts": [],
            "selected_camera": None,
            "selected_candidate": None,
            "ok": False,
        }
        for candidate in item.get("candidates", []):
            candidate_path = Path(candidate["path"])
            add_camera = _safe_call(
                f"add_camera_{item_result['image_id']}_{candidate.get('kind')}",
                lambda candidate_path=candidate_path: _add_camera_candidate(headnum, candidate_path),
            )
            if not add_camera.get("ok"):
                item_result["attempts"].append({
                    "candidate": candidate,
                    "add_camera": add_camera,
                    "align": None,
                })
                continue

            head = settings.get_head(headnum)
            camnum = len(head.cameras) - 1
            camera = head.get_camera(camnum)
            align_result = _safe_call(
                f"align_camera_{camnum}",
                lambda camnum=camnum: _align_camera(headnum, camnum),
            )
            align_value = align_result.get("value") if align_result.get("ok") else {}
            if isinstance(align_value, dict) and align_value.get("ok") and not candidate.get("allow_texture_bake", True):
                _set_camera_bake_enabled(camera, False)
            attempt = {
                "candidate": candidate,
                "camera": _camera_info(camera, camnum) if camera else None,
                "align": align_result,
                "allow_texture_bake": bool(candidate.get("allow_texture_bake", True)),
            }
            item_result["attempts"].append(attempt)
            if isinstance(align_value, dict) and align_value.get("ok"):
                item_result["selected_camera"] = camnum
                item_result["selected_candidate"] = candidate
                item_result["ok"] = True
                break
        result["alignment"].append(item_result)

    result["head_after_align"] = _head_summary(settings, headnum)

    aligned_count = sum(1 for item in result["alignment"] if item.get("ok"))
    failed_count = len(result["alignment"]) - aligned_count
    if aligned_count:
        result["steps"].append(_safe_call(
            "save_facebuilder_state_after_align",
            lambda: FBLoader.save_fb_serial_and_image_pathes(headnum),
        ))

    texture_path: Path | None = None
    if args.bake_texture and aligned_count:
        texture_path = folders["postprocess"] / "facebuilder_texture_bake.png"
        result["texture_bake"] = _safe_call(
            "bake_texture",
            lambda: _bake_texture(headnum, texture_path),
        )

    texture_ok = (
        result["texture_bake"] is not None
        and result["texture_bake"].get("ok")
        and isinstance(result["texture_bake"].get("value"), dict)
        and result["texture_bake"]["value"].get("ok")
    )
    cleanup_texture_path: Path | None = None
    if texture_ok and texture_path is not None:
        cleanup_texture_path = folders["postprocess"] / "facebuilder_texture_bald_cleanup.png"
        cleanup_report_path = folders["postprocess"] / "bald_texture_cleanup_report.json"
        result["texture_cleanup"] = _safe_call(
            "cleanup_baked_texture",
            lambda: _cleanup_baked_texture(texture_path, cleanup_texture_path, cleanup_report_path),
        )

    cleanup_ok = (
        result.get("texture_cleanup") is not None
        and result["texture_cleanup"].get("ok")
        and isinstance(result["texture_cleanup"].get("value"), dict)
        and result["texture_cleanup"]["value"].get("ok")
    )
    material_texture_path = cleanup_texture_path if cleanup_ok else texture_path

    head_obj = _head_object(settings, headnum)
    result["postprocess"] = _safe_call(
        "apply_hair_app_material_and_prep",
        lambda: _apply_hair_app_material(head_obj, material_texture_path if texture_ok else None, output_dir),
    )

    if head_obj is not None and args.export_obj:
        obj_path = folders["exports"] / f"{manifest.get('person')}_{manifest.get('version')}_bald_head.obj"
        result["exports"]["obj"] = _safe_call("export_obj", lambda: _export_obj(head_obj, obj_path))

    if head_obj is not None and args.export_glb:
        glb_path = folders["glb"] / f"{manifest.get('person')}_{manifest.get('version')}_bald_head.glb"
        result["exports"]["glb"] = _safe_call("export_glb", lambda: _export_glb(head_obj, glb_path))

    if head_obj is not None and args.render_review:
        result["review"] = _safe_call("render_review", lambda: _render_review(head_obj, output_dir))

    if args.save_blend:
        blend_path = folders["scene"] / f"{manifest.get('person')}_{manifest.get('version')}_facebuilder.blend"
        result["steps"].append(_safe_call(
            "save_blend",
            lambda: str(bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))),
        ))
        result["saved_blend"] = _safe_path(blend_path)

    glb_value = result["exports"].get("glb", {}).get("value", {})
    texture_enabled_count = sum(
        1
        for camera in result.get("head_after_align", {}).get("cameras", [])
        if camera.get("use_in_tex_baking")
    )
    result["summary"] = {
        "items_count": len(manifest.get("items", [])),
        "aligned_count": aligned_count,
        "failed_count": failed_count,
        "texture_enabled_count": texture_enabled_count,
        "texture_ok": bool(texture_ok),
        "texture_cleanup_ok": bool(cleanup_ok),
        "obj_ok": bool(result["exports"].get("obj", {}).get("ok")),
        "glb_ok": bool(isinstance(glb_value, dict) and glb_value.get("ok")),
        "review_ok": bool(result.get("review", {}).get("ok")),
    }
    result["ok"] = bool(aligned_count > 0)

    _write_json(output_dir / "run_manifest.json", result)
    _write_json(folders["alignment"] / "alignment_report.json", {
        "summary": result["summary"],
        "alignment": result["alignment"],
        "head_after_align": result.get("head_after_align"),
    })
    print(f"FACEBUILDER_BATCH_OK {result['ok']}")
    print(f"FACEBUILDER_BATCH_JSON {output_dir / 'run_manifest.json'}")
    return 0 if result["ok"] else 5


if __name__ == "__main__":
    raise SystemExit(main())
