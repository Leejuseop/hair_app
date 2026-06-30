# Step 3 Colab Cells: FaceXFormer + Grounded SAM2

These cells generate private external masks for:

- `v1_facexformer_only`
- `v2_farl_grounded_sam`
- `v3_facexformer_grounded_sam`

Run on Colab A100. Outputs go to:

```text
/content/drive/MyDrive/hair_app/output/facebuilder_mask_aware_step3_external
```

Do not commit generated masks, photos, overlays, textures, renders, OBJ/GLB, or
review sheets.

## Cell 1. Mount Drive and prepare paths

```python
from google.colab import drive
drive.mount("/content/drive")

from pathlib import Path
import json, os, shutil

DRIVE_ROOT = Path("/content/drive/MyDrive/hair_app")
SOURCE_VERSION = "facebuilder_semantic_v2"
SOURCE_ROOT = DRIVE_ROOT / "output" / SOURCE_VERSION
EXTERNAL_ROOT = DRIVE_ROOT / "output" / "facebuilder_mask_aware_step3_external"
EXTERNAL_ROOT.mkdir(parents=True, exist_ok=True)

PERSONS = ["juseop", "eunchae"]

def load_manifest(person):
    path = SOURCE_ROOT / person / "01_input_manifest" / "input_manifest.json"
    return json.loads(path.read_text(encoding="utf-8-sig"))

def iter_items(person):
    manifest = load_manifest(person)
    for item in manifest["items"]:
        yield item

print("external root:", EXTERNAL_ROOT)
for person in PERSONS:
    items = list(iter_items(person))
    print(person, len(items), items[0]["crop_path"])
```

## Cell 2. Install FaceXFormer

```python
%cd /content
!rm -rf /content/FaceXFormer
!git clone https://github.com/Kartik-3004/FaceXFormer.git /content/FaceXFormer
!pip install -q facenet-pytorch timm einops huggingface_hub

import sys
sys.path.insert(0, "/content/FaceXFormer")

from huggingface_hub import list_repo_files, hf_hub_download

files = list_repo_files("kartiknarayan/facexformer")
print([f for f in files if f.lower().endswith((".pt", ".pth", ".bin", ".ckpt"))])

checkpoint_candidates = [f for f in files if f.lower().endswith((".pt", ".pth", ".bin", ".ckpt"))]
assert checkpoint_candidates, "No FaceXFormer checkpoint found in Hugging Face repo."
FACE_XFORMER_CKPT = hf_hub_download("kartiknarayan/facexformer", checkpoint_candidates[0])
print("checkpoint:", FACE_XFORMER_CKPT)
```

## Cell 3. Run FaceXFormer parsing on existing FaceBuilder crops

This intentionally runs directly on our existing 512x512 FaceBuilder crop
images. It does not re-detect/re-crop faces, because we need the output mask to
stay in the same crop coordinate system.

```python
import torch
import numpy as np
from PIL import Image
import torchvision
from torchvision.transforms import InterpolationMode
from network import FaceXFormer

device = "cuda" if torch.cuda.is_available() else "cpu"
model = FaceXFormer().to(device)
ckpt = torch.load(FACE_XFORMER_CKPT, map_location=device)
state = ckpt.get("state_dict_backbone", ckpt)
model.load_state_dict(state, strict=False)
model.eval()

transform = torchvision.transforms.Compose([
    torchvision.transforms.Resize(size=(224, 224), interpolation=InterpolationMode.BICUBIC),
    torchvision.transforms.ToTensor(),
    torchvision.transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

def facexformer_parse_crop(crop_path):
    image = Image.open(crop_path).convert("RGB")
    x = transform(image).unsqueeze(0).to(device)
    labels = {
        "segmentation": torch.zeros([1, 224, 224], device=device),
        "lnm_seg": torch.zeros([1, 5, 2], device=device),
        "landmark": torch.zeros([1, 68, 2], device=device),
        "headpose": torch.zeros([1, 3], device=device),
        "attribute": torch.zeros([1, 40], device=device),
        "a_g_e": torch.zeros([1, 3], device=device),
        "visibility": torch.zeros([1, 29], device=device),
    }
    tasks = torch.tensor([0], device=device)  # Face parsing task
    with torch.no_grad(), torch.autocast(device_type="cuda", dtype=torch.float16, enabled=(device == "cuda")):
        *_, seg_output = model(x, labels, tasks)
        mask = seg_output.softmax(dim=1).argmax(dim=1)[0].detach().cpu().numpy().astype(np.uint8)
    return Image.fromarray(mask, mode="L").resize(image.size, Image.Resampling.NEAREST)

for person in PERSONS:
    out_dir = EXTERNAL_ROOT / "facexformer" / person / "labels"
    out_dir.mkdir(parents=True, exist_ok=True)
    for item in iter_items(person):
        crop_path = drive_path(item["crop_path"])
        out_path = out_dir / f"{item['index']:03d}.png"
        mask = facexformer_parse_crop(crop_path)
        mask.save(out_path)
    print("saved FaceXFormer labels:", person, out_dir)
```

## Cell 4. Install Grounded SAM2

This uses the official Grounded SAM2 path with Hugging Face Grounding DINO and
SAM2 image predictor.

