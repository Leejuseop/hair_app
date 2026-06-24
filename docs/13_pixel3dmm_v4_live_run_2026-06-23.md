# Pixel3DMM V4 Live Run — Full Record and Resume Guide

Last synchronized: 2026-06-24
Status: preprocessing 8/8 complete and saved; normal/UV checkpoint compatibility fix implemented locally but not yet rerun in the live Colab runtime
Primary notebook: `experiments/milestone1_geometry_bakeoff/pixel3dmm_colab_v4.ipynb`
Notebook SHA-256: `2d1ff3b87c7423876e496aa8b06d1b6451542a00df9f62f75a504bb7ce301d46`
Audited Pixel3DMM commit: `fcd1fa973c7715b02a8948dfc679dff53cf85924`

## 1. Purpose

이 문서는 2026-06-23 Pixel3DMM A100 Colab 재현 과정에서 실제로 실행한 단계, 관찰한 출력, 발생한 오류, 원인, 적용한 수정, 현재 Drive artifact, 다음 시작 지점을 하나의 chronological handoff로 보존한다.

상세 설계 근거는 다음 문서와 함께 본다.

- `docs/10_3d_hair_app_master_plan.md`: Hair App 전체 3D 방향.
- `docs/history.md`: v1~v3 roll 실험을 포함한 전체 프로젝트 역사와 실패 원인.
- `docs/12_pixel3dmm_preprocessing_contract.md`: official source audit와 최종 좌표/전처리 계약.
- `experiments/milestone1_geometry_bakeoff/README.md`: Milestone 1 실행·평가 규칙.

이 문서의 재개 지점은 실제 코드와 결과에 기반한다. 아직 normal/UV 또는 mesh가 성공한 것처럼 해석하면 안 된다.

## 2. Current Exact State

### Completed in the live Colab runtime

- Google Drive mounted.
- Pixel3DMM environment and CUDA extensions built on A100.
- FLAME2020, FLAME2023, Vertex Masks, landmark embedding installed and validated.
- private 8-photo input discovered.
- V4 official FaceBoxes per-image no-roll crop generated for 8/8 images.
- Gate A crop visual validation passed for 8/8 images.
- PIPNet WFLW 98 landmark files and annotated overlays generated for 8/8 images.
- FaRL raw segmentation and color previews generated for 8/8 images.
- count gate result: `input/crop/meta/landmark/annotated/seg = 8/8/8/8/8/8`.
- user visually confirmed the preprocessing output looked correct.
- preprocessing artifacts were saved to a private Google Drive run folder. The user reported the detailed save cell completed; the exact final printed path/count was not pasted back into chat.
- `PREPROCESSING_APPROVED=True` was set before attempting network inference.

### Last attempted step

Pixel3DMM normal inference was started from notebook section 8 and failed before processing the first image while loading the Lightning checkpoint.

Exact root error:

```text
_pickle.UnpicklingError: Weights only load failed.
Unsupported global: GLOBAL omegaconf.dictconfig.DictConfig
```

Cause:

- PyTorch 2.6+ changed `torch.load` default behavior to `weights_only=True`.
- official Pixel3DMM Lightning checkpoints contain OmegaConf configuration objects in addition to tensor weights.
- this is not a corrupt checkpoint and not an input-photo error.

Implemented local notebook fix:

```python
model = p3dmm_system.load_from_checkpoint(
    model_checkpoint,
    strict=False,
    weights_only=False,
)
```

Trust boundary:

- this relaxation is applied only to the official Pixel3DMM checkpoints downloaded by the notebook from the upstream-provided Google Drive IDs;
- it is not a global arbitrary-checkpoint bypass;
- unknown or user-supplied checkpoints must not be loaded with this setting without separate verification.

### Immediate next action

If the current Colab runtime is still alive, start at **Section 11.1** below: patch the live `network_inference.py`, rerun the normal/UV cell, then run the output-count cell.

If the runtime is gone, use **Section 11.2** and start with the latest repository V4 notebook.

## 3. Pinned Components and Runtime Assumptions

The V4 notebook records or pins the following research components.

