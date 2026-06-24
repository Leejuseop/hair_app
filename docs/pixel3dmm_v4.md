# Pixel3DMM V4 Baseline: Contract, Live Results, and Next Experiments

Last synchronized: 2026-06-24

Status: **A100 end-to-end V4 baseline complete; MICA rejected; private 19-view run generated geometry, but cross-context landmarks did not validate the no-MICA identity shape over the refitted mean-shape control**

Executable notebook: `experiments/milestone1_geometry_bakeoff/pixel3dmm_colab_v4.ipynb`

Audited Pixel3DMM commit: `fcd1fa973c7715b02a8948dfc679dff53cf85924`

## 1. Why the Notebook and This Document Are Separate

The notebook and this document both use the name V4, but they do not duplicate the same role.

- `pixel3dmm_colab_v4.ipynb` is the executable, output-free Colab pipeline.
- This file is the human-readable contract, source audit, error history, measured result, interpretation, and next experiment plan.
- Private input photos, crops, landmarks, masks, predicted maps, meshes, videos, and Drive run folders stay outside Git.

Keeping executable code under `experiments/` and long-lived knowledge under `docs/` makes it possible to rerun the experiment without embedding private outputs in the repository. All former Pixel3DMM preprocessing, live-run, and experiment README material has been consolidated here.

## 2. Executive Result

The first complete Hair App Pixel3DMM baseline now works from eight independent photos through a reproducible FLAME geometry artifact. The mesh is useful, but the later mean-shape control means it should not yet be called a strongly validated personalized head.

```text
8 source photos
  -> 8 independent 512x512 no-roll face crops
  -> 8 PIPNet WFLW-98 landmark sets
  -> 8 FaRL face-part segmentations
  -> 8 predicted normal maps
  -> 8 predicted UV correspondence maps
  -> joint multi-photo FLAME tracking
  -> canonical.ply + per-view tracking renders
```

Confirmed live on an NVIDIA A100-SXM4-80GB:

- environment and CUDA extension checks passed;
- all required FLAME assets passed;
- crop passed 8/8;
- PIPNet WFLW-98 landmarks passed 8/8;
- FaRL segmentation passed 8/8;
- normal inference passed 8/8;
- UV inference passed 8/8;
- multi-photo tracking completed;
- `canonical.ply` contains 5,023 vertices and 9,976 faces;
- official tracking result video and all eight source/fitted overlays were visually inspected;
- the fitted identity shape beat the mean FLAME shape in the quick landmark diagnostic on all 8/8 views.

The correct conclusion is:

> V4 is a successful, reproducible first geometry baseline. It demonstrably personalizes the mean FLAME head, but it does not yet prove production-grade identity or measured hidden-scalp accuracy.

## 3. Exact Live Configuration

### 3.1 Runtime and pinned components

| Component | Version, commit, or source |
| --- | --- |
| Pixel3DMM | `fcd1fa973c7715b02a8948dfc679dff53cf85924` |
| Python environment | conda `p3dmm`, Python 3.9 |
| PyTorch | `2.7.0+cu118` |
| torchvision | `0.22.0+cu118` |
| torchaudio | `2.7.0+cu118` |
| PyTorch3D | `75ebeeaea0908c5527e7b1e305fbc7681382db47` |
| nvdiffrast | `253ac4fcea7de5f396371124af597e6cc957bfae` |
| Facer | `ddd35c76ff840174b8a5403ad1c1255e37b8782b` |
| PIPNet | `b9eab58816437403a34aa5bc3adeafe5081fd36b` |
| Landmark embedding fallback | pinned DECA commit `a11554ae2a2b0f3998cf1fa94dd4db03babb34a2` |
| DECA embedding SHA-256 | `8095348eeafce5a02f6bd8765146307f9567a3f03b316d788a2e47336d667954` |
| GPU used | NVIDIA A100-SXM4-80GB |

The user also has H100 access. Compute availability allows higher-resolution and fine-tuning experiments, but it does not recover unobserved scalp geometry, correct a wrong representation, resolve licenses, or replace data quality.

### 3.2 Final crop and preprocessing configuration

| Item | V4 value |
| --- | --- |
| Face detector | official FaceBoxesV2 |
| Candidate selection | highest FaceBoxes confidence |
| Processing unit | every source photo independently |
| Requested square margin | `1.42` |
| Persistent crop | `512x512` |
| Roll normalization | disabled |
| Landmark topology | PIPNet WFLW 98 |
| Segmentation | FaRL `celebm/448` |
| Source type | independent/discontinuous photos |

