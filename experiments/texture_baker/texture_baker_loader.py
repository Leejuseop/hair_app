"""Load private texture-baker inputs without copying biometric artifacts.

This module resolves the cleaned private Drive layout into plain Python objects
that the observed-photo texture baker can consume. It intentionally records
paths and existence checks only; it does not load or write private images,
meshes, masks, textures, or renders into the Git repository.
"""

from __future__ import annotations

import argparse
import json
import os
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


COLAB_PRIVATE_ROOT = "/content/drive/MyDrive/hair_app"
DEFAULT_PEOPLE = ("주섭", "은채")
DEFAULT_EUNCHAE_MESH_KEYS = ("base_flame2023", "canonical")


@dataclass(frozen=True)
class MeshCandidate:
    key: str
    path: str
    exists: bool
    role: str | None = None
    source: str | None = None
    source_exists: bool | None = None
    vertices: int | None = None
    faces: int | None = None


@dataclass(frozen=True)
class FrameEvidence:
    frame_id: str
    crop: str
    crop_exists: bool
    uv_map: str | None
    uv_map_exists: bool
    segmentation_files: list[str]
    landmark_files: list[str]
    crop_meta: str | None
    crop_meta_exists: bool


@dataclass(frozen=True)
class PersonBundle:
    person: str
    input_dir: str
    output_dir: str
    manifest_path: str | None
    manifest_kind: str | None
    meshes: list[MeshCandidate]
    frames: list[FrameEvidence]
    folders: dict[str, str]
    warnings: list[str]


def default_private_root() -> Path:
    """Find the likely private Drive root for Colab or local Windows runs."""

    env_root = os.environ.get("HAIR_APP_PRIVATE_ROOT")
    candidates = [
        env_root,
        COLAB_PRIVATE_ROOT,
        r"G:\내 드라이브\hair_app",
        r"G:\My Drive\hair_app",
        str(Path.home() / "Google Drive" / "My Drive" / "hair_app"),
        str(Path.home() / "Google Drive" / "내 드라이브" / "hair_app"),
    ]
    for value in candidates:
        if not value:
            continue
        path = Path(value)
        if path.exists():
            return path
    raise FileNotFoundError(
        "Private Drive root not found. Pass --private-root or set "
        "HAIR_APP_PRIVATE_ROOT."
    )


def normalize_drive_fragment(value: str) -> str:
    """Normalize Google Drive path fragments across Colab and Windows."""

    value = value.replace("\\", "/")
    return unicodedata.normalize("NFC", value)


def resolve_private_path(
    value: str | None,
    private_root: Path,
    *,
    manifest_dir: Path | None = None,
) -> Path | None:
    """Resolve Colab, Windows, and manifest-relative paths.

    Private manifests were created in Colab and may contain paths such as
    /content/drive/MyDrive/hair_app/output/.... On Windows, those same files
    live under G:/내 드라이브/hair_app. Korean folder names may also arrive in
    decomposed Unicode form from Drive metadata, so path fragments are normalized
    to NFC before joining.
    """

    if value is None:
        return None

    raw_value = str(value).strip()
    if not raw_value:
        return None

    normalized = normalize_drive_fragment(raw_value)
    normalized_colab_root = normalize_drive_fragment(COLAB_PRIVATE_ROOT)

    if normalized == normalized_colab_root:
        return private_root

    prefix = normalized_colab_root + "/"
    if normalized.startswith(prefix):
        relative = normalized[len(prefix) :]
        return private_root / Path(relative)

    path = Path(raw_value)
    if path.is_absolute():
        if path.exists():
            return path
        # Some Colab manifests point into older staging folders. Preserve the
        # leaf-name fallback so frozen mesh copies beside the manifest still load.
        return path

    if manifest_dir is not None:
        return manifest_dir / normalized

    return private_root / normalized


def existing_path_or_sibling(path: Path | None, manifest_dir: Path) -> Path | None:
    """Return a usable path, falling back to a file beside the manifest."""

    if path is None:
        return None
    if path.exists():
        return path
    sibling = manifest_dir / path.name
    if sibling.exists():
        return sibling
    return path


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_ply_header_counts(path: Path) -> tuple[int | None, int | None]:
    if not path.exists():
        return None, None

    vertices: int | None = None
    faces: int | None = None
    with path.open("rb") as file:
        for raw_line in file:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line.startswith("element vertex "):
                vertices = int(line.rsplit(" ", 1)[-1])
            elif line.startswith("element face "):
                faces = int(line.rsplit(" ", 1)[-1])
            elif line == "end_header":
                break
    return vertices, faces


