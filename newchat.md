# Hair App New-Chat Handoff

Last synchronized: 2026-06-26

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
- no-MICA Pixel3DMM V4 as the current measured geometry baseline after MICA A/B;
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
- guided `front`, `left_45`, `right_45`, `left_profile`, `right_profile`, `hairline` capture;
- 8~12 accepted samples per step;
- FastAPI scan upload and file-based storage;
- backend-created `selected_3dmm/` reconstruction input bundle and `selected_3dmm_manifest.json`;
- backend also exports selected 3DMM frames to `C:\Users\User\Desktop\내사진\{scan_id}\selected_3dmm\`;
- `base_profile.json` version `0.2`;
- representative image, landmark, hairline-guide previews, and selected 3DMM frame count.

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

MICA follow-up on the same eight photos:

- MICA preprocessing completed 8/8 and MICA tracking produced `canonical.ply`, eight per-view meshes, and a result video;
- MICA prior run changed the canonical mesh by mean `4.2749 mm`, median `3.2221 mm`, p95 `8.0128 mm`, max `17.0235 mm` versus no-MICA after centroid alignment;
- 2x2 fixed-context landmark comparison rejected the MICA prior as the default: in the no-MICA camera/pose/expression context, MICA shape worsened average error from `5.8803 px` to `7.2801 px` and lost 8/8 views;
- MICA's own context improved from `6.0530 px` with no-MICA shape to `5.7006 px` with MICA shape, winning 5/8 views, but this was not enough because the no-MICA fixed context strongly preferred the no-MICA shape;
- native-run comparison showed only a small non-fixed-context gain: `5.8803 px` no-MICA versus `5.7006 px` MICA.

MICA init-only follow-up also failed the adoption gate:

- no-MICA context: MICA init-only shape worsened `5.8803 px` to `7.2036 px`, losing 8/8 views;
- MICA init-only context: MICA shape improved `5.9761 px` to `5.7245 px`, winning 5/8 views;
- native-run comparison improved only `0.1558 px`;
- conclusion: do not use MICA by default for this baseline. MICA may be kept as a research reference, but the active baseline remains no-MICA Pixel3DMM V4.

Fully refitted mean-shape control:

- identity shape was forced to zero while camera, pose, expression, jaw, eyes, eyelids, and intrinsics were allowed to refit;
- mean-shape refit average landmark error: `5.742349992829476 px`;
- the validation script reports fitted and mean as identical because the run's fitted shape is intentionally the mean shape;
- this is slightly better than the previous no-MICA fitted-shape landmark diagnostic value `5.880312144215164 px`;
- interpretation: the earlier same-camera shape-swap improvement from `7.1109 px` to `5.8803 px` was not a fair proof of personal identity shape, because refitting camera/pose/expression lets the mean shape reach the same landmark accuracy;
- do not claim the current `canonical.ply` is a strongly validated personal head shape yet. It is an end-to-end geometry artifact and working baseline, but identity-shape evidence is weak under this landmark metric.

Private 19-view app-scan plus selfie run on 2026-06-24:

- the private input set combined selected selfies and app scan frames;
- clean views: `19`;
- no-MICA Pixel3DMM tracking completed and produced `canonical.ply`;
- full no-MICA tracking was preserved in the private Drive run folder;
- fully refitted mean-shape control completed with identity shape effectively zero;
- raw FLAME, fitted mean-shape control, and personal no-MICA were visualized side by side and are visibly different;
- cross-context landmark comparison still did not validate the personal no-MICA identity shape over the refitted mean-shape control:

```json
{
  "views": 19,
  "no_mica_context_gain_px": 0.19544085823244828,
  "mean_shape_context_gain_px": -0.6038492081183984,
  "no_mica_wins_both_contexts": false
}
```

Current decision:

- keep the personal no-MICA mesh as a temporary development candidate, not a validated production identity mesh;
- personal no-MICA, fitted mean-shape control, and raw FLAME have been frozen into the private model-trio handoff folder;
- the current private Drive source of truth is the cleaned `MyDrive/hair_app/input`, `MyDrive/hair_app/output`, and `MyDrive/hair_app/shared` layout, with `data_layout_manifest.json` as the index;
- the next texture-baker entrypoint is the private `output/<current-person>/models/model_trio_for_texture/model_trio_manifest.json`;
- next implement the custom observed-photo face texture baker and apply the same private photo evidence to all three candidates before deciding which visual asset to carry forward.

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

The exact final no-MICA `track.py` total/component loss values were not pasted into chat and must not be invented. The numbers above are post-run landmark diagnostics, not the tracker's weighted objective.

Correct interpretation:

- tracking changed the mean FLAME mesh into a different geometry artifact;
- the fitted identity explains observed landmarks better only under the same fitted cameras/poses/expressions;
- the fully refitted mean-shape control matched or slightly beat that landmark score;
- therefore this is a useful first end-to-end geometry baseline, not a validated personal identity shape yet;
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

Texture Baker v1/v2 are implemented diagnostic milestones, and Texture Baker v3
is now the latest iterative research baker. The user rejected the visual quality
as still far below product standard, so none of these outputs are product
textures yet. v3 combines frame quality scoring, weighted UV evidence,
whole-face repair, two lighting variants, per-iteration review sheets, and
early clean final selection.

Product target:

- not a perfect 360-degree personal scan;
- a personal bald head substrate that looks credible from front through about
  45 degrees;
- good enough geometry/texture for later hair fitting and realistic user
  experience;
- rear head, hidden scalp, and low-confidence regions may use plausible generic
  fallback or completion.

Input policy stays unchanged:

- unconstrained user selfies;
- app scan frames;
- no stricter photo guide, because that would hurt app adoption.

Immediate implementation order:

1. keep the three base mesh candidates active: raw FLAME, fitted mean-shape
   control, and personal no-MICA;
2. build photo/frame quality scoring for blur, face size, pose, exposure, eye
   and mouth state, landmark stability, segmentation reliability, and occlusion
   from hair, hands, phones, glasses, or headphones;
3. use app scan frames as the stable geometry/camera coordinate source and
   selfies mainly as high-detail texture evidence;
4. replace v1 UV splatting with fitted-camera triangle projection,
   z-buffer visibility, view-angle weighting, confidence, occlusion rejection,
   source-photo provenance, and color normalization;
5. add a front-focused review sheet at `0`, `±15`, `±30`, and `±45` degrees;
6. only after observed baking is stable, add per-user optimization that renders
   the head into useful selfie cameras and refines camera, lighting, texture,
   and very small safe geometry/detail terms against masked losses.

This is initially explicit optimization logic for one user at a time, not
training a neural network. A network can later learn to predict better
texture/shape updates faster and use the explicit optimization as refinement.

2026-06-26 v2 status update:

- `experiments/texture_baker/evidence_quality_report.py` scores frames for v2 bake decisions and writes private `quality_v2` reports.
- `experiments/texture_baker/texture_baker_v2.py` creates the current hybrid v2 atlas under `observed_v2_camera_visibility_front45_preview`.
- Latest local coverage was about `33.5%` for Juseop and `30.3%` for Eunchae.
- Current v2 private review sheet: `output/_comparison/face_texture_model_comparison_front45_v2.png` plus JSON manifest beside it.
- It contains 6 model-candidate rows at yaw `-45,-30,-15,0,15,30,45`.
- v2 is easier to inspect than v1 because black holes are reduced, but it still shows forehead/hair/headwear contamination, color seams, and non-final diagnostic eyes.
- Do not choose a final base mesh winner from v2 yet. The next concrete task is completion/occlusion cleanup: remove hair/headwear leakage, fill low-confidence forehead/scalp/neck with plausible skin material, improve eyes, then return to fitted-camera selfie comparison.
- Cleanup/completion pass now exists at `experiments/texture_baker/texture_cleanup_completion.py`.
- It writes `base_color_cleanup_completed.png`, `cleanup_removed_mask.png`, `completion_replaced_mask.png`, and `cleanup_completion_manifest.json` beside each private v2 atlas.
- Current cleanup sheet: `output/_comparison/face_texture_model_comparison_front45_v2_cleanup.png`. It reduces black holes and obvious headwear/hair leakage, but hidden scalp/neck is intentionally flatter material and central face color seams still remain.

2026-06-26 v3 status update:

- `experiments/texture_baker/texture_baker_v3.py` is now implemented.
- It keeps geometry fixed and builds two variants: `v3_no_lighting` and `v3_lighting_normalized`.
- It runs iterations `0..5`, writes per-iteration texture/confidence/observed/fill masks, metrics, fitted-camera comparison sheets, and front-to-45 review sheets.
- It uses weighted multi-frame UV evidence, whole-face bad/empty texel repair, region material fallback, seam smoothing, and skin coherence cleanup.
- Fitted-camera projection support exists but is disabled by default because the current projection pass still adds forehead/mouth noise.
- The final texture is selected from the earliest clean-enough iteration instead of always using the last iteration. In the current private run the selected final is `iter_01` for both people and both variants.
- Current private outputs: `output/<person>/texture_baker/v3_v3_no_lighting/`, `output/<person>/texture_baker/v3_v3_lighting_normalized/`, `output/_comparison/v3_주섭_variant_overview.png`, and `output/_comparison/v3_은채_variant_overview.png`.
- Current decision: v3 is cleaner than v1/v2 but still not product-quality. Do not pick a base mesh winner from v3 yet.
- Next concrete work: proper eye/iris/eyelid and mouth materials, better brow/lip feature preservation, and stronger but safer fitted-camera texture refinement.

Current loader and baker scaffold:

- `experiments/texture_baker/texture_baker_loader.py` resolves local Windows and Colab private Drive roots.
- It currently verifies `주섭` as 3 frozen meshes plus 19 crop/UV/segmentation/landmark/crop-meta frames.
- It currently verifies `은채` as 3 frozen meshes plus 8 crop/UV/segmentation/landmark/crop-meta frames after adding a private `model_trio_for_texture`: shared raw FLAME template, existing `base_flame2023`, and `personal_no_mica`.
- It only reports private paths and existence checks; it does not copy private biometric artifacts into Git.
- `experiments/texture_baker/observed_texture_baker.py` now creates the first observed texture atlas, coverage map, confidence map, source-view map, and manifest from crop RGB plus Pixel3DMM UV PNG plus segmentation labels.
- `observed_v6_primary00000_faceonly_secondary0_preview` for `주섭` uses frame `00000` as central-face primary, weighted mode, face-label whitelist, mask erosion, and conservative preview fill. It is cleaner and less ghosted than `observed_v0_preview`, with lower coverage.
- `observed_v15_primary00004_wideface_strict_occlusion_preview` for `은채` uses frame `00004` as the primary, keeps side/ear labels available, lowers erosion to `2`, allows only slight secondary central contribution, and adds hair/headwear margin plus skin-color occlusion filtering.
- `experiments/texture_baker/textured_mesh_preview.py` renders private quick previews by combining the observed atlas, Pixel3DMM `flame_uv_coords.npy`, and the frozen PLY meshes. Current correct orientation is `--uv-mode flip_y --depth-mode max`. It supports review-only FLAME-mask material fallback, low-confidence texture fallback, and diagnostic iris/pupil eye overlays.
- Local private Drive mesh previews were generated for all current candidates under `mesh_texture_preview/<mesh-key>/contact_sheet.png`: `주섭` raw FLAME, mean-shape control, personal no-MICA; `은채` raw FLAME, base FLAME2023, personal no-MICA.
- `experiments/texture_baker/make_texture_comparison_sheet.py` creates a single manual review PNG with rows as model candidates and columns as 45-degree yaw views.
- Last diagnostic private review sheet: `output/_comparison/face_texture_model_comparison_8view_wideface_eyes_conf5_v4.png` plus JSON manifest beside it. It contains 6 rows: Juseop 3 candidates and Eunchae 3 candidates, each at yaw `0,45,90,135,180,225,270,315`, with material fallback, low-confidence fallback threshold `5`, and eye overlays enabled. It is not product-quality and should not be used to choose a final base mesh.
- `experiments/texture_baker/complete_texture_for_review.py` can create `base_color_visual_completed.png` for UV hole-fill A/B, but current visual inspection found it creates misleading rear-head streaks; prefer the material-fallback sheet for model choice.
- These atlas PNGs and mesh renders are still private debug/runtime artifacts under Drive. They are not final skin textures.
- Do not ask the user for stricter photo capture. The app must work with ordinary selfies plus the app scan.
- Do not choose a base mesh winner from v1 texture renders. Texture quality is currently the bottleneck.

Do not start by using a generative completion model. First make the observed-photo layer reproducible. Completion for missing UV regions comes after coverage/confidence exists.

Product scan update now implemented:

- the app's guided scan flow is geometry-oriented rather than only profile-preview-oriented;
- backend keeps raw accepted samples and additionally creates a curated `selected_3dmm/` folder with 10 best scan frames;
- backend also copies the curated scan frames to `C:\Users\User\Desktop\내사진\{scan_id}\selected_3dmm\` for local manual use;
- completed private data experiment: combined the user's chosen selfies with the app-scan bundle and reran Pixel3DMM no-MICA plus the mean-shape control. The stable three-mesh texture handoff folder now exists in the cleaned private Drive layout.
- the product still lacks selfie upload UI, so selfie selection currently happens outside the app in a private local folder.

Do not change geometry, texture, completion, and landmark losses in one run; otherwise the improvement cause is unknowable.

Private Drive cleanup guidance:

- keep the cleaned `input/`, `output/`, `shared/`, and `data_layout_manifest.json`;
- keep the current user and legacy girl experiment under the same person-oriented layout;
- staging folders such as `_OLD_STAGING_AFTER_CLEAN_LAYOUT_*`, `_TRASH_REVIEW_*`, and `_REMOVE_FROM_KEEP_REVIEW_*` can be deleted after visually confirming that the cleaned layout contains the source inputs, preprocessing artifacts, model folders, tracking folders, and manifests;
- do not commit any private Drive artifact to Git.

## 9. Current Improvement Ideas

Prioritized ideas are fully specified in `docs/pixel3dmm_v4.md`:

- MICA identity prior A/B;
- MICA init-only A/B;
- fully refitted mean-shape control, which matched or slightly beat no-MICA fitted-shape landmark error;
- cross-context no-MICA shape versus mean-shape validation on the private 19-view run;
- freeze raw FLAME, fitted mean-shape control, and personal no-MICA as a private model trio;
- custom observed-photo face texture baker for all three frozen candidates;
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
    freeze_model_trio_for_texture.py   # private Drive model-trio freeze helper
    scoring_sheet.csv                  # experiment score template
  texture_baker/
    texture_baker_loader.py            # private Drive path resolver and input bundle checker
    README.md                          # local and Colab loader smoke-test commands
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

> We have a working app scan foundation, offline Pixel3DMM geometry artifacts, and three frozen mesh candidates: raw FLAME, fitted mean-shape control, and personal no-MICA. Texture Baker v3 now runs iterative fixed-geometry texture baking for Juseop/Eunchae, produces no-lighting and lighting-normalized variants, and selects `iter_01` as the current clean-enough final in the private run. It is cleaner than v1/v2 but still not product-quality, so the next move is eye/mouth material work, better feature preservation, and safer fitted-camera texture refinement before any base-mesh decision.