### 3.3 Tracking configuration used for the baseline

```text
iters=100
global_iters=1500
batch_size=8
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

The resulting run folder name contained `_noMICA_uv2000.0_n2000.0`. `ignore_mica=True` is important: the current result starts without a MICA identity prior and became the control for the MICA A/B tests. Those follow-ups did not pass the adoption gate, so this no-MICA run remains the active measured baseline.

## 4. What Each Intermediate Output Means

### 4.1 Crop

The crop does not reconstruct the face. It creates a stable per-photo coordinate frame with comparable face scale and enough forehead, jaw, and side context for the downstream networks.

### 4.2 PIPNet WFLW-98 landmarks

The 98 landmarks describe two-dimensional face feature locations on each final crop. They include face contour, brows, eyes, nose, mouth, and two iris-related points. They support camera, pose, expression, and selected landmark losses; they are not the complete 3D answer.

### 4.3 FaRL segmentation

The colored preview is a semantic face-part label map, not a UV map. It separates regions such as skin, hair, eyes, brows, nose, lips, and background. Pixel3DMM primarily uses it to obtain face silhouette and valid-region evidence.

### 4.4 Predicted normal map

A normal map predicts the direction that each visible surface point faces. It provides local 3D shape evidence: nose curvature, cheek orientation, brow depth, and other surface changes. The RGB-like colors encode directions, not skin color.

### 4.5 Predicted UV map

The Pixel3DMM UV prediction is a dense correspondence map. For each visible image pixel it predicts where that point belongs on the canonical FLAME face surface. It answers “which canonical face point is this pixel?” rather than “what skin color should this point have?”

This is different from the future Hair App face texture. The future UV baker will use camera, visibility, and these surface correspondences to project actual photographed pixels into a common texture atlas.

### 4.6 FLAME tracking

The tracker jointly adjusts:

- one shared identity shape across all photos;
- a separate camera for each photo;
- separate head and jaw pose for each photo;
- separate expression parameters for each photo.

It repeatedly renders the current FLAME estimate and compares it with observed or predicted evidence. The user does not provide a ground-truth 3D head; normal, UV, silhouette, and landmark agreement provide self-supervised fitting targets.

## 5. Official Source Audit and Why the Crop Was Changed

### 5.1 Official order

The audited upstream order is conceptually:

```text
input frames
  -> FaceBoxes crop
  -> PIPNet WFLW-98
  -> FaRL segmentation
  -> Pixel3DMM normal/UV network
  -> FLAME optimization
```

There are three different landmark roles that must not be confused:

1. **Crop detection:** FaceBoxes locates a face box before the persistent crop.
2. **Fitting landmarks:** PIPNet produces WFLW-98 on the final crop.
3. **Rendered landmarks:** FLAME projects its own 3D landmark embedding into each camera so the tracker can compare prediction and observation.

### 5.2 Why an apparent second crop exists

PIPNet/FaRL may perform a temporary internal re-detection and alignment because FaRL expects a `448x448` aligned face ROI. That temporary ROI is only a network input transform. Its segmentation result is mapped back to the persistent `512x512` crop coordinate system.

V4 therefore preserves two different concepts:

- one persistent, saved `512x512` crop used by the full pipeline;
- temporary internal ROIs that may be used by PIPNet/FaRL but never overwrite the persistent crop.

### 5.3 Root cause of the original broken crops

Upstream `static_crop=True` can average face boxes across frames of one continuous video, where every frame shares a coordinate system. Hair App supplied independent photos with different resolutions, locations, zooms, and orientations. Averaging absolute source-pixel boxes across those photos produced invalid crops: some images retained only eyes and forehead while nose, mouth, and chin were cut away.

The final fix is not a new face reconstruction model. It is an adapter that keeps the official FaceBoxes detector but processes each independent photo independently.

### 5.4 Why V4 does not rotate the persistent crop

Crop v1 through v3 tried to normalize roll before PIPNet:

| Version | Idea | What was learned |
| --- | --- | --- |
| v1 | RetinaFace box plus two-eye roll | box and scale improved, but sparse profile eye points were unreliable |
| v2 | five-point plausibility and profile skip | safer warnings, no decisive visual gain |
| v3 | nose-anchored five-point least-squares roll | geometry tests passed, but the sparse points were not exact pupil center, nose tip, and mouth corners |

The main problem was landmark semantics, not the angle formula. Pixel3DMM already estimates camera/head rotation after accurate PIPNet landmarks are available. Rotating the persistent input with weaker crop-time landmarks added interpolation and coordinate transforms without proven downstream benefit.

Current default:

> Normalize face location and scale once, preserve image-plane roll, then let PIPNet and the tracker estimate pose in the stage designed for it.

Roll normalization can return only as a controlled A/B test if downstream evidence shows that no-roll inputs fail.

## 6. Final V4 Preprocessing Contract

```text
private source photo
  -> apply EXIF orientation
  -> run FaceBoxes independently
  -> choose highest-confidence candidate
  -> save every candidate for diagnostics
  -> build a square box with requested margin 1.42
  -> move the square inside source bounds
  -> reduce margin only when the source is physically too tight
  -> resize once to 512x512
  -> do not rotate
  -> save source<->crop matrices and warnings
  -> run PIPNet WFLW-98
  -> run FaRL segmentation
  -> count and human visual gate