```python
%cd /content
!rm -rf /content/Grounded-SAM-2
!git clone https://github.com/IDEA-Research/Grounded-SAM-2.git /content/Grounded-SAM-2
%cd /content/Grounded-SAM-2
!pip install -q -e .
!pip uninstall -y accelerate torchaudio
!pip install -q --no-cache-dir --force-reinstall "numpy==2.0.2" "Pillow==10.4.0"
!pip install -q transformers supervision pycocotools
%cd /content/Grounded-SAM-2/checkpoints
!bash download_ckpts.sh
!find /content/Grounded-SAM-2 -maxdepth 2 -name "sam2.1_hiera_*.pt" -print
!ls -lh /content/Grounded-SAM-2/checkpoints/*.pt
%cd /content/Grounded-SAM-2
```

## Cell 5. Run Grounded SAM2 object/occlusion masks

The prompt is intentionally object-focused. Do not include `person` or `face`,
because those would remove the actual face.

```python
%cd /content/Grounded-SAM-2

import sys, json, torch, numpy as np
from pathlib import Path
from PIL import Image, ImageDraw
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor

device = "cuda" if torch.cuda.is_available() else "cpu"
torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True

sam2_checkpoint = "./checkpoints/sam2.1_hiera_large.pt"
sam2_model_config = "configs/sam2.1/sam2.1_hiera_l.yaml"
sam2_model = build_sam2(sam2_model_config, sam2_checkpoint, device=device)
sam2_predictor = SAM2ImagePredictor(sam2_model)

grounding_model_id = "IDEA-Research/grounding-dino-tiny"
processor = AutoProcessor.from_pretrained(grounding_model_id)
grounding_model = AutoModelForZeroShotObjectDetection.from_pretrained(grounding_model_id).to(device)

TEXT_PROMPT = (
    "hand. finger. mobile phone. smartphone. perfume bottle. cosmetic bottle. "
    "bottle. compact mirror. makeup product. eyeglasses. glasses. headphones. hair clip."
)

REJECT_LABEL_WORDS = ("face", "person", "head", "hair", "skin", "eye", "nose", "mouth", "lip")

def box_area_fraction(box, image_size):
    width, height = image_size
    x0, y0, x1, y1 = box
    return max(0.0, x1 - x0) * max(0.0, y1 - y0) / max(1.0, width * height)

def max_allowed_area(label):
    label_l = label.lower()
    if "hand" in label_l or "finger" in label_l or "headphones" in label_l:
        return 0.42
    return 0.22

def should_keep_detection(label, score, box, image_size):
    label_l = label.lower()
    if any(word in label_l for word in REJECT_LABEL_WORDS):
        return False, "rejected_label"
    area = box_area_fraction(box, image_size)
    if area > max_allowed_area(label):
        return False, f"box_too_large:{area:.3f}"
    return True, "kept"

def grounded_sam_object_mask(image_path, box_threshold=0.30, text_threshold=0.25):
    image = Image.open(image_path).convert("RGB")
    sam2_predictor.set_image(np.array(image))
    inputs = processor(images=image, text=TEXT_PROMPT, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = grounding_model(**inputs)
    results = processor.post_process_grounded_object_detection(
        outputs,
        inputs.input_ids,
        threshold=box_threshold,
        text_threshold=text_threshold,
        target_sizes=[image.size[::-1]],
    )[0]
    boxes_all = results["boxes"].detach().cpu().numpy()
    labels_all = list(results["labels"])
    scores_all = results["scores"].detach().cpu().numpy().tolist()
    kept = []
    rejected = []
    for label, score, box in zip(labels_all, scores_all, boxes_all):
        keep, reason = should_keep_detection(label, score, box, image.size)
        record = {"label": label, "score": float(score), "box": box.tolist(), "reason": reason}
        if keep:
            kept.append(record)
        else:
            rejected.append(record)

    kept_masks = []
    for item in kept:
        box = np.asarray([item["box"]], dtype=np.float32)
        masks, mask_scores, logits = sam2_predictor.predict(
            point_coords=None,
            point_labels=None,
            box=box,
            multimask_output=False,
        )
        if masks.ndim == 4:
            masks = masks.squeeze(1)
        mask = masks[0].astype(bool)
        mask_area = float(mask.mean())
        if mask_area > max_allowed_area(item["label"]) * 1.35:
            item["mask_area"] = mask_area
            item["reason"] = f"mask_too_large:{mask_area:.3f}"
            rejected.append(item)
            continue
        item["mask_area"] = mask_area
        kept_masks.append(mask)

    if kept_masks:
        combined = np.stack(kept_masks, axis=0).any(axis=0)
    else:
        combined = np.zeros((image.size[1], image.size[0]), dtype=bool)
    return Image.fromarray((combined.astype(np.uint8) * 255), mode="L"), {
        "prompt": TEXT_PROMPT,
        "kept": kept,
        "rejected": rejected,
        "all_labels": labels_all,
        "all_scores": scores_all,
        "all_boxes": boxes_all.tolist(),
    }

for person in PERSONS:
    mask_dir = EXTERNAL_ROOT / "grounded_sam" / person / "object_masks"
    meta_dir = EXTERNAL_ROOT / "grounded_sam" / person / "metadata"
    mask_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    for item in iter_items(person):
        crop_path = drive_path(item["crop_path"])
        mask, meta = grounded_sam_object_mask(crop_path)
        mask.save(mask_dir / f"{item['index']:03d}.png")
        (meta_dir / f"{item['index']:03d}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("saved Grounded SAM masks:", person, mask_dir)
```

## Cell 6. After Colab finishes

Back in Codex/local, run:

```powershell
python experiments\facebuilder_mask_aware_correction\run_step3_masks.py `
  --source-version facebuilder_semantic_v2
```

That regenerates all four versions:

```text
v0_farl_only
v1_facexformer_only
v2_farl_grounded_sam
v3_facexformer_grounded_sam
```
