import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np
import torch
from omegaconf import OmegaConf

from pixel3dmm.tracking.flame.FLAME import FLAME
from pixel3dmm.utils.utils_3d import (
    matrix_to_rotation_6d,
    rotation_6d_to_matrix,
)


WFLW_TO_68 = np.array(
    [
        0,
        2,
        4,
        6,
        8,
        10,
        12,
        14,
        16,
        18,
        20,
        22,
        24,
        26,
        28,
        30,
        32,
        33,
        34,
        35,
        36,
        37,
        42,
        43,
        44,
        45,
        46,
        51,
        52,
        53,
        54,
        55,
        56,
        57,
        58,
        59,
        60,
        61,
        63,
        64,
        65,
        67,
        68,
        69,
        71,
        72,
        73,
        75,
        76,
        77,
        78,
        79,
        80,
        81,
        82,
        83,
        84,
        85,
        86,
        87,
        88,
        89,
        90,
        91,
        92,
        93,
        94,
        95,
    ],
    dtype=np.int64,
)


def as_tensor(value, ndim, device):
    value = torch.as_tensor(value, dtype=torch.float32, device=device)
    while value.ndim < ndim:
        value = value.unsqueeze(0)
    return value


def project_points(
    points,
    focal_length,
    principal_point,
    rotation_base,
    translation_base,
    size,
):
    batch = points.shape[0]
    intrinsics = (
        torch.eye(3, dtype=torch.float32, device=points.device)
        .unsqueeze(0)
        .repeat(batch, 1, 1)
    )
    intrinsics[:, 0, 0] = focal_length.reshape(-1) * size
    intrinsics[:, 1, 1] = focal_length.reshape(-1) * size
    intrinsics[:, :2, 2] = (
        size / 2 + 0.5 + principal_point * (size / 2 + 0.5)
    )

    # Match Pixel3DMM's landmark projection convention.
    intrinsics[:, 0:1, 2:3] = size - intrinsics[:, 0:1, 2:3]

    world_to_camera = (
        torch.eye(4, dtype=torch.float32, device=points.device)
        .unsqueeze(0)
        .repeat(batch, 1, 1)
    )
    world_to_camera[:, :3, :3] = rotation_base
    world_to_camera[:, :3, 3] = translation_base

    homogeneous = torch.cat([points, torch.ones_like(points[..., :1])], dim=-1)
    camera = torch.bmm(homogeneous, world_to_camera.transpose(1, 2))
    normalized = camera[..., :3] / -camera[..., [2]]
    screen = -torch.bmm(normalized, intrinsics.transpose(1, 2))[..., :2]

    return torch.stack(
        [size - 1 - screen[..., 0], screen[..., 1]],
        dim=-1,
    )


def generate_landmarks(flame, shape, context):
    rotation_matrix = rotation_6d_to_matrix(context["rotation"])
    landmark_rotation = matrix_to_rotation_6d(torch.inverse(rotation_matrix))

    _, landmarks, _, _, _ = flame(
        cameras=torch.inverse(context["rotation_base"]),
        shape_params=shape,
        expression_params=context["expression"],
        eye_pose_params=context["eyes"],
        jaw_pose_params=context["jaw"],
        neck_pose_params=context["neck"],
        eyelid_params=context["eyelids"],
        rot_params_lmk_shift=landmark_rotation,
    )

    landmarks = torch.einsum("bny,bxy->bnx", landmarks, rotation_matrix)
    return landmarks + context["translation"].unsqueeze(1)


def load_frame(path):
    return torch.load(path, map_location="cpu", weights_only=False)


def load_shape(frame, device):
    return as_tensor(frame["flame"]["shape"], 2, device)


