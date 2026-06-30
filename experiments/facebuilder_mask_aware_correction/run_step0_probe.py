"""Run Step 0 probes for existing FaceBuilder outputs.

This runner does not rebuild FaceBuilder scenes. It opens the existing .blend
files in background Blender and verifies whether the mask-aware correction
pipeline can access mesh, UV, texture, camera, projection, and per-frame builder
values.

All generated outputs are private diagnostics and should stay in Drive/local
output, not in Git.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")
DEFAULT_DRIVE_ROOT = Path(os.environ.get("HAIR_APP_DRIVE_ROOT", "G:/\ub0b4 \ub4dc\ub77c\uc774\ube0c/hair_app"))
PERSONS = ("juseop", "eunchae")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drive-root", type=Path, default=DEFAULT_DRIVE_ROOT)
    parser.add_argument("--blender-exe", type=Path, default=DEFAULT_BLENDER_EXE)
    parser.add_argument("--source-version", default="facebuilder_semantic_v2")
    parser.add_argument("--person", action="append", choices=PERSONS)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--headnum", type=int, default=0)
    return parser.parse_args(argv)


def _safe_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _find_one(pattern_root: Path, pattern: str) -> Path:
    matches = sorted(pattern_root.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No match under {pattern_root}: {pattern}")
    if len(matches) > 1:
        # Keep deterministic behavior and report the chosen file in the summary.
        return matches[0]
    return matches[0]


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _path_exists(path_text: str | None) -> bool:
    if not path_text:
        return False
    return Path(path_text.replace("/", "\\")).exists()


def _summarize_manifest(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    data = _read_json(path)
    rows = data.get("rows") or data.get("images") or data.get("items") or []
    summary: dict[str, Any] = {
        "path": _safe_path(path),
        "top_level_keys": sorted(data.keys()),
        "row_count": len(rows) if isinstance(rows, list) else None,
    }
    if isinstance(rows, list):
        summary["texture_enabled_count"] = sum(1 for row in rows if row.get("allow_texture_bake", row.get("texture_enabled", True)))
        summary["sample_rows"] = rows[:3]
    return summary


def _summarize_probe(person: str, person_dir: Path, probe_path: Path, npz_path: Path) -> dict[str, Any]:
    probe = _read_json(probe_path)
    head = (probe.get("heads") or [{}])[0]
    mesh = head.get("mesh") or {}
    cameras = head.get("cameras") or []
    per_camera = head.get("per_camera_builder_values") or []
    scene_images = probe.get("scene_images") or []
    raw_texture_path = person_dir / "05_postprocess" / "facebuilder_texture_bake.png"
    obj_path = _first_existing(list((person_dir / "04_exports").glob("*.obj")))
    glb_path = _first_existing(list((person_dir / "06_glb").glob("*.glb")))

    projection_count = sum(1 for camera in cameras if camera.get("projection_matrix_ok"))
    image_path_count = sum(1 for camera in cameras if ((camera.get("image") or {}).get("filepath")))
    existing_image_count = sum(1 for camera in cameras if _path_exists((camera.get("image") or {}).get("filepath")))
    model_count = sum(1 for item in per_camera if ((item.get("model_mat") or {}).get("matrix") is not None))
    geo_count = sum(
        1
        for item in per_camera
        if (((item.get("applied_args_model_at") or {}).get("summary") or {}).get("array_usable_as_numeric_geometry"))
    )

    material_image_count = 0
    for material in mesh.get("material_texture_refs") or []:
        material_image_count += len(material.get("images") or [])

    checklist = {
        "blend_opened": bool(probe.get("ok")),
        "mesh_available": bool(mesh.get("available")),
        "uv_available": int(mesh.get("uv_layer_count") or 0) > 0 and bool(mesh.get("active_uv")),
        "obj_export_exists": obj_path is not None and obj_path.exists(),
        "glb_export_exists": glb_path is not None and glb_path.exists(),
        "raw_texture_png_exists": raw_texture_path.exists(),
        "scene_or_material_texture_refs": bool(scene_images or material_image_count),
        "camera_image_paths_available": image_path_count == len(cameras) and len(cameras) > 0,
        "camera_image_files_exist": existing_image_count == len(cameras) and len(cameras) > 0,
        "projection_matrices_available": projection_count == len(cameras) and len(cameras) > 0,
        "model_matrices_available": model_count == len(cameras) and len(cameras) > 0,
        "per_camera_geo_numeric_arrays_available": geo_count == len(cameras) and len(cameras) > 0,
        "texture_builder_eligible_frames_available": int(head.get("texture_builder_eligible_cameras_count") or 0) > 0,
        "npz_written": npz_path.exists(),
    }

    can_start_step1 = all(
        checklist[key]
        for key in (
            "blend_opened",
            "mesh_available",
            "uv_available",
            "camera_image_paths_available",
            "camera_image_files_exist",
            "projection_matrices_available",
            "model_matrices_available",
            "texture_builder_eligible_frames_available",
            "npz_written",
        )
    )

    return {
        "person": person,
        "can_start_step1_reprojection": can_start_step1,
        "checklist": checklist,
        "counts": {
            "cameras": len(cameras),
            "pinned_cameras": int(head.get("pinned_cameras_count") or 0),
            "texture_enabled_cameras": int(head.get("texture_enabled_cameras_count") or 0),
            "texture_builder_eligible_cameras": int(head.get("texture_builder_eligible_cameras_count") or 0),
            "projection_matrices": projection_count,
            "model_matrices": model_count,
            "geo_numeric_arrays": geo_count,
            "camera_image_paths": image_path_count,
            "camera_image_files_existing": existing_image_count,
            "scene_images": len(scene_images),
            "material_image_refs": material_image_count,
        },
        "mesh": {
            "object_name": mesh.get("object_name"),
            "vertex_count": mesh.get("vertex_count"),
            "polygon_count": mesh.get("polygon_count"),
            "loop_count": mesh.get("loop_count"),
            "uv_layer_count": mesh.get("uv_layer_count"),
            "active_uv": mesh.get("active_uv"),
        },
        "paths": {
            "person_dir": _safe_path(person_dir),
            "probe_json": _safe_path(probe_path),
            "probe_npz": _safe_path(npz_path),
            "obj": _safe_path(obj_path),
            "glb": _safe_path(glb_path),
            "raw_texture_png": _safe_path(raw_texture_path),
        },
    }


def _write_report(path: Path, summary: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# FaceBuilder Mask-Aware Correction Step 0 Probe")
    lines.append("")
    lines.append(f"- Created: {summary['created_at']}")
    lines.append(f"- Source version: `{summary['source_version']}`")
    lines.append(f"- Output root: `{summary['output_dir']}`")
    lines.append("")
    for person_result in summary["people"]:
        lines.append(f"## {person_result['person']}")
        lines.append("")
        status = "PASS" if person_result["can_start_step1_reprojection"] else "BLOCKED"
        lines.append(f"- Step 1 reprojection readiness: **{status}**")
        lines.append("- Counts:")
        for key, value in person_result["counts"].items():
            lines.append(f"  - {key}: {value}")
        lines.append("- Mesh:")
        for key, value in person_result["mesh"].items():
            lines.append(f"  - {key}: {value}")
        lines.append("- Checklist:")
        for key, value in person_result["checklist"].items():
            mark = "ok" if value else "missing"
            lines.append(f"  - {mark}: {key}")
        lines.append("- Private outputs:")
        for key, value in person_result["paths"].items():
            lines.append(f"  - {key}: `{value}`")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    people = args.person or list(PERSONS)
    output_dir = args.output_dir
    if output_dir is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = args.drive_root / "output" / "facebuilder_mask_aware_step0" / stamp

    blender_script = REPO_ROOT / "experiments" / "facebuilder_mask_aware_correction" / "blender_step0_extract.py"
    source_root = args.drive_root / "output" / args.source_version
    summary: dict[str, Any] = {
        "schema_version": "facebuilder_mask_aware_step0_runner_v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": _safe_path(REPO_ROOT),
        "drive_root": _safe_path(args.drive_root),
        "source_version": args.source_version,
        "source_root": _safe_path(source_root),
        "output_dir": _safe_path(output_dir),
        "blender_exe": _safe_path(args.blender_exe),
        "people": [],
    }

    for person in people:
        person_dir = source_root / person
        blend = _find_one(person_dir / "03_facebuilder_scene", "*.blend")
        probe_dir = output_dir / person
        probe_json = probe_dir / "step0_facebuilder_probe.json"
        probe_npz = probe_dir / "step0_facebuilder_arrays.npz"
        blender_log = probe_dir / "blender_step0_stdout_stderr.txt"
        probe_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(args.blender_exe),
            "--background",
            str(blend),
            "--python",
            str(blender_script),
            "--",
            "--output",
            str(probe_json),
            "--npz",
            str(probe_npz),
            "--headnum",
            str(args.headnum),
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        blender_log.write_text(
            "COMMAND:\n"
            + " ".join(cmd)
            + "\n\nSTDOUT:\n"
            + (proc.stdout or "")
            + "\n\nSTDERR:\n"
            + (proc.stderr or ""),
            encoding="utf-8",
        )
        if proc.returncode != 0:
            summary["people"].append({
                "person": person,
                "can_start_step1_reprojection": False,
                "error": f"Blender probe failed with return code {proc.returncode}",
                "paths": {
                    "blend": _safe_path(blend),
                    "blender_log": _safe_path(blender_log),
                    "probe_json": _safe_path(probe_json),
                    "probe_npz": _safe_path(probe_npz),
                },
            })
            continue

        person_summary = _summarize_probe(person, person_dir, probe_json, probe_npz)
        person_summary["paths"]["blend"] = _safe_path(blend)
        person_summary["paths"]["blender_log"] = _safe_path(blender_log)
        person_summary["input_manifest"] = _summarize_manifest(person_dir / "01_input_manifest" / "input_manifest.json")
        person_summary["run_manifest"] = _summarize_manifest(person_dir / "run_manifest.json")
        summary["people"].append(person_summary)

    summary_json = output_dir / "step0_summary.json"
    report_md = output_dir / "step0_report.md"
    _write_json(summary_json, summary)
    _write_report(report_md, summary)

    print(json.dumps({
        "summary_json": _safe_path(summary_json),
        "report_md": _safe_path(report_md),
        "people": [
            {
                "person": item.get("person"),
                "can_start_step1_reprojection": item.get("can_start_step1_reprojection"),
                "counts": item.get("counts"),
                "error": item.get("error"),
            }
            for item in summary["people"]
        ],
    }, indent=2, ensure_ascii=True))
    return 0 if all(item.get("can_start_step1_reprojection") for item in summary["people"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
