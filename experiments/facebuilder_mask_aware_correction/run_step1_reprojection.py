"""Run Step 1 FaceBuilder reprojection smoke tests.

The runner opens existing FaceBuilder .blend files with Blender, asks Blender
to project the solved head mesh onto each FaceBuilder camera image, and draws a
private review sheet.

Generated images stay in Drive/local output and must not be committed.
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

from PIL import Image, ImageDraw, ImageFont, ImageOps


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
    parser.add_argument("--max-edges-per-camera", type=int, default=7000)
    return parser.parse_args(argv)


def _safe_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _find_one(pattern_root: Path, pattern: str) -> Path:
    matches = sorted(pattern_root.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No match under {pattern_root}: {pattern}")
    return matches[0]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "malgun.ttf",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf",
    ]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except Exception:
                pass
    return ImageFont.load_default()


def _load_image(path_text: str) -> Image.Image:
    path = Path(path_text)
    if not path.exists():
        path = Path(path_text.replace("/", "\\"))
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def _quality_label(camera: dict[str, Any]) -> tuple[str, tuple[int, int, int]]:
    if not camera.get("ok"):
        return "projection failed", (255, 80, 80)
    if not camera.get("has_pins"):
        return "no pins", (255, 80, 80)
    inside = float(camera.get("vertices_inside_image_ratio") or 0.0)
    coverage = float(camera.get("projected_bbox_coverage_ratio") or 0.0)
    if inside < 0.15 or coverage < 0.08:
        return "suspicious", (255, 170, 60)
    return "projected", (80, 220, 120)


def _draw_overlay(camera: dict[str, Any], output_path: Path) -> dict[str, Any]:
    image_path = camera.get("image_path")
    if not image_path:
        return {"ok": False, "reason": "missing_image_path", "output": _safe_path(output_path)}

    base = _load_image(image_path)
    width, height = base.size
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    label, color = _quality_label(camera)
    line_color = color + (130,)
    for edge in camera.get("draw_edges") or []:
        if len(edge) != 4:
            continue
        draw.line(tuple(edge), fill=line_color, width=1)

    bbox = camera.get("projected_bbox")
    if bbox:
        draw.rectangle(tuple(bbox), outline=(255, 230, 40, 210), width=3)

    composed = Image.alpha_composite(base.convert("RGBA"), overlay)
    label_band = Image.new("RGBA", (width, 46), (24, 24, 24, 230))
    label_draw = ImageDraw.Draw(label_band)
    font = _font(max(14, int(width * 0.032)))
    small_font = _font(max(11, int(width * 0.024)))
    title = (
        f"cam {camera.get('camera_index'):02d} | key {camera.get('keyframe')} | "
        f"pins {camera.get('pins_count')} | tex {camera.get('use_in_tex_baking')}"
    )
    metrics = (
        f"{label} | inside {float(camera.get('vertices_inside_image_ratio') or 0.0):.2f} | "
        f"bbox {float(camera.get('projected_bbox_coverage_ratio') or 0.0):.2f}"
    )
    label_draw.text((8, 4), title, fill=(245, 245, 245, 255), font=font)
    label_draw.text((8, 26), metrics, fill=color + (255,), font=small_font)
    final = Image.new("RGBA", (width, height + 46), (0, 0, 0, 255))
    final.alpha_composite(label_band, (0, 0))
    final.alpha_composite(composed, (0, 46))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.convert("RGB").save(output_path, quality=95)
    return {
        "ok": True,
        "output": _safe_path(output_path),
        "source_image": image_path,
        "label": label,
        "draw_edges": len(camera.get("draw_edges") or []),
        "inside_ratio": float(camera.get("vertices_inside_image_ratio") or 0.0),
        "coverage_ratio": float(camera.get("projected_bbox_coverage_ratio") or 0.0),
    }


def _make_sheet(person: str, overlays: list[dict[str, Any]], sheet_path: Path) -> None:
    ok_overlays = [item for item in overlays if item.get("ok")]
    if not ok_overlays:
        return

    thumb_w = 260
    header_h = 74
    gap = 12
    columns = 4
    rows = (len(ok_overlays) + columns - 1) // columns

    thumbs = []
    for item in ok_overlays:
        image = Image.open(Path(str(item["output"]).replace("/", "\\"))).convert("RGB")
        ratio = thumb_w / image.width
        thumb_h = max(1, int(round(image.height * ratio)))
        thumbs.append(image.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS))

    tile_h = max(image.height for image in thumbs)
    sheet_w = columns * thumb_w + (columns + 1) * gap
    sheet_h = header_h + rows * tile_h + (rows + 1) * gap
    sheet = Image.new("RGB", (sheet_w, sheet_h), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    draw.text((16, 12), f"{person} Step 1 FaceBuilder reprojection smoke test", fill=(245, 245, 245), font=_font(24))
    draw.text(
        (16, 44),
        "3D FaceBuilder mesh wireframe projected back onto each camera image. Private review sheet; do not commit.",
        fill=(180, 180, 180),
        font=_font(14),
    )

    for index, thumb in enumerate(thumbs):
        row = index // columns
        col = index % columns
        x = gap + col * (thumb_w + gap)
        y = header_h + gap + row * (tile_h + gap)
        sheet.paste(thumb, (x, y))

    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(sheet_path, quality=95)


def _write_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# FaceBuilder Mask-Aware Correction Step 1 Reprojection",
        "",
        f"- Created: {summary['created_at']}",
        f"- Source version: `{summary['source_version']}`",
        f"- Output root: `{summary['output_dir']}`",
        "",
    ]
    for person in summary["people"]:
        lines += [
            f"## {person['person']}",
            "",
            f"- Cameras: {person['counts']['cameras']}",
            f"- Overlay images: {person['counts']['overlays']}",
            f"- No-pin cameras: {person['counts']['no_pin_cameras']}",
            f"- Suspicious projections: {person['counts']['suspicious_projections']}",
            f"- Review sheet: `{person['paths']['review_sheet']}`",
            f"- Projection JSON: `{person['paths']['projection_json']}`",
            "",
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _summarize_person(person: str, projection_json: Path, overlays: list[dict[str, Any]], person_dir: Path, output_dir: Path) -> dict[str, Any]:
    projection = _read_json(projection_json)
    cameras = projection.get("cameras") or []
    no_pin = [camera for camera in cameras if not camera.get("has_pins")]
    suspicious = []
    for camera in cameras:
        label, _ = _quality_label(camera)
        if label in {"projection failed", "no pins", "suspicious"}:
            suspicious.append({"camera_index": camera.get("camera_index"), "label": label, "image": camera.get("image_name")})

    return {
        "person": person,
        "counts": {
            "cameras": len(cameras),
            "overlays": sum(1 for item in overlays if item.get("ok")),
            "no_pin_cameras": len(no_pin),
            "suspicious_projections": len(suspicious),
        },
        "suspicious": suspicious,
        "paths": {
            "source_person_dir": _safe_path(person_dir),
            "projection_json": _safe_path(projection_json),
            "review_sheet": _safe_path(output_dir / "review_sheet.png"),
            "overlays_dir": _safe_path(output_dir / "overlays"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    people = args.person or list(PERSONS)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = args.output_dir or (args.drive_root / "output" / "facebuilder_mask_aware_step1" / stamp)
    source_root = args.drive_root / "output" / args.source_version
    blender_script = REPO_ROOT / "experiments" / "facebuilder_mask_aware_correction" / "blender_step1_project.py"

    summary: dict[str, Any] = {
        "schema_version": "facebuilder_mask_aware_step1_runner_v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": _safe_path(REPO_ROOT),
        "drive_root": _safe_path(args.drive_root),
        "source_version": args.source_version,
        "output_dir": _safe_path(output_root),
        "people": [],
    }

    for person in people:
        person_source_dir = source_root / person
        blend = _find_one(person_source_dir / "03_facebuilder_scene", "*.blend")
        person_output = output_root / person
        projection_json = person_output / "projection" / "camera_projection_wireframe.json"
        blender_log = person_output / "logs" / "blender_step1_stdout_stderr.txt"
        blender_log.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(args.blender_exe),
            "--background",
            str(blend),
            "--python",
            str(blender_script),
            "--",
            "--output",
            str(projection_json),
            "--headnum",
            str(args.headnum),
            "--max-edges-per-camera",
            str(args.max_edges_per_camera),
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
                "error": f"Blender projection failed with return code {proc.returncode}",
                "paths": {"blend": _safe_path(blend), "blender_log": _safe_path(blender_log)},
            })
            continue

        projection = _read_json(projection_json)
        overlays: list[dict[str, Any]] = []
        overlays_dir = person_output / "overlays"
        for camera in projection.get("cameras") or []:
            output_path = overlays_dir / f"camera_{int(camera.get('camera_index', 0)):03d}_overlay.jpg"
            overlays.append(_draw_overlay(camera, output_path))

        review_sheet = person_output / "review_sheet.png"
        _make_sheet(person, overlays, review_sheet)
        person_summary = _summarize_person(person, projection_json, overlays, person_source_dir, person_output)
        person_summary["paths"]["blend"] = _safe_path(blend)
        person_summary["paths"]["blender_log"] = _safe_path(blender_log)
        summary["people"].append(person_summary)

    summary_json = output_root / "step1_summary.json"
    report_md = output_root / "step1_report.md"
    _write_json(summary_json, summary)
    _write_report(report_md, summary)
    print(json.dumps({
        "summary_json": _safe_path(summary_json),
        "report_md": _safe_path(report_md),
        "people": [
            {
                "person": item.get("person"),
                "counts": item.get("counts"),
                "error": item.get("error"),
                "review_sheet": (item.get("paths") or {}).get("review_sheet"),
            }
            for item in summary["people"]
        ],
    }, indent=2, ensure_ascii=True))

    failed = any(item.get("error") for item in summary["people"])
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
