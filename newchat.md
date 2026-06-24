# Hair App New-Chat Handoff

Last synchronized: 2026-06-24

Branch expected: `main`

Current architecture source of truth: `docs/10_3d_hair_app_master_plan.md`

Current experiment source of truth: `docs/pixel3dmm_v4.md`

Executable research notebook: `experiments/milestone1_geometry_bakeoff/pixel3dmm_colab_v4.ipynb`

Documentation consolidation status: committed and pushed to `main` on 2026-06-24 with this handoff; use `git log -1` for the exact immutable commit hash.

## 1. How to Resume

At the beginning of a new conversation:

1. run `git status --short --branch`;
2. read `AGENTS.md`;
3. read every tracked Markdown file;
4. inspect the actual code/notebook before trusting this handoff;
5. do not commit private biometric inputs or outputs.

Detailed Markdown is intentionally consolidated:

- `docs/10_3d_hair_app_master_plan.md`: complete product, current app/API/storage, personal-head asset, UV, hair, service, evaluation, privacy, and license plan;
- `docs/pixel3dmm_v4.md`: all Pixel3DMM source audit, crop contract, runtime errors/fixes, measured result, current losses, limitations, and next experiments;
- `docs/history.md`: full project chronology and portfolio-quality reasoning;
- this file: compact current handoff.

Root `README.md`, `AGENTS.md`, and `newchat.md` remain outside `docs/` because GitHub and coding agents discover them at the repository root.

## 2. Product Direction

Hair App targets a real editable 3D pipeline, not one isolated 2D edited image.

```text
multiple user photos + guided hairline/head scan
  -> reusable editable hairless head mesh
  -> observed multi-photo face UV texture

hairstyle reference image(s)
  -> independent 3D strand hair

head + hair
  -> hairline-aware scalp retargeting
  -> collision correction
  -> rotatable mobile GLB + optional renders
```

Current first-stack hypothesis:

- MediaPipe for capture guidance and low-cost checks;
- Pixel3DMM/FLAME for first geometry baseline;
- next MICA identity-prior A/B;
- optional VGGT camera/depth/point initialization;
- custom observed-pixel multi-photo UV baker;
- FreeUV versus simple completion only for missing UV;
- DiffLocks versus Im2Haircut/current alternatives for strand hair;
- custom scalp/root fitting and collision correction;
- Blender/server validation and GLB/Three.js delivery.

All model choices remain replaceable. FastAvatar is not current core because Gaussian output conflicts with editable UV mesh and independently replaceable hair. FLUX.2/2D work remains useful for quality benchmarks, auxiliary views, still-render refinement, and fallback.

## 3. Actual Product Implementation Boundary

Implemented in the app repository:

- React + Vite mobile web;
- browser camera and MediaPipe Face Landmarker;
- guided `front`, `left`, `right`, `hairline` capture;
- 20 accepted samples per step;
- FastAPI scan upload and file-based storage;
- `base_profile.json` version `0.1`;
- representative image, landmark, and hairline-guide previews.

Not implemented in the product:

- existing-selfie multi-upload and star UI;
- production 3D reconstruction worker/API;
- observed-photo UV baker/completion;
- style-reference persistence and strand hair;
- head/hair retargeting and collision;
- GPU job queue;
- GLB builder/viewer;
- production privacy/auth/deletion infrastructure.

Important: the Pixel3DMM result below is an offline research baseline. It is not connected to FastAPI or the frontend.

## 4. Pixel3DMM V4: Completed State

The only active executable notebook is:

```text
experiments/milestone1_geometry_bakeoff/pixel3dmm_colab_v4.ipynb
```

Audited Pixel3DMM commit:

```text
fcd1fa973c7715b02a8948dfc679dff53cf85924
```

Live A100 run on the same eight private photos completed end to end:

- official FaceBoxes per-photo, highest-confidence, margin `1.42`, `512x512`, no-roll crop: 8/8;
- PIPNet WFLW-98 landmarks: 8/8;
- FaRL CelebM segmentation: 8/8;
- Pixel3DMM normal inference: 8/8;
- Pixel3DMM UV correspondence inference: 8/8;
- multi-photo FLAME tracking: complete;
- mesh: `canonical.ply`, 5,023 vertices, 9,976 faces;
- official result video and eight source/fitted overlays visually inspected;
- full private artifacts were saved with the notebook workflow to Drive; the exact final folder must be checked in Drive/Colab output because it was not pasted into chat.

Tracking configuration:

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

This is the **no-MICA control baseline**.

## 5. Pixel3DMM Result and Meaning

Mean FLAME versus fitted identity vertex displacement after centroid alignment:

- mean: `3.73 mm`;
- RMS: `5.50 mm`;
- p95: `11.37 mm`;
- max: `25.02 mm`.

Quick same-camera/pose/expression shape-swap landmark diagnostic:

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

Approximate improvement: `17.3%`. The fitted shape beat mean FLAME on 8/8 views.

The exact final `track.py` total/component loss values were not pasted into chat and must not be invented. The numbers above are a post-run landmark diagnostic, not the optimizer's weighted objective. Preserve and parse raw component losses in the next MICA A/B.

Correct interpretation:

- tracking changed the mean FLAME shape into a user-specific shape;
- the fitted identity explains observed landmarks better under the same fitted cameras/poses/expressions;
- this is a useful first personal geometry baseline;
- it is not proof of production-grade identity;
- a fairer control must rerun with identity shape fixed to zero while camera/pose/expression refit;
- hidden crown/rear scalp remain prior-driven, not measured truth.

