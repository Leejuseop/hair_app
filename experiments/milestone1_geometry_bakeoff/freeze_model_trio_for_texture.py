"""Freeze the three mesh candidates used by the next texture-baking step.

This helper is intended to run in Colab against private Drive artifacts. It
copies only private runtime outputs into the private run folder; do not commit
the generated folder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


ACTOR_SUFFIX = "_nV1_noPho_noMICA_uv2000.0_n2000.0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_ply_header_counts(path: Path) -> dict[str, int | None]:
    counts: dict[str, int | None] = {"vertices": None, "faces": None}
    with path.open("rb") as file:
        for raw_line in file:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line.startswith("element vertex "):
                counts["vertices"] = int(line.split()[-1])
            elif line.startswith("element face "):
                counts["faces"] = int(line.split()[-1])
            elif line == "end_header":
                break
    return counts


def as_array(value: Any) -> np.ndarray:
    if hasattr(value, "r"):
        value = value.r
    return np.asarray(value)


def find_actor_dir(root: Path) -> Path:
    candidates = []
    if root.exists():
        for path in root.glob(f"*{ACTOR_SUFFIX}"):
            if not path.is_dir():
                continue
            frames = sorted((path / "checkpoint").glob("*.frame"))
            canonical = path / "mesh" / "canonical.ply"
            if frames and canonical.exists():
                candidates.append((len(frames), path.name, path))

    assert candidates, f"No complete actor directory found under {root}"
    candidates.sort()
    return candidates[-1][2]


def extract_raw_flame_template(output_path: Path, search_roots: list[Path]) -> Path:
    candidates: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        candidates.extend(root.rglob("generic_model.pkl"))
        candidates.extend(root.rglob("FLAME*.npz"))
        candidates.extend(root.rglob("*flame*.npz"))

    candidates = sorted(
        set(candidates),
        key=lambda p: (
            0 if p.name == "generic_model.pkl" else 1,
            0 if "FLAME2020" in str(p) else 1,
            len(str(p)),
        ),
    )
    assert candidates, "FLAME model file not found"

    last_error = None
    for model_path in candidates:
        try:
            if model_path.suffix == ".pkl":
                with model_path.open("rb") as file:
                    data = pickle.load(file, encoding="latin1")
            else:
                data = np.load(model_path, allow_pickle=True)

            keys = set(data.keys())
            face_key = "f" if "f" in keys else ("faces" if "faces" in keys else None)
            if "v_template" not in keys or face_key is None:
                continue

            vertices = as_array(data["v_template"]).astype(np.float32)
            faces = as_array(data[face_key]).astype(np.int64)

            if vertices.ndim == 3:
                vertices = vertices[0]
            if faces.ndim == 3:
                faces = faces[0]

            assert vertices.ndim == 2 and vertices.shape[1] == 3, vertices.shape
            assert faces.ndim == 2 and faces.shape[1] == 3, faces.shape

            with output_path.open("w", encoding="utf-8") as file:
                file.write("ply\n")
                file.write("format ascii 1.0\n")
                file.write(f"element vertex {len(vertices)}\n")
                file.write("property float x\n")
                file.write("property float y\n")
                file.write("property float z\n")
                file.write(f"element face {len(faces)}\n")
                file.write("property list uchar int vertex_indices\n")
                file.write("end_header\n")

                for x, y, z in vertices:
                    file.write(f"{x} {y} {z}\n")

                for a, b, c in faces:
                    file.write(f"3 {a} {b} {c}\n")

            return model_path
        except Exception as error:  # pragma: no cover - diagnostic only
            last_error = repr(error)

    raise RuntimeError(f"FLAME template extraction failed. last_error={last_error}")


def copy_mesh(source: Path, destination: Path) -> None:
    assert source.exists(), source
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument(
        "--output-name",
        default="model_trio_for_texture",
        help="Private subfolder created inside run-dir.",
    )
    parser.add_argument(
        "--code-base",
        default="/content/pixel3dmm",
        type=Path,
        help="Pixel3DMM checkout used to find FLAME assets.",
    )
    args = parser.parse_args()

    run_dir = args.run_dir
    out_dir = run_dir / args.output_name
    assert run_dir.exists(), run_dir

    no_mica_actor_dir = find_actor_dir(run_dir / "tracking_full")
    mean_shape_actor_dir = find_actor_dir(run_dir / "tracking_mean_shape_19_full")

    personal_source = run_dir / "meshes" / "canonical.ply"
    if not personal_source.exists():
        personal_source = no_mica_actor_dir / "mesh" / "canonical.ply"
    mean_source = mean_shape_actor_dir / "mesh" / "canonical.ply"

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_mesh = out_dir / "raw_flame_template.ply"
    raw_source = extract_raw_flame_template(
        raw_mesh,
        [args.code_base, Path("/content")],
    )

    mean_mesh = out_dir / "mean_flame_fitted_control_canonical.ply"
    personal_mesh = out_dir / "personal_no_mica_canonical.ply"
    copy_mesh(mean_source, mean_mesh)
    copy_mesh(personal_source, personal_mesh)

    meshes = {
        "raw_flame_template": {
            "role": "No photo values. FLAME v_template only.",
            "path": str(raw_mesh),
            "source": str(raw_source),
        },
        "mean_flame_fitted_control": {
            "role": "Identity shape fixed near zero; camera, pose, expression, jaw, eyes, eyelids, and intrinsics fitted to the private photos.",
            "path": str(mean_mesh),
            "source": str(mean_source),
            "tracking_actor_dir": str(mean_shape_actor_dir),
        },
        "personal_no_mica": {
            "role": "Pixel3DMM no-MICA identity shape fitted from the private input set.",
            "path": str(personal_mesh),
            "source": str(personal_source),
            "tracking_actor_dir": str(no_mica_actor_dir),
        },
    }

    for item in meshes.values():
        mesh_path = Path(item["path"])
        item["sha256"] = sha256(mesh_path)
        item.update(read_ply_header_counts(mesh_path))

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Freeze raw FLAME, fitted mean-shape control, and personalized no-MICA meshes for the next observed-photo face texture baker experiment.",
        "privacy": "Private biometric runtime artifacts. Keep in Drive/private storage; do not commit generated meshes or this private manifest to Git.",
        "run_dir": str(run_dir),
        "output_dir": str(out_dir),
        "mesh_coordinate_policy": "Original mesh coordinates are preserved. Display-only normalization from Plotly preview is not applied.",
        "texture_next_step": "Implement a custom multi-photo observed-pixel UV/texture baker and apply it to all three frozen mesh candidates before making a visual adoption decision.",
        "meshes": meshes,
    }

    (out_dir / "model_trio_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "README_PRIVATE.md").write_text(
        "# Private Model Trio For Texture\n\n"
        "This folder is generated from private biometric runtime data and must not be committed.\n\n"
        "- `raw_flame_template.ply`: FLAME template with no photo-derived values.\n"
        "- `mean_flame_fitted_control_canonical.ply`: mean identity shape with photo-fitted context.\n"
        "- `personal_no_mica_canonical.ply`: Pixel3DMM no-MICA personalized candidate.\n"
        "- `model_trio_manifest.json`: hashes, source paths, and roles.\n",
        encoding="utf-8",
    )

    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