```

Candidate area and center scores remain metadata only. They must not outweigh detector confidence without a measured identity-aware selection strategy.

Obstacles such as hair, hands, a phone, headphones, hats, or a product are not automatic crop failures. Crop should locate the intended face; later segmentation and confidence logic should mark obstructed regions and reduce their geometry/texture weight. If two real people appear, confidence alone may select the wrong identity, so production capture will need identity continuity or explicit user confirmation.

### 6.1 Coordinate and metadata contract

- persistent crop size: `512x512`;
- crop origin: top-left;
- x increases right and y increases down;
- PIPNet normalized points are relative to the final crop;
- pixel position is `normalized_coordinate * 512`;
- every frame stores source size, chosen box, all candidates, warnings, and source-to-crop/crop-to-source `3x3` transforms;
- every derived artifact retains the source ID and pipeline version.

## 7. Live Error and Fix Record

This section records the failures that materially changed V4. It is intentionally detailed so a later runtime failure is not rediscovered from scratch.

### 7.1 Conda restart and ephemeral Colab state

`condacolab.install()` restarts Python. A full runtime loss also removes the conda environment, cloned repositories, `/content` assets, and generated outputs. Drive persists.

Rule: after a full runtime loss, run the complete notebook setup and complete FLAME installer again. Do not run a one-file recovery fragment against missing directories.

### 7.2 Google Drive mount

Observed:

```text
ValueError: mount failed
```

Recovery:

```python
from google.colab import drive
drive.mount('/content/drive', force_remount=True, timeout_ms=120000)
```

This was authentication/mount state, not a Pixel3DMM failure.

### 7.3 FLAME distribution mismatch

Drive contained `FLAME2020.zip`, `FLAME2023.zip`, and `FLAME_masks.zip`, but no ready `landmark_embedding.npy`. Earlier code incorrectly assumed it would always find RingNet files named `flame_static_embedding.pkl` and `flame_dynamic_embedding.npy`.

Observed:

```text
AssertionError: flame_static_embedding.pkl ... 찾지 못함
```

Final installer behavior:

1. extract valid FLAME archives;
2. install `generic_model.pkl`, `flame2023_no_jaw.pkl`, and `FLAME_masks.pkl`;
3. reuse an existing valid `landmark_embedding.npy` if present;
4. otherwise download the pinned DECA embedding;
5. verify its SHA-256 and the four required static/dynamic face-index and barycentric-coordinate keys;
6. assert every required asset exists before tracking.

### 7.4 Runtime loss during manual embedding recovery

Observed:

```text
FileNotFoundError: .../FLAME2020/landmark_embedding.npy
AssertionError: .../FLAME2020/generic_model.pkl
```

The runtime had changed and the destination directory plus other FLAME files were gone. Final rule: rerun the complete asset cell, not the failed embedding-only cell.

### 7.5 FaceBoxes legacy import

Observed:

```text
ModuleNotFoundError: No module named 'detector'
```

The legacy module uses `from detector import Detector`. V4 now adds the official `FaceBoxesV2` directory to `sys.path` before importing `faceboxes_detector`. Nested commands use `conda run --no-capture-output` so the real traceback remains visible.

### 7.6 Wrong face selected in the last profile image

The first custom score used `0.70 * area + 0.20 * confidence + 0.10 * centrality`. It selected a large chest/neck false positive instead of the face.

| Candidate | Meaning | Confidence | Relative area | Old score |
| --- | --- | ---: | ---: | ---: |
| 0 | actual profile face | `0.9352349` | `0.5601853` | `0.6665744` |
| 1 | chest/neck false positive | `0.7161046` | `1.0` | `0.8933956` |

FaceBoxes itself had ranked the face correctly. V4 reverted to official-like highest-confidence selection, retained other scores only as metadata, and passed 8/8 crops.

### 7.7 FaRL weight download interruption

Observed while downloading the approximately 617 MB JIT weight:

```text
ConnectionResetError: [Errno 104] Connection reset by peer
```

V4 now uses a resumable `curl` download with retries, writes to `.part`, moves only after completion, and validates the checkpoint with `torch.jit.load` before inference. The live retry produced segmentation 8/8.

### 7.8 PyTorch 2.6+ Lightning checkpoint behavior

Observed before normal inference:

```text
_pickle.UnpicklingError: Weights only load failed.
Unsupported global: GLOBAL omegaconf.dictconfig.DictConfig
```

PyTorch changed the default of `torch.load(weights_only=...)` to `True`. The official Lightning checkpoint includes trusted OmegaConf objects. V4 patches only the pinned official Pixel3DMM load:

```python
model = p3dmm_system.load_from_checkpoint(
    model_checkpoint,
    strict=False,
    weights_only=False,
)
```

This must never be generalized to unknown user-supplied checkpoints. After this fix, normal and UV inference succeeded 8/8.

### 7.9 Mesh preview package installed into the wrong interpreter

Observed after successful tracking:

```text
ModuleNotFoundError: No module named 'trimesh'
```

Both `!pip` and `%pip` could point at a different interpreter than the active notebook kernel after the conda/Colab setup. V4 now installs with the exact active interpreter:

```python
import sys, subprocess, importlib
subprocess.check_call([
    sys.executable, '-m', 'pip', 'install',
    '--no-cache-dir', '--upgrade', 'trimesh', 'plotly'
])
importlib.invalidate_caches()
```

The first Plotly view also used an unhelpful default camera and flat gray shading. That made a valid sideways face hard to inspect; it was a visualization issue, not evidence that tracking had failed. The official tracking video and fixed-view comparisons are the stronger visual gate.

### 7.10 Other compatibility hardening retained in V4

- use HTTPS rather than unavailable SSH dependency clones;
- install Cython before FaceBoxesV2 build;
- place normal and UV checkpoints in upstream-expected paths;
- cast Facer image indices to `.long()`;
- skip MICA preprocessing when `ignore_mica=True`;
- supply a zero MICA shape prior in the no-MICA control;
- use `batch_size=min(number_of_views, 16)`;
- correct duplicated upstream `iters` argument to `iters=100 global_iters=1500`;
- validate normal/UV output counts because upstream inference can catch a frame exception and continue;
- lower crop-internal PIPNet re-detection gate from `0.99` to `0.75`, while retaining count and visual gates;
- save raw logs, exact configuration, provenance, hashes, and environment information to Drive.

## 8. Generated Artifact Contract

The private preprocessing bundle is stored under a timestamped folder such as:

```text
MyDrive/hair_app/runs/
  pixel3dmm_v4_preprocessing_{VID_NAME}_{UTC}/