| Component | Version / commit / source |
| --- | --- |
| Pixel3DMM | `fcd1fa973c7715b02a8948dfc679dff53cf85924` |
| Python env | conda `p3dmm`, Python 3.9 |
| Torch | `2.7.0+cu118` |
| torchvision | `0.22.0+cu118` |
| torchaudio | `2.7.0+cu118` |
| PyTorch3D | `75ebeeaea0908c5527e7b1e305fbc7681382db47` |
| nvdiffrast | `253ac4fcea7de5f396371124af597e6cc957bfae` |
| Facer | `ddd35c76ff840174b8a5403ad1c1255e37b8782b` |
| PIPNet | `b9eab58816437403a34aa5bc3adeafe5081fd36b` |
| DECA landmark embedding | `yfeng95/DECA@a11554ae2a2b0f3998cf1fa94dd4db03babb34a2` |
| DECA embedding SHA-256 | `8095348eeafce5a02f6bd8765146307f9567a3f03b316d788a2e47336d667954` |
| Crop | official FaceBoxesV2, confidence-first, margin 1.42, 512×512, no roll |
| Landmarks | official PIPNet WFLW 98 on final crop |
| Segmentation | FaRL `celebm/448` |
| GPU observed | NVIDIA A100-SXM4-80GB |

The user also has H100 access. V4 detects compute capability and sets A100/H100-compatible CUDA arch automatically.

## 4. Final V4 Pipeline Contract

```text
private source photos
  -> EXIF orientation
  -> FaceBoxes detections independently per photo
  -> highest-confidence face candidate
  -> square bbox, requested margin 1.42
  -> move inside source bounds; reduce margin only when source is too tight
  -> resize once to final 512x512 crop
  -> preserve image-plane roll
  -> save every candidate, selected bbox, warnings, source<->crop matrices
  -> official PIPNet WFLW 98 on the final crop
  -> official FaRL CelebM segmentation on the final crop
  -> human/count gate
  -> Pixel3DMM normals and UV
  -> multi-image FLAME tracking
  -> mesh preview and Drive run manifest
```

The persistent crop must not rotate the image. The tracker estimates camera/head rotation from PIPNet landmarks, segmentation, normal and UV evidence. v1~v3 crop-time sparse-landmark roll experiments are historical only.

## 5. Chronological Live Error and Fix Log

### 5.1 Conda/Colab runtime restart

Expected behavior:

- `condacolab.install()` restarts the Python runtime.
- `/content` survives a simple kernel restart in some cases but must never be assumed persistent across disconnect/reallocation.
- after a full runtime loss, conda env, cloned repositories and generated preprocessing files disappear; Google Drive files remain.

Operational rule:

- after the first conda restart, run the notebook again from the repository clone/environment check;
- if the runtime was fully replaced, use the latest V4 notebook from the beginning.

### 5.2 Google Drive mount failure

Observed error:

```text
ValueError: mount failed
```

Recovery used:

```python
from google.colab import drive
drive.mount('/content/drive', force_remount=True, timeout_ms=120000)
```

This was an authentication/mount-state problem, not a Pixel3DMM error.

### 5.3 FLAME distribution mismatch

Drive contained:

- `FLAME2020.zip`
- `FLAME2023.zip`
- `FLAME_masks.zip`

The ZIPs did not contain Pixel3DMM's required `landmark_embedding.npy`. An earlier V4 draft incorrectly assumed it could always find RingNet files named:

- `flame_static_embedding.pkl`
- `flame_dynamic_embedding.npy`

Observed error:

```text
AssertionError: flame_static_embedding.pkl ... 찾지 못함
```

Final fix:

- use an existing `landmark_embedding.npy` when the user has one;
- otherwise download the FLAME-compatible embedding from pinned DECA commit;
- verify SHA-256;
- verify required keys:
  - `static_lmk_faces_idx`
  - `static_lmk_bary_coords`
  - `dynamic_lmk_faces_idx`
  - `dynamic_lmk_bary_coords`

The final V4 notebook contains the complete corrected installer.

### 5.4 Runtime loss during manual recovery

A manual embedding-only recovery cell later failed with:

```text
FileNotFoundError: .../FLAME2020/landmark_embedding.npy
AssertionError: .../FLAME2020/generic_model.pkl
```