The official tracking comparison's third column is a per-view posed/expressive fitted render, not the neutral canonical mesh. `canonical.ply` is the shared neutral identity.

## 6. What Drives the Current Fit

Do not summarize it as “98 landmarks + UV + normal with equal weight.”

Inputs/evidence include:

- PIPNet WFLW-98 extraction;
- selected active eye contour, eye-closure, and iris landmark losses;
- mouth landmarks disabled in the current run;
- dense UV correspondence;
- surface normals;
- FaRL silhouette/valid-region evidence;
- shape, expression, pose, camera, symmetry, and other regularizers;
- optional MICA identity prior, disabled in this control.

Blindly replacing 98 with MediaPipe 478 will not automatically improve geometry. A robust mapping, visibility, regional confidence, and explicit loss terms are required.

## 7. Important V4 Fixes Already in the Notebook

- independent per-photo crop replaced upstream static video bbox averaging;
- no crop-time roll normalization;
- highest detector confidence replaced area-heavy false-positive ranking;
- complete FLAME2020/2023/masks/embedding installer with SHA/key checks;
- legacy FaceBoxes import path fix;
- resumable FaRL download and JIT validation;
- trusted official Lightning checkpoint load with `weights_only=False` for PyTorch 2.6+;
- HTTPS dependency clones, Cython/build fixes, Facer index dtype fix;
- corrected `iters=100 global_iters=1500`;
- normal/UV exact count gates;
- private Drive bundle and manifest/hash save;
- `trimesh`/Plotly installed with `sys.executable -m pip`, avoiding the previous wrong-interpreter import failure.

Do not resurrect crop v1/v2/v3 or old notebooks unless a named A/B test requires them. Their lessons are in `docs/history.md` and `docs/pixel3dmm_v4.md`.

## 8. Immediate Next Task

Run **MICA enabled versus the preserved no-MICA baseline** on the same eight photos.

Rules:

1. keep the no-MICA Drive folder unchanged;
2. use the same crop, PIPNet, FaRL, normal, and UV inputs where compatible;
3. change only MICA-related initialization/prior behavior;
4. keep iterations, resolution, and unrelated weights identical;
5. write the MICA run into a new folder;
6. generate the same fixed-view renders and metrics;
7. compare front, oblique, tilt, profile, nose, cheek, jaw, forehead, and ears;
8. record runtime and failures;
9. keep MICA only if it measurably improves identity without worse multi-view consistency or implausible geometry.

After the MICA A/B:

1. fully refitted mean-shape control;
2. tracker size 256 versus 512;
3. float32/16-bit normal and UV versus current 8-bit PNG;
4. robust regional landmarks and occlusion confidence;
5. more identities/capture conditions;
6. only then normal/UV fine-tuning;
7. begin observed-pixel UV baker after the temporary geometry baseline is chosen.

Do not change MICA, resolution, map precision, and landmark losses in one run; otherwise the improvement cause is unknowable.

## 9. Current Improvement Ideas

Prioritized ideas are fully specified in `docs/pixel3dmm_v4.md`:

- MICA identity prior A/B;
- fair mean-shape control with camera/expression refit;
- 512 tracking resolution;
- float normal/UV outputs instead of only 8-bit PNG;
- robust nose/brow/jaw/mouth regional constraints with visibility/confidence;
- MediaPipe 478 as cross-check before direct loss integration;
- hand/phone/headphone/hair/general-unknown occlusion masks;
- angular/multi-scale normal loss and multi-view UV consistency;
- Hair App-style normal/UV fine-tuning after baseline diagnosis;
- face-only displacement/high-resolution refinement beyond FLAME;
- better pulled-back-hair, crown/rear, depth, or VGGT scalp evidence.

## 10. Repository Layout After Documentation Consolidation

```text
README.md                              # GitHub landing/current status
AGENTS.md                              # repository agent rules
newchat.md                             # this compact handoff
docs/
  10_3d_hair_app_master_plan.md        # complete system/product plan
  pixel3dmm_v4.md                      # all current geometry experiment knowledge
  history.md                           # chronology/portfolio record
experiments/
  milestone1_geometry_bakeoff/
    pixel3dmm_colab_v4.ipynb           # executable output-free notebook
    scoring_sheet.csv                  # experiment score template
```

Former standalone mobile, scan, base-asset, hair, preprocessing-contract, live-run, and experiment README files were merged into the three detailed documents above and removed. Git history preserves the originals.

## 11. Privacy and License Guardrails

- Never commit private face photos, scan samples, landmarks, segmentations, normals, UV maps, embeddings, textures, meshes, or videos.
- Drive run folders are biometric-sensitive.
- Product inference data and training data must remain separate.
- Training requires explicit opt-in.
- Pixel3DMM, FLAME, KaoLRM, DiffLocks, Im2Haircut, FreeUV, and related assets need separate code/weight/data/dependency license audits.
- A research run does not imply commercial safety.

## 12. What to Say When Asked “Where Are We?”

Short answer:

> We completed the first multi-photo personal head baseline. Eight photos now pass crop, landmarks, segmentation, normal, UV, and FLAME tracking, producing a personalized neutral mesh. A quick landmark diagnostic improved about 17.3% over mean FLAME on all eight views. Next we must test whether MICA improves identity, then strengthen the control, resolution, map precision, and regional evidence before building the photo-based UV texture and 3D hair pipeline.