def load_context(frame, device):
    flame_data = frame["flame"]
    camera_data = frame["camera"]
    r_key = sorted(key for key in camera_data if key.startswith("R_base_"))[0]
    t_key = sorted(key for key in camera_data if key.startswith("t_base_"))[0]

    return {
        "expression": as_tensor(flame_data["exp"], 2, device),
        "eyes": as_tensor(flame_data["eyes"], 2, device),
        "eyelids": as_tensor(flame_data["eyelids"], 2, device),
        "jaw": as_tensor(flame_data["jaw"], 2, device),
        "neck": as_tensor(flame_data["neck"], 2, device),
        "rotation": as_tensor(flame_data["R"], 2, device),
        "translation": as_tensor(flame_data["t"], 2, device),
        "rotation_base": as_tensor(camera_data[r_key], 3, device),
        "translation_base": as_tensor(camera_data[t_key], 2, device),
        "focal_length": as_tensor(camera_data["fl"], 2, device),
        "principal_point": as_tensor(camera_data["pp"], 2, device),
    }


def predict_2d(flame, shape, context, size):
    points_3d = generate_landmarks(flame, shape, context)
    return (
        project_points(
            points_3d,
            context["focal_length"],
            context["principal_point"],
            context["rotation_base"],
            context["translation_base"],
            size,
        )[0]
        .cpu()
        .numpy()
    )


def error_stats(prediction, target, valid):
    errors = np.linalg.norm(prediction[valid] - target[valid], axis=1)
    contour_valid = valid[:17]
    internal_valid = valid[17:]
    contour = np.linalg.norm(
        prediction[:17][contour_valid] - target[:17][contour_valid],
        axis=1,
    )
    internal = np.linalg.norm(
        prediction[17:][internal_valid] - target[17:][internal_valid],
        axis=1,
    )
    interocular = max(float(np.linalg.norm(target[36] - target[45])), 1e-6)
    return {
        "error_px": float(errors.mean()),
        "contour_error_px": float(contour.mean()),
        "internal_error_px": float(internal.mean()),
        "normalized_error": float(errors.mean() / interocular),
    }


def draw_points(image, points, color, radius=2):
    result = image.copy()
    for x, y in points:
        if not np.isfinite(x) or not np.isfinite(y):
            continue
        x = int(round(x))
        y = int(round(y))
        if 0 <= x < result.shape[1] and 0 <= y < result.shape[0]:
            cv2.circle(
                result,
                (x, y),
                radius,
                color,
                -1,
                lineType=cv2.LINE_AA,
            )
    return result