Cause:

- the Colab runtime process had changed;
- `/content/.../FLAME2020` and previously copied model assets no longer existed;
- downloading only the missing embedding could not reconstruct the other FLAME assets.

Final rule:

- after a runtime loss, rerun the complete corrected FLAME installation cell, not a single-file recovery fragment.

### 5.5 Legacy FaceBoxes import

Observed error from V4 crop helper:

```text
ModuleNotFoundError: No module named 'detector'
```

Cause:

- `FaceBoxesV2/faceboxes_detector.py` uses legacy absolute import `from detector import Detector`;
- official `run_cropping.py` first appends the FaceBoxesV2 folder to `sys.path`;
- the first V4 embedded helper omitted that setup.

Final fix:

```python
import sys
from pixel3dmm import env_paths

faceboxes_dir = (
    f'{env_paths.CODE_BASE}/src/pixel3dmm/'
    'preprocessing/PIPNet/FaceBoxesV2'
)
if faceboxes_dir not in sys.path:
    sys.path.insert(0, faceboxes_dir)

from faceboxes_detector import FaceBoxesDetector
```

`conda run --no-capture-output` is used so nested Python errors remain visible.

### 5.6 Wrong primary-face selection in image 00007

First custom selection hypothesis:

```text
0.70 * relative area + 0.20 * confidence + 0.10 * centrality
```

Live visual failure:

- 7 crops were correct;
- image `00007` selected a large chest/neck false positive instead of the profile face;
- FaceBoxes had actually detected the correct face as another candidate.

Recorded candidates:

| Candidate | Meaning | FaceBoxes confidence | Relative area | Old selection score |
| --- | --- | ---: | ---: | ---: |
| 0 | actual profile face | `0.9352349` | `0.5601853` | `0.6665744` |
| 1 | chest/neck false positive | `0.7161046` | `1.0` | `0.8933956` |

Conclusion:

- FaceBoxes itself preferred the correct face;
- the custom area-heavy ranking reversed the correct decision;
- the first baseline should match official `pipnet_utils.py` and select by FaceBoxes confidence.

Final selection:

```python
score = confidence
```

Area and centrality remain in metadata for diagnostics and future identity-aware tie-breaking. After this change, `00007` selected the real face at confidence `0.935` and Gate A passed 8/8.

### 5.7 Upstream static crop bug

Original official preprocessing used `static_crop=True` for a sequence and averaged bbox coordinates across frames. That is acceptable for a continuous video with one coordinate system but wrong for independent photos with different resolutions and face positions.

Live symptom before V4:

- some crops showed only the eyes/forehead;
- nose, mouth and chin were cut off;
- downstream FaRL detection failed in several frames.

V4 fix:

- detect and crop every photo independently;
- preserve one final crop coordinate system per photo;
- never average absolute source-pixel bbox coordinates across independent images.

### 5.8 PIPNet and FaRL preprocessing

PIPNet live result:

- 8/8 images exported landmarks;
- FaceBoxes confidence inside final crops ranged approximately `0.987–0.999`;
- official WFLW 98 `.npy` and annotated images were produced.

FaRL first attempt failed before inference while downloading its 617MB JIT weight.

Observed error:

```text
ConnectionResetError: [Errno 104] Connection reset by peer
```

Download stopped at roughly 361MB/617MB.

Recovery:

```bash
DIR=/root/.cache/torch/hub/checkpoints
NAME=face_parsing.farl.celebm.main_ema_181500_jit.pt
URL=https://github.com/FacePerceiver/facer/releases/download/models-v1/$NAME
TARGET=$DIR/$NAME
PART=$TARGET.part

mkdir -p "$DIR"
rm -f "$TARGET"
touch "$PART"
curl -L --fail \
  --retry 20 \
  --retry-all-errors \
  --retry-delay 2 \
  --connect-timeout 30 \
  --continue-at - \
  --output "$PART" \
  "$URL"
mv "$PART" "$TARGET"

conda run --no-capture-output -n p3dmm python -c \
"import torch; torch.jit.load('$TARGET', map_location='cpu'); print('FaRL JIT weight: PASS')"
```

Then only segmentation was rerun:

```bash
conda run --no-capture-output -n p3dmm \
  python /content/pixel3dmm/scripts/run_facer_segmentation.py \
  --video_name inputs
```

Final count gate:

```text
input/crop/meta/landmark/annotated/seg: 8 8 8 8 8 8
PREPROCESSING COMPLETE: PASS
```

The final V4 notebook pre-downloads the FaRL weight with retry/resume and validates `torch.jit.load` during dependency setup.

### 5.9 Other hardened compatibility fixes already in V4

These were discovered in the earlier safe-notebook run and carried into V4.

- replace upstream SSH dependency clones with HTTPS clones;
- install Cython before building FaceBoxesV2;
- place UV and normal checkpoints in `/content/pixel3dmm/pretrained_weights`;
- patch Facer `images[data['image_ids']]` to use `.long()` tensor indices;
- skip MICA preprocessing when `ignore_mica=True`;
- patch tracker to use a zero MICA shape prior instead of reading missing `mica/*/identity.npy`;
- validate FLAME2020 and FLAME2023 assets before tracking;
- use dynamic tracking batch `min(number_of_views, 16)`;
- correct upstream README's duplicate `iters=100 iters=1500` to `iters=100 global_iters=1500`;
- validate normal/UV output counts because upstream inference catches frame exceptions and continues;
- save raw logs and run manifests to Drive;
- lower PIPNet crop re-detection gate from `0.99` to `0.75` but require output-count and visual gates;
- preserve PIPNet's temporary internal ROI while preventing it from overwriting the V4 persistent crop.

### 5.10 Current normal/UV checkpoint error

The latest live error is the PyTorch `weights_only` change described in Section 2.

Exact live patch to run next:

```python
from pathlib import Path

path = Path('/content/pixel3dmm/scripts/network_inference.py')
text = path.read_text()

old = (
    'model = p3dmm_system.load_from_checkpoint('
    'model_checkpoint, strict=False)'
)
new = (
    'model = p3dmm_system.load_from_checkpoint('
    'model_checkpoint, strict=False, weights_only=False)'
)

assert old in text or new in text
path.write_text(text.replace(old, new))
assert new in path.read_text()
print('Pixel3DMM trusted checkpoint patch: PASS')
```

The repository V4 notebook already applies this patch automatically in its compatibility-patch cell. The current live runtime still needs the patch cell above because it was launched from the earlier uploaded notebook.

## 6. Crop v1–v3 Historical Experiments

The following experiments explain why roll normalization was removed from the default. Their standalone code, tests, and crop-only notebooks were deleted from the active repository on 2026-06-24; this table, `docs/history.md`, docs 12, and Git history preserve the reasoning.

| Version | Core idea | Result |
| --- | --- | --- |
| v1 | RetinaFace bbox + two-eye roll | bbox/scale improved, profile eye points invalid |
| v2 | five-point plausibility gate, profile roll skip, validity mask | safer warnings, no decisive visual improvement |
| v3 | nose-anchor five-point least-squares roll | math tests passed, sparse alignment points were not exact pupil/nose-tip/mouth-corner points |

All synthetic unit tests passed at the time, but these engines are not the V4 Pixel3DMM default. Restore them from Git history only if a concrete future A/B experiment needs them.

## 7. Drive Artifact Bundle

V4 sections 7.3 and 7.4 preserve preprocessing output under a timestamped private folder:

```text
MyDrive/hair_app/runs/
  pixel3dmm_v4_preprocessing_{VID_NAME}_{UTC}/
```

Expected content:

```text
raw_inputs/                     # immutable copies used for this run
rgb/                            # official-style final network input
cropped/                        # final 512 no-roll crops
crop_meta/
  manifest.json                 # all candidate boxes, selected face, warnings
  00000.json ...                # source size, bbox, matrices, provenance
PIPnet_landmarks/
  00000.npy ...                 # original normalized WFLW 98 points
PIPnet_annotated_images/        # 98-point visual overlays
pipnet/test.npy                 # combined upstream PIPNet output
landmarks_json/
  00000.json ...                # readable per-frame 98 points
landmarks_all.json              # all frames combined
landmarks_long.csv              # 8 * 98 = 784 long-form rows
seg_og/                         # raw FaRL label IDs
seg_non_crop_annotations/       # colored FaRL previews
segmentation_statistics.json    # per-frame label pixel counts/ratios
preprocessing_overview.png      # 8-row crop/landmark/segmentation gate
logs/                           # preprocessing logs
README_PRIVATE.txt
preprocessing_summary.json
preprocessing_bundle_manifest.json
artifact_sha256.json            # size and SHA-256 per saved file
```

