"""Create a minimal FaceBuilder scene from a photo folder in headless Blender.

This is an automation feasibility test, not a production pipeline. It starts
from an empty Blender session, creates a FaceBuilder head, adds 1-N photos as
FaceBuilder cameras, tries code-only auto-align, optionally bakes a texture, and
writes a private diagnostic bundle.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any

import bpy


SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []

    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--person", default="person")
    parser.add_argument("--max-images", type=int, default=2)
    parser.add_argument("--bake-texture", action="store_true")
    parser.add_argument("--save-blend", action="store_true")
    return parser.parse_args(argv)


def _safe_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")


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


def _list_images(input_dir: Path, max_images: int) -> list[Path]:
    images = [
        path
        for path in sorted(input_dir.iterdir(), key=lambda p: p.name.lower())
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
    ]
    return images[:max_images]


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
        "cameras": [
            _camera_info(camera, index)
            for index, camera in enumerate(head.cameras)
        ],
    }


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
    return {
        "ok": bool(pose_ok and after_solve_pins > 0),
        "reason": "aligned" if pose_ok and after_solve_pins > 0 else "detect_face_pose_failed",
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

    texture_name = f"HairAppAutoSceneTexture_{headnum}"
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


def main() -> int:
    args = _parse_args(sys.argv)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "ok": False,
        "person": args.person,
        "input_dir": _safe_path(args.input_dir),
        "output_dir": _safe_path(output_dir),
        "blender": {
            "version": bpy.app.version_string,
            "background": bpy.app.background,
        },
        "selected_images": [],
        "steps": [],
        "align_results": [],
        "texture_bake": None,
        "saved_blend": None,
    }

    images = _list_images(args.input_dir, args.max_images)
    result["selected_images"] = [_safe_path(path) for path in images]
    if not images:
        result["steps"].append({"label": "list_images", "ok": False, "reason": "no_images_found"})
        _write_json(output_dir / "result.json", result)
        print(f"FACEBUILDER_AUTO_SCENE_JSON {output_dir / 'result.json'}")
        return 2

    from bl_ext.user_default.keentools.addon_config import fb_settings
    from bl_ext.user_default.keentools.facebuilder.fbloader import FBLoader

    add_head = _safe_call("add_facebuilder_head", lambda: str(bpy.ops.keentools_fb.add_head()))
    result["steps"].append(add_head)
    if not add_head["ok"] or "FINISHED" not in str(add_head.get("value")):
        _write_json(output_dir / "result.json", result)
        print(f"FACEBUILDER_AUTO_SCENE_JSON {output_dir / 'result.json'}")
        return 3

    settings = fb_settings()
    headnum = settings.get_last_headnum()
    settings.current_headnum = headnum

    for image_path in images:
        camera_step = _safe_call(
            f"add_camera_{image_path.name}",
            lambda image_path=image_path: _camera_info(
                FBLoader.add_new_camera_with_image(headnum, str(image_path)),
                len(settings.get_head(headnum).cameras) - 1,
            ),
        )
        result["steps"].append(camera_step)

    head = settings.get_head(headnum)
    if head is not None:
        for camnum in range(len(head.cameras)):
            align_step = _safe_call(
                f"align_camera_{camnum}",
                lambda camnum=camnum: _align_camera(headnum, camnum),
            )
            result["align_results"].append(align_step)

    result["head_after_align"] = _head_summary(settings, headnum)

    successful_aligns = [
        item
        for item in result["align_results"]
        if item.get("ok") and isinstance(item.get("value"), dict) and item["value"].get("ok")
    ]

    if successful_aligns:
        save_state_step = _safe_call(
            "save_facebuilder_state_after_align",
            lambda: FBLoader.save_fb_serial_and_image_pathes(headnum),
        )
        result["steps"].append(save_state_step)

    if args.bake_texture and successful_aligns:
        texture_output = output_dir / "texture_bake.png"
        result["texture_bake"] = _safe_call(
            "bake_texture",
            lambda: _bake_texture(headnum, texture_output),
        )

    if args.save_blend:
        blend_output = output_dir / f"{args.person}_auto_scene_v0.blend"
        save_step = _safe_call(
            "save_blend",
            lambda: str(bpy.ops.wm.save_as_mainfile(filepath=str(blend_output))),
        )
        result["steps"].append(save_step)
        if save_step.get("ok"):
            result["saved_blend"] = _safe_path(blend_output)

    texture_ok = (
        not args.bake_texture
        or (
            result["texture_bake"] is not None
            and result["texture_bake"].get("ok")
            and isinstance(result["texture_bake"].get("value"), dict)
            and result["texture_bake"]["value"].get("ok")
        )
    )
    result["ok"] = bool(successful_aligns and texture_ok)

    _write_json(output_dir / "result.json", result)
    print(f"FACEBUILDER_AUTO_SCENE_OK {result['ok']}")
    print(f"FACEBUILDER_AUTO_SCENE_JSON {output_dir / 'result.json'}")
    return 0 if result["ok"] else 5


if __name__ == "__main__":
    raise SystemExit(main())