def find_manifest(person_output_dir: Path) -> tuple[Path | None, str | None]:
    trio = person_output_dir / "models" / "model_trio_for_texture" / "model_trio_manifest.json"
    if trio.exists():
        return trio, "model_trio"

    models_manifest = person_output_dir / "models" / "models_manifest.json"
    if models_manifest.exists():
        return models_manifest, "models_manifest"

    return None, None


def mesh_candidate_from_entry(
    key: str,
    entry: dict[str, Any],
    *,
    private_root: Path,
    manifest_dir: Path,
) -> MeshCandidate:
    path = existing_path_or_sibling(
        resolve_private_path(entry.get("path"), private_root, manifest_dir=manifest_dir),
        manifest_dir,
    )
    source = resolve_private_path(entry.get("source"), private_root, manifest_dir=manifest_dir)
    vertices, faces = read_ply_header_counts(path) if path is not None else (None, None)

    return MeshCandidate(
        key=key,
        path=str(path) if path is not None else "",
        exists=bool(path and path.exists()),
        role=entry.get("role"),
        source=str(source) if source is not None else None,
        source_exists=bool(source and source.exists()) if source is not None else None,
        vertices=vertices,
        faces=faces,
    )


def load_meshes_from_manifest(
    manifest_path: Path,
    manifest_kind: str,
    private_root: Path,
) -> list[MeshCandidate]:
    manifest = read_json(manifest_path)
    manifest_dir = manifest_path.parent

    if manifest_kind == "model_trio":
        meshes = manifest.get("meshes", {})
        return [
            mesh_candidate_from_entry(key, entry, private_root=private_root, manifest_dir=manifest_dir)
            for key, entry in meshes.items()
        ]

    candidates: list[MeshCandidate] = []
    for key in DEFAULT_EUNCHAE_MESH_KEYS:
        entry = manifest.get(key)
        if isinstance(entry, dict):
            candidates.append(
                mesh_candidate_from_entry(
                    key,
                    entry,
                    private_root=private_root,
                    manifest_dir=manifest_dir,
                )
            )

    # Fallback for the current cleaned Eunchae folder if the manifest shape changes.
    existing_keys = {item.key for item in candidates}
    fallback_paths = {
        "base_flame2023": manifest_dir / "base_flame2023.ply",
        "canonical": manifest_dir / "eunchae_no_mica_canonical.ply",
    }
    for key, path in fallback_paths.items():
        if key in existing_keys:
            continue
        if not path.exists():
            continue
        vertices, faces = read_ply_header_counts(path)
        candidates.append(
            MeshCandidate(
                key=key,
                path=str(path),
                exists=True,
                vertices=vertices,
                faces=faces,
            )
        )

    return candidates


def list_matching_files(folder: Path, frame_id: str, prefixes: tuple[str, ...]) -> list[Path]:
    if not folder.exists():
        return []

    matches: list[Path] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        stem = path.stem
        if stem == frame_id or stem in {f"{prefix}{frame_id}" for prefix in prefixes}:
            matches.append(path)
    return matches


def collect_frames(person_output_dir: Path) -> list[FrameEvidence]:
    crop_dir = person_output_dir / "crop"
    uv_dir = person_output_dir / "uv_map"
    segmentation_dir = person_output_dir / "segmentation"
    landmarks_dir = person_output_dir / "landmarks"
    crop_meta_dir = person_output_dir / "crop_meta"

    crop_paths = sorted(
        path
        for path in crop_dir.glob("*")
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )

    frames: list[FrameEvidence] = []
    for crop_path in crop_paths:
        frame_id = crop_path.stem
        uv_path = uv_dir / f"{frame_id}.png"
        crop_meta = crop_meta_dir / f"{frame_id}.json"
        segmentation_files = list_matching_files(
            segmentation_dir,
            frame_id,
            prefixes=("color_", "raw_", "mask_", "seg_"),
        )
        landmark_files = list_matching_files(
            landmarks_dir,
            frame_id,
            prefixes=("annotated_", "landmarks_", "pipnet_"),
        )

        frames.append(
            FrameEvidence(
                frame_id=frame_id,
                crop=str(crop_path),
                crop_exists=crop_path.exists(),
                uv_map=str(uv_path) if uv_path.exists() else None,
                uv_map_exists=uv_path.exists(),
                segmentation_files=[str(path) for path in segmentation_files],
                landmark_files=[str(path) for path in landmark_files],
                crop_meta=str(crop_meta) if crop_meta.exists() else None,
                crop_meta_exists=crop_meta.exists(),
            )
        )

    return frames