Coordinate contract for landmark JSON/CSV:

- topology: PIPNet WFLW 98, indices 0–97;
- normalized coordinates are relative to the final 512 crop;
- origin is top-left;
- x increases right, y increases down;
- pixel coordinates are `normalized * 512`;
- crop metadata contains source→crop and crop→source 3×3 matrices.

Privacy:

- this bundle is biometric-sensitive private data;
- it belongs only in the user's private Drive or another approved private store;
- it must never be committed to this repository;
- training use requires a separate opt-in.

## 8. Notebook Sections

Latest V4 has the following major sections.

1. GPU/CUDA arch detection.
2. Conda installation and expected restart.
3. audited Pixel3DMM checkout.
4. CUDA extension/environment build.
5. preprocessing dependencies and checkpoints.
6. Drive and robust FLAME asset installation.
7. private input setup.
8. per-image no-roll FaceBoxes crop.
9. Gate A source/crop visualization.
10. PIPNet 98 and FaRL segmentation.
11. count/visual gate.
12. basic Drive preprocessing save.
13. complete reproducibility bundle.
14. approval gate.
15. normal/UV inference and count validation.
16. multi-image FLAME tracking.
17. mesh preview.
18. final logs/results/manifest save.
19. scoring.

The notebook intentionally stops at the human gate until:

```python
PREPROCESSING_APPROVED = True
```

## 9. Validation Already Performed

### Local repository validation

- every new notebook parses as JSON;
- V4 pure-Python cells and embedded helper scripts parse with `ast.parse`;
- V4 contains no saved private notebook outputs;
- no private source filename, local clipboard path, or private image bytes are stored in tracked experiment files;
- V4 crop geometry/source↔crop round-trip contract test passed;
- v1 unit tests: 3 passed;
- v2 unit tests: 5 passed;
- v3 unit tests: 5 passed;
- `git diff --check` passes apart from informational Windows LF/CRLF warnings.

### Live Colab validation

- environment/core imports passed;
- `ALL FLAME ASSETS: PASS` was reached in the corrected flow;
- V4 crop 8/8 generated;
- Gate A visual 8/8 passed after confidence-first selection;
- PIPNet landmark and overlay 8/8 generated;
- FaRL segmentation 8/8 generated after robust weight download;
- preprocessing count gate 8/8/8/8/8/8 passed;
- preprocessing bundle was reported saved;
- normal/UV has not yet passed because the last compatibility patch still needs a live rerun.

## 10. Known Limitations and Open Follow-ups

- A single output-count pass does not prove all 98 points are equally reliable under hand/product/headphone/hair occlusion.
- FaRL does not provide a complete general obstacle model. A later Hair App module should preserve hand/object/unknown occlusion masks and regional confidence.
- `multiple_faces_detected` remains a diagnostic. Confidence-first fixed the current false positive, but a real second person with higher confidence will require identity-aware selection.
- Hidden scalp/rear geometry is still a FLAME/Pixel3DMM prior, not measured truth.
- `ignore_mica=True` currently uses a zero shape prior; after first geometry baseline, compare a correct MICA-enabled run.
- Pixel3DMM and FLAME-related research assets require separate license review before commercial use.
- no normal, UV, tracked mesh, GLB, UV texture, or hair result has been completed yet.

## 11. Resume Procedure

### 11.1 Current Colab runtime still alive

Do not rerun the earlier crop or full preprocessing cells. They already produced and saved valid results.

Run exactly this patch cell:

```python
from pathlib import Path

path = Path('/content/pixel3dmm/scripts/network_inference.py')
text = path.read_text()
old = 'model = p3dmm_system.load_from_checkpoint(model_checkpoint, strict=False)'
new = 'model = p3dmm_system.load_from_checkpoint(model_checkpoint, strict=False, weights_only=False)'
assert old in text or new in text
path.write_text(text.replace(old, new))
assert new in path.read_text()
print('Pixel3DMM trusted checkpoint patch: PASS')
```

