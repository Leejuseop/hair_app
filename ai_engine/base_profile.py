from __future__ import annotations

import statistics
from typing import Any


SCAN_STEPS = ("front", "left", "right", "hairline")


def build_base_profile(scan_record: dict[str, Any]) -> dict[str, Any]:
    """Build a reusable personal base profile from stored scan samples."""
    steps = scan_record["steps"]
    best_samples = {
        step: _best_sample(steps.get(step, {}).get("samples", []))
        for step in SCAN_STEPS
    }

    front = best_samples["front"]
    hairline = best_samples["hairline"]

    return {
        "scan_id": scan_record["scan_id"],
        "version": "0.1",
        "status": "ready",
        "assets": _build_assets(best_samples),
        "raw_landmark_samples": _build_raw_landmark_samples(steps),
        "derived_metrics": _build_derived_metrics(steps, best_samples),
        "synthesis_anchors": _build_synthesis_anchors(front, hairline),
        "preview": _build_preview(front, hairline),
    }


def _best_sample(samples: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not samples:
        return None

    return max(samples, key=lambda sample: _quality_score(sample))


def _quality_score(sample: dict[str, Any]) -> float:
    quality = sample.get("quality") or {}
    score = quality.get("score", 0)
    return float(score or 0)


def _build_assets(best_samples: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    return {
        f"best_{step}_image": _asset_payload(sample)
        for step, sample in best_samples.items()
    }


def _asset_payload(sample: dict[str, Any] | None) -> dict[str, Any] | None:
    if not sample:
        return None

    return {
        "sample_id": sample["id"],
        "image_path": sample.get("image_path"),
        "image_url": sample.get("image_url"),
        "quality_score": _quality_score(sample),
    }


def _build_raw_landmark_samples(steps: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    raw_samples: dict[str, list[dict[str, Any]]] = {}

    for step in SCAN_STEPS:
        raw_samples[step] = [
            {
                "sample_id": sample["id"],
                "image_path": sample.get("image_path"),
                "image_url": sample.get("image_url"),
                "key_points": sample.get("keyPoints", {}),
                "landmarks": sample.get("landmarks", []),
                "pose": sample.get("pose", {}),
                "quality": sample.get("quality", {}),
            }
            for sample in steps.get(step, {}).get("samples", [])
        ]

    return raw_samples


def _build_derived_metrics(
    steps: dict[str, Any],
    best_samples: dict[str, dict[str, Any] | None],
) -> dict[str, Any]:
    front = best_samples["front"]
    hairline = best_samples["hairline"]
    left = best_samples["left"]
    right = best_samples["right"]

    return {
        "average_quality": {
            step: _round(_average_quality(steps.get(step, {}).get("samples", [])))
            for step in SCAN_STEPS
        },
        "face": _face_metrics(front),
        "hairline": _hairline_metrics(hairline),
        "side_profile": {
            "left": _side_metrics(left),
            "right": _side_metrics(right),
            "symmetry_proxy": _side_symmetry_proxy(left, right),
        },
    }


def _face_metrics(sample: dict[str, Any] | None) -> dict[str, Any]:
    if not sample:
        return {}

    quality = sample.get("quality", {})
    face_width = float(quality.get("faceWidth") or 0)
    face_height = float(quality.get("faceHeight") or 0)
    key_points = sample.get("keyPoints", {})

    return {
        "face_height": _round(face_height),
        "face_ratio": _round(face_height / face_width) if face_width else None,
        "face_width": _round(face_width),
        "jaw_width_proxy": _round(
            _point_distance(
                key_points.get("leftCheek"),
                key_points.get("rightCheek"),
            ),
        ),
        "mouth_symmetry_proxy": quality.get("mouthSymmetry"),
        "roll": quality.get("roll"),
    }


def _hairline_metrics(sample: dict[str, Any] | None) -> dict[str, Any]:
    if not sample:
        return {}

    quality = sample.get("quality", {})
    key_points = sample.get("keyPoints", {})
    forehead_top = key_points.get("foreheadTop")
    left_brow = key_points.get("leftBrowOuter")
    right_brow = key_points.get("rightBrowOuter")
    brow_midpoint = _midpoint(left_brow, right_brow)
    face_height = float(quality.get("faceHeight") or 0)

    forehead_height = (
        abs(float(brow_midpoint["y"]) - float(forehead_top["y"])) / face_height
        if forehead_top and brow_midpoint and face_height
        else None
    )

    return {
        "face_top": quality.get("faceTop"),
        "forehead_height_proxy": _round(forehead_height),
        "hairline_visibility_proxy": quality.get("faceTop"),
    }


def _side_metrics(sample: dict[str, Any] | None) -> dict[str, Any]:
    if not sample:
        return {}

    quality = sample.get("quality", {})

    return {
        "face_height": quality.get("faceHeight"),
        "face_width": quality.get("faceWidth"),
        "matrix_yaw": quality.get("matrixYaw"),
        "roll": quality.get("roll"),
        "yaw_proxy": quality.get("yawProxy"),
    }


def _side_symmetry_proxy(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> dict[str, Any]:
    if not left or not right:
        return {}

    left_quality = left.get("quality", {})
    right_quality = right.get("quality", {})

    return {
        "height_delta": _round(
            abs(
                float(left_quality.get("faceHeight") or 0)
                - float(right_quality.get("faceHeight") or 0),
            ),
        ),
        "width_delta": _round(
            abs(
                float(left_quality.get("faceWidth") or 0)
                - float(right_quality.get("faceWidth") or 0),
            ),
        ),
        "yaw_delta": _round(
            abs(
                abs(float(left_quality.get("yawProxy") or 0))
                - abs(float(right_quality.get("yawProxy") or 0)),
            ),
        ),
    }


def _build_synthesis_anchors(
    front: dict[str, Any] | None,
    hairline: dict[str, Any] | None,
) -> dict[str, Any]:
    front_points = front.get("keyPoints", {}) if front else {}
    hairline_points = hairline.get("keyPoints", {}) if hairline else {}
    source_points = hairline_points or front_points

    return {
        "face_centerline": _filter_points(
            source_points,
            ("foreheadTop", "foreheadCenter", "noseBridge", "noseTip", "chin"),
        ),
        "hairline": _filter_points(
            source_points,
            ("leftTemple", "leftBrowOuter", "foreheadTop", "rightBrowOuter", "rightTemple"),
        ),
        "jaw": _filter_points(front_points, ("leftCheek", "chin", "rightCheek")),
        "temples": _filter_points(source_points, ("leftTemple", "rightTemple")),
    }


def _build_preview(
    front: dict[str, Any] | None,
    hairline: dict[str, Any] | None,
) -> dict[str, Any]:
    if not front:
        return {}

    hairline_points = (
        _filter_points(
            hairline.get("keyPoints", {}) if hairline else {},
            ("leftTemple", "leftBrowOuter", "foreheadTop", "rightBrowOuter", "rightTemple"),
        )
        or _filter_points(
            front.get("keyPoints", {}),
            ("leftTemple", "leftBrowOuter", "foreheadTop", "rightBrowOuter", "rightTemple"),
        )
    )

    return {
        "front_image_url": front.get("image_url"),
        "front_sample_id": front["id"],
        "hairline_points": hairline_points,
        "landmarks": front.get("landmarks", []),
        "quality_score": _quality_score(front),
    }


def _average_quality(samples: list[dict[str, Any]]) -> float | None:
    scores = [_quality_score(sample) for sample in samples]
    return statistics.fmean(scores) if scores else None


def _filter_points(points: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    return {
        name: points[name]
        for name in names
        if name in points and points[name] is not None
    }


def _point_distance(first: dict[str, Any] | None, second: dict[str, Any] | None) -> float | None:
    if not first or not second:
        return None

    return (
        (float(first["x"]) - float(second["x"])) ** 2
        + (float(first["y"]) - float(second["y"])) ** 2
    ) ** 0.5


def _midpoint(first: dict[str, Any] | None, second: dict[str, Any] | None) -> dict[str, float] | None:
    if not first or not second:
        return None

    return {
        "x": (float(first["x"]) + float(second["x"])) / 2,
        "y": (float(first["y"]) + float(second["y"])) / 2,
        "z": (float(first.get("z") or 0) + float(second.get("z") or 0)) / 2,
    }


def _round(value: float | None) -> float | None:
    if value is None:
        return None

    return round(float(value), 3)