```

The final full-run save copies the tracking result and the complete preprocessed actor. The user reported that the save workflow completed, but the exact final printed Drive directory was not pasted into chat; it must be read from the Colab variable/output or checked in Drive rather than guessed.

Expected private artifacts include:

```text
raw_inputs/
rgb/
cropped/
crop_meta/
  manifest.json
  00000.json ...
PIPnet_landmarks/
PIPnet_annotated_images/
pipnet/test.npy
landmarks_json/
landmarks_all.json
landmarks_long.csv
seg_og/
seg_non_crop_annotations/
segmentation_statistics.json
preprocessing_overview.png
p3dmm/
  normals/
  uv_map/
tracking result folder/
  mesh/canonical.ply
  result.mp4
logs/
environment and exact config
manifest and SHA-256 inventory
```

None of these biometric artifacts belongs in Git. Training use requires separate opt-in.

## 9. Geometry Validation Results

### 9.1 Mean FLAME versus fitted mesh displacement

After removing global translation by centroid alignment, vertex displacement from the mean FLAME shape to the fitted identity shape was:

| Metric | Result |
| --- | ---: |
| Mean displacement | `3.73 mm` |
| RMS displacement | `5.50 mm` |
| 95th percentile | `11.37 mm` |
| Maximum | `25.02 mm` |

Interpretation:

- the optimizer did not simply return the untouched mean FLAME head;
- visible changes in face depth and profile are substantial enough to treat the result as personalized;
- the largest values can occur at neck/scalp boundary regions and are not automatically identity improvements;
- displacement magnitude alone cannot prove that the changes are correct.

### 9.2 Same-camera shape-swap landmark diagnostic

The fitted identity and mean FLAME identity were rendered with the fitted run's same per-view camera, pose, and expression, then compared against PIPNet landmarks.

```json
{
  "views": 8,
  "mean_flame_average_error_px": 7.110900421740904,
  "fitted_average_error_px": 5.880312144215164,
  "average_improvement_px": 1.2305882775257402,
  "fitted_wins_views": 8,
  "mean_wins_views": 0
}
```

This is an average improvement of approximately `17.3%`, and the fitted shape won in every view. It confirms that the fitted identity explains the observed landmark locations better under the same cameras, poses, and expressions.

Limitation:

> This is a quick shape-swap diagnostic, not a fully fair independent baseline. A fairer comparison must rerun optimization with identity shape fixed to zero so camera, pose, and expression can refit for the mean-shape control.

The fully refitted mean-shape control was then run. Identity shape was forced to zero while camera, pose, expression, jaw, eyes, eyelids, and intrinsics were allowed to refit. The result was:

```json
{
  "views": 8,
  "mean_shape_refit_average_error_px": 5.742349992829476,
  "previous_no_mica_fitted_shape_average_error_px": 5.880312144215164
}
```

In that run the validation script reports fitted and mean as identical because the fitted identity shape is intentionally zero. This weakens the earlier landmark-only personalization claim: mean FLAME can match or slightly beat the no-MICA fitted-shape landmark score once camera, pose, and expression are allowed to refit. The current no-MICA output remains a working end-to-end geometry artifact, but the optimized identity shape should not yet be described as strongly validated personal head geometry.

### 9.3 Visual inspection

The official result showed, for each of the eight views:

- original crop;
- fitted mesh over the source image;
- a rendered per-view fitted shape.

The third panel must not be mislabeled as the neutral canonical mesh: it includes the view's pose and expression. `canonical.ply` is the shared neutral identity mesh.

Observed result:

- alignment followed front, oblique, tilted, and profile views coherently;
- profile views showed meaningful nose, lips, chin, and cheek depth;
- expressions differed by input as expected because expression is per view;
- scalp and rear head remain prior-driven where photos contain no direct evidence.

### 9.4 Optimizer loss record

The exact final scalar values printed by `track.py` were not pasted into chat, so they are not reconstructed or invented here. The available quantitative result is the post-run landmark diagnostic above, not the tracker's raw training objective.

This distinction matters because the tracking objective is a weighted sum of UV, normal, silhouette, selected landmark, shape, expression, pose, camera, symmetry, and optional prior terms with different units. A lower total objective is meaningful only under the same configuration. Future A/B runs must copy the raw tracking log and export at least:

- final and best total objective;
- each named loss component;
- iteration of the best checkpoint;
- exact weights and optimization size;
- runtime and GPU;
- NaN/exception/frame-skip counts.

The MICA comparison must report both the same post-run geometry metrics and these raw component losses. Do not compare one condition's total loss with another condition if their weights or active terms differ.

## 10. What Losses Actually Drive the Fit

It is inaccurate to describe the baseline as simply “98 landmarks + UV + normal.” The tracker receives PIPNet-98, maps the topology for its own landmark use, but the audited code does not apply one equally weighted loss to all 98 points.

Current important evidence:

- dense predicted UV correspondence;
- predicted surface normals;
- FaRL-derived face silhouette and valid regions;
- active eye contour landmarks;
- eye-closure constraints;
- left and right iris constraints;
- optional mouth landmarks, disabled in the current run;
- regularizers for shape, general shape, expression, pose, camera, and symmetry;
- optional MICA identity prior, disabled in the current run.

The full 68-point landmark loss in the audited tracker is not the main active term in this baseline; selected regions are used. `use_mouth_lmk=False` and the default mouth landmark weight leave mouth evidence mostly to dense normal/UV/silhouette and regularization.

This distinction matters: merely changing “98 landmarks” to “478 landmarks” would not improve the fit unless the tracker defines robust correspondences, region weights, visibility, confidence, and loss terms for those points.

## 11. Current Limitations

- Eight successful outputs do not mean every PIPNet point is reliable under fingers, products, headphones, hair, or extreme profile.
- FaRL is a face parser, not a complete general obstacle segmenter.
- Highest-confidence selection can still choose a different real person if multiple people appear.
- The normal and UV networks currently save 8-bit PNG predictions, losing precision.
- The tracker default optimization size is 256 even though persistent crops are 512.
- FLAME has stable, useful topology but only 5,023 vertices and a limited identity subspace; it cannot represent every pore, eyelid fold, cartilage detail, or arbitrary scalp shape.
- `ignore_mica=True` removes a potentially valuable identity prior.
- The quick identity diagnostic holds camera, pose, and expression fixed and is not the fully refitted control.
- Hair-covered crown and rear scalp remain inferred. More facial landmarks cannot create evidence for invisible scalp.
- This result is geometry only. It does not yet include the Hair App observed-photo UV texture, hairstyle reconstruction, retargeting, collision correction, or GLB.
- Pixel3DMM, FLAME, and related research assets require a separate commercial-license path.

## 12. Improvement Roadmap

The next changes should be introduced one at a time against this frozen no-MICA baseline.

### Completed: MICA identity-prior and init-only A/B

The same eight images and same non-MICA settings were tested with MICA enabled.

MICA's role:

- estimate a photo-based FLAME identity shape initialization/prior;
- give Pixel3DMM a better starting identity than mean FLAME;
- allow dense normal/UV/silhouette evidence to refine it across all views.

Result: MICA is not adopted as the default geometry path for this baseline.

MICA prior run:

- MICA preprocessing completed 8/8;
- MICA tracking produced `canonical.ply`, eight per-view meshes, and a result video;
- canonical displacement versus no-MICA after centroid alignment: mean `4.2749 mm`, median `3.2221 mm`, p95 `8.0128 mm`, max `17.0235 mm`;
- in the no-MICA camera/pose/expression context, MICA shape worsened average landmark error from `5.8803 px` to `7.2801 px`, losing 8/8 views;
- in the MICA camera/pose/expression context, MICA shape improved `6.0530 px` to `5.7006 px`, winning 5/8 views;
- native-run comparison improved only `0.1797 px`, but this is not a fixed-context comparison.

MICA init-only run:

- no-MICA context: MICA init-only shape worsened `5.8803 px` to `7.2036 px`, losing 8/8 views;
- MICA init-only context: MICA shape improved `5.9761 px` to `5.7245 px`, winning 5/8 views;
- native-run comparison improved only `0.1558 px`.

Interpretation:

- MICA changes the final geometry, but the fixed-context test shows the no-MICA fitted shape is preferred under the original no-MICA solution;
- the small native-run gain appears to come largely from camera/pose/expression compensation around the MICA-shaped identity;
- profile and contour-heavy views are especially risky;
- MICA may remain a research reference, but it is not the default baseline for the current Hair App geometry path.

The comparison helper is `experiments/milestone1_geometry_bakeoff/validate_mica_vs_no_mica.py`.

### Priority 1: fully refitted mean-shape control

Completed. Rerun tracking with identity shape fixed to zero while allowing camera, pose, expression, jaw, eyes, eyelids, and intrinsics to optimize. The result matched or slightly beat the no-MICA fitted-shape landmark score, so it did not strengthen the personalization claim.

### Completed: cross-context no-MICA shape versus mean-shape validation

Completed for the private 19-view run. The no-MICA shape won slightly in its own fixed context but lost in the mean-shape context, so the identity-shape claim remains unvalidated by landmarks alone. The next test is not another geometry parameter change; it is a visual texture comparison across the frozen raw FLAME, fitted mean-shape control, and personal no-MICA candidates.

### Priority 2: observed-photo texture baker across the frozen model trio

Apply the same private photo evidence to the raw FLAME, fitted mean-shape control, and personal no-MICA meshes. Record coverage/confidence/provenance and compare textured renders before changing geometry settings.

### Priority 3: optimization resolution 256 versus 512

Run the same baseline at tracker size 512. The persistent images are already 512, but the default tracker downsamples. Compare identity, regional error, memory, and runtime. Do not assume 512 wins merely because it is larger.

### Priority 4: preserve prediction precision

Modify normal/UV inference to retain float32 `.npy` or a validated 16-bit format alongside preview PNGs. Record confidence when the network exposes it. Compare against the current 8-bit baseline.

### Priority 5: robust regional landmarks

Do not blindly add every MediaPipe point. Add tested regions with visibility and confidence:

- current eyes and irises;
- nose ridge/base;
- brows;
- jaw/contour only when visible;
- outer mouth and corners, preferably on neutral or high-confidence frames.

MediaPipe 478 is useful as a cross-check and possible dense regional source, but it needs an explicit mapping to FLAME or surface constraints. Candidate losses should use robust penalties and downweight occluded or inconsistent points.

### Priority 6: better masks and dense losses

- add a general occluder/unknown mask for hands, phones, products, glasses, headphones, and heavy hair;
- build per-region confidence instead of only accept/reject;
- use angular and multi-scale normal consistency;
- enforce multi-view UV correspondence consistency;
- avoid fitting silhouette to hair or objects;
- record which views support each surface region.

### Priority 7: fine-tune the normal/UV networks

Only after the baseline and A/B tests are understood:

- collect or legally generate Hair App-style multi-view data;
- include selfie lenses, makeup, varied skin tones, occlusion, profile, tilt, pulled-back hair, and real phone compression;
- fine-tune normal and UV predictors with fixed validation identities;
- measure downstream mesh improvement, not just map image loss.

### Priority 8: high-frequency face refinement

If FLAME identity is correct at low frequency but lacks detail, add a face-only displacement or higher-resolution refinement layer with smoothness, symmetry, and observation-confidence constraints. Keep the stable base topology for UV and hair fitting.

### Priority 9: acquire actual scalp evidence

Improve the capture protocol with pulled-back-hair front/temple/profile views, visible ears, crown/rear guidance, and optional depth or VGGT initialization. A head prior may still be necessary, but observed and inferred regions must be labeled separately.

## 13. Immediate Next Experiment

### 13.1 Private 19-view app-scan plus selfie run

Completed on 2026-06-24 in private Drive storage, not in Git:

- input set: selected user selfies plus app-selected scan frames;
- accepted clean views: `19`;
- no-MICA Pixel3DMM tracking completed;
- full no-MICA tracking folder was preserved;
- fully refitted mean-shape control completed with identity shape effectively zero;
- raw FLAME template, fitted mean-shape control, and personal no-MICA were visually compared side by side.

The mean-shape sanity check confirmed that the control was nearly zero identity shape:

```json
{
  "no_mica_shape_l2": 10.628931045532227,
  "mean_shape_l2": 4.09764743380947e-06,
  "shape_difference_l2": 10.62893009185791,
  "shape_param_count": 300
}
```

The cross-context landmark comparison reported:

```json
{
  "views": 19,
  "no_mica_context": {
    "no_mica_shape_error_px": 4.719309781745137,
    "mean_shape_error_px": 4.914750639977585,
    "no_mica_shape_gain_px": 0.19544085823244828
  },
  "mean_shape_context": {
    "no_mica_shape_error_px": 5.123912251678183,
    "mean_shape_error_px": 4.520063043559785,
    "no_mica_shape_gain_px": -0.6038492081183984
  },
  "no_mica_wins_both_contexts": false
}
```

Interpretation:

- the personal no-MICA mesh is visibly different from raw FLAME and from the fitted mean-shape control;
- the no-MICA candidate is still useful as a temporary development mesh;
- the landmark gate does not prove that no-MICA identity shape is better than a refitted mean shape;
- visual texture quality may still separate the three candidates, so the next experiment is to apply observed-photo face texture to all three frozen meshes before making a practical asset decision.

Private artifact rule:

- freeze the three mesh candidates in the private Drive run folder with `experiments/milestone1_geometry_bakeoff/freeze_model_trio_for_texture.py`;
- keep the generated PLY files, private manifest, source photos, tracking folders, textures, and overlays out of Git;
- commit only the generic helper, contract, metrics summary, and next-step plan.

### 13.2 Next experiment: observed-photo face texture baker

The next implementation milestone is not another geometry run. Build a custom texture/UV engine that projects the actual private photo pixels onto the three frozen mesh candidates:

1. load the frozen model trio from the private manifest;
2. load the corresponding preprocessed crops, PIPNet/FaRL masks, UV maps, and tracking cameras;
3. rasterize or otherwise map each visible mesh surface into each source photo;
4. accumulate observed pixels into a shared texture atlas with angle, resolution, segmentation, sharpness, exposure, occlusion, and multi-view consistency weights;
5. store coverage, confidence, source-view support, and observed-versus-completed masks;
6. apply the same baker to raw FLAME, fitted mean-shape control, and personal no-MICA;
7. compare textured renders visually and with reprojection/coverage metrics before choosing a temporary head asset.

Do not use a generative completion model as the first texture result. First preserve and inspect the raw observed-photo texture and its coverage map. Completion can fill missing regions only after the observed layer is reproducible.

The previous product-data geometry task is complete for the current private run. The new immediate task is texture:

1. freeze the three mesh candidates and their manifest in the private Drive run folder;
2. implement the first observed-photo texture baker in this repository;
3. run it against all three mesh candidates without changing the input photos;
4. inspect textured front, oblique, profile, and neutral turntable renders;
5. use the visual result plus coverage/confidence/reprojection diagnostics to decide whether the personal no-MICA candidate is worth carrying forward as the temporary head asset.

Only after that should the project return to geometry changes such as tracker size 512, high-precision maps, regional landmarks, or different identity constraints. Changing geometry and texture at the same time would make it unclear whether a visual improvement came from the mesh or the face appearance layer.

## 14. Notebook Run and Human Gates

The notebook intentionally includes explicit gates.

1. GPU and CUDA architecture check.
2. expected conda install/restart.
3. pinned repository checkout.
4. environment and CUDA extension build.
5. dependency/checkpoint setup.
6. Drive and complete FLAME asset installation.
7. private input discovery.
8. V4 independent no-roll crop.
9. source/crop visual gate.
10. PIPNet and FaRL.
11. preprocessing count/visual gate.
12. Drive preprocessing bundle.
13. `PREPROCESSING_APPROVED=True` only after human inspection.
14. normal/UV inference and exact count gate.
15. tracking.
16. mesh/result visualization.
17. full Drive save and manifest.
18. quantitative evaluation.

Do not bypass a failed count gate merely because later cells can technically run.

## 15. Repository and Privacy Rules

Active executable research file:

- `experiments/milestone1_geometry_bakeoff/pixel3dmm_colab_v4.ipynb`
- `experiments/milestone1_geometry_bakeoff/freeze_model_trio_for_texture.py`

Knowledge files:

- this document for all Pixel3DMM V4 details;
- `docs/10_3d_hair_app_master_plan.md` for the complete product and system plan;
- `docs/history.md` for chronological project decisions;
- `newchat.md` for the compact current handoff.

Removed crop v1/v2/v3 scripts, tests, crop-only notebooks, earlier Pixel3DMM notebooks, and the KaoLRM scaffold remain available in Git history only. Restore them only for a named controlled comparison.

Never commit:

- private photos or scans;
- crop/landmark/segmentation outputs;
- embeddings, meshes, textures, or tracking videos;
- private Drive paths containing identity information;
- notebook output cells containing user data.

## 16. Official Source Links

- Pixel3DMM repository: <https://github.com/SimonGiebenhain/pixel3dmm>
- audited tracker: <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/src/pixel3dmm/tracking/tracker.py>
- tracking configuration: <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/configs/tracking.yaml>
- network inference: <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/scripts/network_inference.py>
- FLAME wrapper: <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/src/pixel3dmm/tracking/flame/FLAME.py>

## 17. Decision Summary

Current temporary decision:

```text
official FaceBoxes per-photo crop
  + highest-confidence selection
  + margin 1.42
  + persistent 512x512 no-roll coordinate system
  + official PIPNet WFLW-98
  + official FaRL CelebM segmentation
  + Pixel3DMM normal and UV networks
  + no-MICA multi-photo FLAME tracking as the control baseline
```

The baseline is successful but replaceable. The stable target is an editable personal head with honest observed/inferred confidence, not permanent loyalty to Pixel3DMM or FLAME.