Then rerun notebook section 8's normal/UV bash cell:

```bash
%%bash -s "$VID_NAME"
set -euo pipefail
cd /content/pixel3dmm
conda run -n p3dmm python scripts/network_inference.py model.prediction_type=normals video_name="$1" 2>&1 | tee /content/p3dmm_normals.log
conda run -n p3dmm python scripts/network_inference.py model.prediction_type=uv_map video_name="$1" 2>&1 | tee /content/p3dmm_uv.log
```

Do not run tracking yet. Run the immediately following count cell and require:

```text
expected/normals/uv: 8 8 8
network inference completeness: PASS
```

If it fails, save and inspect:

- `/content/p3dmm_normals.log`
- `/content/p3dmm_uv.log`
- first traceback in either log;
- counts under `p3dmm/normals` and `p3dmm/uv_map`.

If Gate D passes, proceed to section 9 tracking with the existing dynamic batch and corrected `global_iters` arguments.

### 11.2 Colab runtime was lost

1. Use `experiments/milestone1_geometry_bakeoff/pixel3dmm_colab_v4.ipynb` from the latest `main` branch.
2. Connect A100 or H100.
3. Run all once; the condacolab restart is expected.
4. After restart, run all again from the environment check.
5. The notebook now contains all fixes listed in this document:
   - Drive/FLAME distribution handling;
   - pinned DECA embedding and SHA verification;
   - FaceBoxes import path;
   - confidence-first face selection;
   - FaRL retry/resume and JIT verification;
   - PyTorch `weights_only=False` compatibility for trusted official checkpoints;
   - Drive save bundles.
6. At the visual gate, inspect all 8 rows and set `PREPROCESSING_APPROVED=True` only if valid.
7. Continue through normal/UV, count gate, tracking, mesh preview and final save.

### 11.3 After normal/UV succeeds

Run tracking only after Gate D count passes. Expected command is already in V4:

```text
iters=100
global_iters=1500
batch_size=min(number_of_views,16)
include_neck=False
w_exp=0.1
use_mouth_lmk=False
w_shape=0.01
w_shape_general=0.001
normal_super=2000.0
sil_super=1000.0
use_flame2023=True
ignore_mica=True
is_discontinuous=True
```

Then:

1. confirm a non-empty `.ply` or `.obj` exists;
2. inspect the interactive neutral-gray mesh preview;
3. save mesh, raw logs, crop manifest, exact config and commit to Drive;
4. record scores in `scoring_sheet.csv`;
5. compare the same input set with KaoLRM before selecting a temporary geometry baseline.

## 12. Active Repository Files After Cleanup

Primary implementation:

- `experiments/milestone1_geometry_bakeoff/pixel3dmm_colab_v4.ipynb`
- `experiments/milestone1_geometry_bakeoff/README.md`

Only `pixel3dmm_colab_v4.ipynb` remains as an executable notebook. Earlier Pixel3DMM notebooks, the KaoLRM scaffold, and crop v1~v3 implementation/test notebooks were removed on 2026-06-24 because they were superseded. Their historical conclusions remain in this document, `docs/history.md`, docs 12, and Git history.

Documentation:

- `docs/04_scan_pipeline.md`
- `docs/10_3d_hair_app_master_plan.md`
- `docs/history.md`
- `docs/12_pixel3dmm_preprocessing_contract.md`
- this document;
- `newchat.md`.

No private photos, landmark outputs, masks, meshes, Drive run folders or notebook outputs are committed.

## 13. Decision Summary

Current temporary preprocessing decision:

```text
official FaceBoxes per-image crop
+ confidence-first candidate selection
+ margin 1.42
+ 512x512
+ no roll
+ official PIPNet WFLW 98
+ official FaRL CelebM segmentation
+ explicit count and human visual gates
```

This decision is not permanent. It stays only while it produces better downstream normal/UV/tracking results than alternatives. The next evidence needed is the first successful normal/UV and tracked mesh from this exact 8-photo set.
