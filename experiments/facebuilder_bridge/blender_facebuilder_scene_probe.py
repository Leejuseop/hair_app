"""Probe a FaceBuilder Blender scene from headless Blender.

Run with an existing .blend file:

    blender --background C:/path/to/file.blend --python blender_facebuilder_scene_probe.py -- --try-align-unpinned

The script writes diagnostics only. It does not save the .blend unless future
code explicitly adds that behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any

import bpy


def _parse_args(argv: list[str]) -> argparse.Namespace:
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("private_outputs/facebuilder_bridge/scene_probe.json"),
    )
    parser.add_argument("--headnum", type=int, default=0)
    parser.add_argument("--target-camnum", type=int, default=None)
    parser.add_argument("--try-align-unpinned", action="store_true")
    parser.add_argument("--max-align-attempts", type=int, default=1)
    parser.add_argument("--bake-texture", action="store_true")
    parser.add_argument("--texture-name", default="HairAppFaceBuilderSmokeTexture")
    parser.add_argument("--texture-output", type=Path, default=None)
    return parser.parse_args(argv)


def _safe(label: str, func: Any) -> dict[str, Any]:
    try:
        value = func()
    except Exception as exc:  # noqa: BLE001 - diagnostic script.
        return {
            "label": label,
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=6),
        }
    return {"label": label, "ok": True, "value": value}


def _image_path(image: Any) -> str | None:
    if image is None or not image.filepath:
        return None
    return bpy.path.abspath(image.filepath).replace("\\", "/")


def _camera_info(camera: Any, index: int) -> dict[str, Any]:
    image = camera.cam_image
    return {
        "index": index,
        "keyframe": camera.get_keyframe(),
        "camobj": camera.camobj.name if camera.camobj else None,
        "image_name": image.name if image else None,
        "image_size": list(image.size) if image else None,
        "image_filepath": _image_path(image),
        "pins_count_prop": camera.pins_count,
        "has_pins": camera.has_pins(),
        "use_in_tex_baking": camera.use_in_tex_baking,
        "focal": camera.focal,
        "auto_focal_estimation": camera.auto_focal_estimation,
    }


def _scene_info(settings: Any) -> dict[str, Any]:
    heads = []
    for head_index, head in enumerate(settings.heads):
        cameras = [
            _camera_info(camera, camera_index)
            for camera_index, camera in enumerate(head.cameras)
        ]
        heads.append(
            {
                "index": head_index,
                "headobj": head.headobj.name if head.headobj else None,
                "cameras_count": len(head.cameras),
                "has_cameras": head.has_cameras(),
                "has_pins": head.has_pins(),
                "pinned_cameras_count": sum(1 for camera in head.cameras if camera.has_pins()),
                "cameras": cameras,
            }
        )
    return {
        "blend_file": bpy.data.filepath,
        "heads_count": len(settings.heads),
        "current_headnum": settings.current_headnum,
        "heads": heads,
    }


def _len_or_none(value: Any) -> int | None:
    try:
        return len(value)
    except Exception:
        return None


def _attempt_align(headnum: int, camnum: int) -> dict[str, Any]:
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
        return {"ok": False, "reason": "camera_not_found", "headnum": headnum, "camnum": camnum}

    image = load_rgba(camera)
    if image is None:
        return {"ok": False, "reason": "image_load_failed", "camnum": camnum}

    FBLoader.load_model(headnum)
    fb = FBLoader.get_builder()
    fb.set_use_emotions(head.should_use_emotions())
    configure_focal_mode_and_fixes(fb, head)

    keyframe = camera.get_keyframe()
    before_pins = fb.pins_count(keyframe) if fb.is_key_at(keyframe) else 0
    pixel_aspect_ratio = fb.pixel_aspect_ratio(keyframe)
    faces = fb.detect_faces(image, pixel_aspect_ratio)
    faces_count = _len_or_none(faces)

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
        "saved_blend": False,
    }


def _bake_texture(headnum: int, texture_name: str, texture_output: Path | None) -> dict[str, Any]:
    from bl_ext.user_default.keentools.utils.materials import bake_tex

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

    if image is not None and texture_output is not None:
        texture_output.parent.mkdir(parents=True, exist_ok=True)
        image.filepath_raw = str(texture_output)
        image.file_format = "PNG"
        image.save()
        result["saved_texture"] = str(texture_output).replace("\\", "/")

    return result


def main() -> int:
    args = _parse_args(sys.argv)
    from bl_ext.user_default.keentools.addon_config import fb_settings

    settings = fb_settings()
    result: dict[str, Any] = {
        "ok": True,
        "blender": {
            "version": bpy.app.version_string,
            "background": bpy.app.background,
        },
        "scene": _scene_info(settings),
        "align_attempts": [],
        "texture_bake": None,
    }

    if args.try_align_unpinned:
        head = settings.get_head(args.headnum)
        if head is None:
            result["ok"] = False
            result["align_attempts"].append(
                {"ok": False, "reason": "head_not_found", "headnum": args.headnum}
            )
        else:
            if args.target_camnum is None:
                candidates = [
                    index for index, camera in enumerate(head.cameras) if not camera.has_pins()
                ]
            else:
                candidates = [args.target_camnum]

            for camnum in candidates[: args.max_align_attempts]:
                probe = _safe(
                    f"align_head_{args.headnum}_camera_{camnum}",
                    lambda camnum=camnum: _attempt_align(args.headnum, camnum),
                )
                result["align_attempts"].append(probe)
                value = probe.get("value") if probe.get("ok") else None
                if not probe.get("ok") or not (isinstance(value, dict) and value.get("ok")):
                    result["ok"] = False

            result["scene_after_align_attempts"] = _scene_info(settings)

    if args.bake_texture:
        texture_probe = _safe(
            f"bake_texture_head_{args.headnum}",
            lambda: _bake_texture(args.headnum, args.texture_name, args.texture_output),
        )
        result["texture_bake"] = texture_probe
        value = texture_probe.get("value") if texture_probe.get("ok") else None
        if not texture_probe.get("ok") or not (isinstance(value, dict) and value.get("ok")):
            result["ok"] = False

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"FACEBUILDER_SCENE_PROBE_OK {result['ok']}")
    print(f"FACEBUILDER_SCENE_PROBE_JSON {args.output}")
    return 0 if result["ok"] else 5


if __name__ == "__main__":
    raise SystemExit(main())