def add_panel(image, target, prediction, title, error):
    # Green: PIPNet target, red: evaluated FLAME landmarks.
    panel = draw_points(image, target, (0, 255, 0), radius=2)
    panel = draw_points(panel, prediction, (0, 0, 255), radius=1)
    cv2.putText(
        panel,
        f"{title} {error:.2f}px",
        (6, 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return panel


def actor_frames(actor_dir):
    files = sorted((actor_dir / "checkpoint").glob("*.frame"))
    assert files, actor_dir / "checkpoint"
    return {int(path.stem): path for path in files}


parser = argparse.ArgumentParser()
parser.add_argument("--video-name", required=True)
parser.add_argument("--no-mica-actor-dir", required=True)
parser.add_argument("--mica-actor-dir", required=True)
parser.add_argument("--output-dir", required=True)
args = parser.parse_args()

device = "cuda"
torch.set_grad_enabled(False)

no_actor_dir = Path(args.no_mica_actor_dir)
mica_actor_dir = Path(args.mica_actor_dir)
output_dir = Path(args.output_dir)
output_dir.mkdir(parents=True, exist_ok=True)
data_dir = Path("/content/p3dmm_preprocessed") / args.video_name

config = OmegaConf.load("/content/pixel3dmm/configs/tracking.yaml")
config.use_flame2023 = True
config.num_shape_params = 300
config.num_exp_params = 100
size = int(config.size)
flame = FLAME(config).to(device).eval()

no_frames = actor_frames(no_actor_dir)
mica_frames = actor_frames(mica_actor_dir)
assert set(no_frames) == set(mica_frames), {
    "only_no_mica": sorted(set(no_frames) - set(mica_frames)),
    "only_mica": sorted(set(mica_frames) - set(no_frames)),
}
frame_ids = sorted(no_frames)

no_first = load_frame(no_frames[frame_ids[0]])
mica_first = load_frame(mica_frames[frame_ids[0]])
no_shape = load_shape(no_first, device)
mica_shape = load_shape(mica_first, device)
assert no_shape.shape == mica_shape.shape, (no_shape.shape, mica_shape.shape)

# Identity should be shared by every view within each tracking run.
shape_consistency = {"no_mica_max_abs": 0.0, "mica_max_abs": 0.0}
for frame_id in frame_ids:
    current_no = load_shape(load_frame(no_frames[frame_id]), device)
    current_mica = load_shape(load_frame(mica_frames[frame_id]), device)
    shape_consistency["no_mica_max_abs"] = max(
        shape_consistency["no_mica_max_abs"],
        float((current_no - no_shape).abs().max().item()),
    )
    shape_consistency["mica_max_abs"] = max(
        shape_consistency["mica_max_abs"],
        float((current_mica - mica_shape).abs().max().item()),
    )

rows = []
metrics = []

for frame_id in frame_ids:
    no_frame = load_frame(no_frames[frame_id])
    mica_frame = load_frame(mica_frames[frame_id])
    no_context = load_context(no_frame, device)
    mica_context = load_context(mica_frame, device)

    predictions = {
        "no_context_no_shape": predict_2d(
            flame, no_shape, no_context, size
        ),
        "no_context_mica_shape": predict_2d(
            flame, mica_shape, no_context, size
        ),
        "mica_context_no_shape": predict_2d(
            flame, no_shape, mica_context, size
        ),
        "mica_context_mica_shape": predict_2d(
            flame, mica_shape, mica_context, size
        ),
    }

    landmark_path = data_dir / "PIPnet_landmarks" / f"{frame_id:05d}.npy"
    assert landmark_path.exists(), landmark_path
    gt68 = np.load(landmark_path)[WFLW_TO_68] * size

    valid = np.isfinite(gt68).all(axis=1) & (gt68.sum(axis=1) != 0)
    for prediction in predictions.values():
        valid &= np.isfinite(prediction).all(axis=1)

    condition_stats = {
        name: error_stats(prediction, gt68, valid)
        for name, prediction in predictions.items()
    }

    item = {
        "frame": frame_id,
        "valid_landmarks": int(valid.sum()),
    }
    for name, stats in condition_stats.items():
        for metric_name, value in stats.items():
            item[f"{name}_{metric_name}"] = value

    item["no_context_mica_improvement_px"] = (
        item["no_context_no_shape_error_px"]
        - item["no_context_mica_shape_error_px"]
    )
    item["mica_context_mica_improvement_px"] = (
        item["mica_context_no_shape_error_px"]
        - item["mica_context_mica_shape_error_px"]
    )
    item["native_mica_improvement_px"] = (
        item["no_context_no_shape_error_px"]
        - item["mica_context_mica_shape_error_px"]
    )
    metrics.append(item)

    image_path = data_dir / "cropped" / f"{frame_id:05d}.jpg"
    if not image_path.exists():
        image_path = data_dir / "cropped" / f"{frame_id:05d}.png"
    image = cv2.imread(str(image_path))
    assert image is not None, image_path
    image = cv2.resize(image, (size, size))

    panels = [
        add_panel(
            image,
            gt68,
            predictions["no_context_no_shape"],
            "NOctx/NOshape",
            item["no_context_no_shape_error_px"],
        ),
        add_panel(
            image,
            gt68,
            predictions["no_context_mica_shape"],
            "NOctx/MICAshape",
            item["no_context_mica_shape_error_px"],
        ),
        add_panel(
            image,
            gt68,
            predictions["mica_context_no_shape"],
            "MICActx/NOshape",
            item["mica_context_no_shape_error_px"],
        ),
        add_panel(
            image,
            gt68,
            predictions["mica_context_mica_shape"],
            "MICActx/MICAshape",
            item["mica_context_mica_shape_error_px"],
        ),
    ]
    combined = np.concatenate(panels, axis=1)
    cv2.putText(
        combined,
        (
            f"view {frame_id} | MICA shape gain: "
            f"NOctx {item['no_context_mica_improvement_px']:+.2f}px, "
            f"MICActx {item['mica_context_mica_improvement_px']:+.2f}px"
        ),
        (6, size - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    rows.append(combined)

sheet = np.concatenate(rows, axis=0)
sheet = cv2.resize(
    sheet,
    None,
    fx=1.5,
    fy=1.5,
    interpolation=cv2.INTER_CUBIC,
)
sheet_path = output_dir / "mica_vs_no_mica_2x2_landmarks.png"
cv2.imwrite(str(sheet_path), sheet)


def values(key):
    return np.asarray([item[key] for item in metrics], dtype=np.float64)


no_context_no = values("no_context_no_shape_error_px")
no_context_mica = values("no_context_mica_shape_error_px")
mica_context_no = values("mica_context_no_shape_error_px")
mica_context_mica = values("mica_context_mica_shape_error_px")

summary = {
    "views": len(metrics),
    "shape_consistency_max_abs": shape_consistency,
    "no_mica_camera_pose_expression_context": {
        "no_mica_shape_average_error_px": float(no_context_no.mean()),
        "mica_shape_average_error_px": float(no_context_mica.mean()),
        "mica_shape_average_improvement_px": float(
            no_context_no.mean() - no_context_mica.mean()
        ),
        "mica_shape_wins_views": int(np.sum(no_context_mica < no_context_no)),
        "no_mica_shape_wins_views": int(
            np.sum(no_context_no < no_context_mica)
        ),
    },
    "mica_camera_pose_expression_context": {
        "no_mica_shape_average_error_px": float(mica_context_no.mean()),
        "mica_shape_average_error_px": float(mica_context_mica.mean()),
        "mica_shape_average_improvement_px": float(
            mica_context_no.mean() - mica_context_mica.mean()
        ),
        "mica_shape_wins_views": int(
            np.sum(mica_context_mica < mica_context_no)
        ),
        "no_mica_shape_wins_views": int(
            np.sum(mica_context_no < mica_context_mica)
        ),
    },
    "native_run_comparison_not_same_context": {
        "no_mica_native_average_error_px": float(no_context_no.mean()),
        "mica_native_average_error_px": float(mica_context_mica.mean()),
        "mica_native_improvement_px": float(
            no_context_no.mean() - mica_context_mica.mean()
        ),
    },
    "landmark_signal": {
        "mica_better_in_both_fixed_contexts": bool(
            no_context_mica.mean() < no_context_no.mean()
            and mica_context_mica.mean() < mica_context_no.mean()
        ),
        "note": (
            "This isolates identity-shape preference under each run's fixed "
            "camera, pose and expression. It is landmark evidence, not a full "
            "identity or hidden-scalp quality proof."
        ),
    },
}

(output_dir / "metrics.json").write_text(
    json.dumps(
        {
            "summary": summary,
            "per_view": metrics,
        },
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

with (output_dir / "metrics.csv").open(
    "w",
    newline="",
    encoding="utf-8",
) as file:
    writer = csv.DictWriter(file, fieldnames=list(metrics[0].keys()))
    writer.writeheader()
    writer.writerows(metrics)

print("MICA VS NO-MICA 2x2 VALIDATION COMPLETE")
print(json.dumps(summary, indent=2, ensure_ascii=False))
print("saved:", output_dir)
print("sheet:", sheet_path)