def load_person(person: str, private_root: Path | None = None) -> PersonBundle:
    root = private_root or default_private_root()
    person_input_dir = root / "input" / person
    person_output_dir = root / "output" / person
    manifest_path, manifest_kind = find_manifest(person_output_dir)
    warnings: list[str] = []

    if not person_input_dir.exists():
        warnings.append(f"Missing input directory: {person_input_dir}")
    if not person_output_dir.exists():
        warnings.append(f"Missing output directory: {person_output_dir}")
    if manifest_path is None or manifest_kind is None:
        warnings.append(f"Missing model manifest under: {person_output_dir / 'models'}")

    meshes: list[MeshCandidate] = []
    if manifest_path is not None and manifest_kind is not None:
        meshes = load_meshes_from_manifest(manifest_path, manifest_kind, root)
        for mesh in meshes:
            if not mesh.exists:
                warnings.append(f"Mesh path missing for {person}:{mesh.key}: {mesh.path}")

    frames = collect_frames(person_output_dir)
    if not frames:
        warnings.append(f"No crop frames found under: {person_output_dir / 'crop'}")

    missing_uv = [frame.frame_id for frame in frames if not frame.uv_map_exists]
    if missing_uv:
        warnings.append(f"Frames missing UV map: {', '.join(missing_uv[:8])}")

    folders = {
        "crop": str(person_output_dir / "crop"),
        "crop_meta": str(person_output_dir / "crop_meta"),
        "landmarks": str(person_output_dir / "landmarks"),
        "segmentation": str(person_output_dir / "segmentation"),
        "uv_map": str(person_output_dir / "uv_map"),
        "tracking": str(person_output_dir / "tracking"),
        "models": str(person_output_dir / "models"),
    }

    return PersonBundle(
        person=person,
        input_dir=str(person_input_dir),
        output_dir=str(person_output_dir),
        manifest_path=str(manifest_path) if manifest_path is not None else None,
        manifest_kind=manifest_kind,
        meshes=meshes,
        frames=frames,
        folders=folders,
        warnings=warnings,
    )


def summarize_bundle(bundle: PersonBundle) -> dict[str, Any]:
    frame_count = len(bundle.frames)
    return {
        "person": bundle.person,
        "manifest_kind": bundle.manifest_kind,
        "manifest_path": bundle.manifest_path,
        "mesh_count": len(bundle.meshes),
        "meshes": [
            {
                "key": mesh.key,
                "exists": mesh.exists,
                "vertices": mesh.vertices,
                "faces": mesh.faces,
                "path": mesh.path,
            }
            for mesh in bundle.meshes
        ],
        "frame_count": frame_count,
        "frames_with_uv": sum(1 for frame in bundle.frames if frame.uv_map_exists),
        "frames_with_segmentation": sum(1 for frame in bundle.frames if frame.segmentation_files),
        "frames_with_landmarks": sum(1 for frame in bundle.frames if frame.landmark_files),
        "frames_with_crop_meta": sum(1 for frame in bundle.frames if frame.crop_meta_exists),
        "first_frame_ids": [frame.frame_id for frame in bundle.frames[:8]],
        "warnings": bundle.warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve private Hair App texture-baker inputs.",
    )
    parser.add_argument(
        "--private-root",
        type=Path,
        default=None,
        help="Private Drive root, e.g. /content/drive/MyDrive/hair_app or G:/내 드라이브/hair_app.",
    )
    parser.add_argument(
        "--person",
        action="append",
        default=None,
        help="Person folder to load. May be passed more than once. Defaults to 주섭 and 은채.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Print full frame-level paths instead of a compact summary.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    private_root = args.private_root or default_private_root()
    people = args.person or list(DEFAULT_PEOPLE)

    bundles = [load_person(person, private_root=private_root) for person in people]
    output = {
        "private_root": str(private_root),
        "bundles": [asdict(bundle) if args.full else summarize_bundle(bundle) for bundle in bundles],
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
