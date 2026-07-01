# Hair App Project History

Last synchronized: 2026-06-30
Status: detailed project chronology and archive for retired engine paths

## How To Read This File

This file is the long-form memory of the project. It records what was tried,
why it was tried, what failed, what was learned, and how those decisions led to
the current FaceBuilder/KeenTools direction.

Current source-of-truth files:

- `README.md`: high-level current state.
- `newchat.md`: compact handoff for the next chat.
- `docs/10_3d_hair_app_master_plan.md`: active product and system plan.
- `experiments/facebuilder_bridge/README.md`: current FaceBuilder automation
  bridge.
- `docs/history.md`: this detailed chronology and archive.

Former standalone active documents for Pixel3DMM and Texture Baker were moved
into this file because those engines are no longer the main product path. Their
records are preserved below as detailed archive sections.

## 2026-06-28 FaceBuilder Semantic Crop/Sentinel Ablation

This entry records the current active FaceBuilder comparison after the user
rejected the skin-color fill preprocessing approach.

### Why The v1-v4 Color-Mute Ablation Was Retired

After texture-bake parity with Blender UI `Create Texture` was fixed, a
four-version FaceBuilder ablation was attempted:

```text
v1 = original photos + raw FaceBuilder texture
v2 = original photos + same-size preprocessed texture photos
v3 = original photos + output cleanup texture
v4 = same-size preprocessed texture photos + output cleanup texture
```

The experiment proved routing and review automation, but it was not a good
quality direction. The preprocessor filled hair/background/object regions with
skin-like colors. FaceBuilder then treated that fake skin as real texture
evidence, so the input was not cleaned; it was corrupted before the bake.

Those private outputs were moved out of the active output root and preserved as
a private historical archive:

```text
G:\내 드라이브\hair_app\output\history_archive\retired_facebuilder_color_mute_v1_v4_20260628T091346Z\
```

The archive keeps the old `.blend`, OBJ/GLB, texture, logs, manifests, and
review sheets for forensic comparison. These remain private biometric artifacts
and must not be committed to Git.

### New Semantic Ablation Goal

The next experiment changed one thing: instead of inventing a new crop or
segmentation system, it reuses the previous Pixel3DMM V4 preprocessing outputs:

- official FaceBoxesV2 per-photo no-roll crop;
- 512x512 crop;
- margin 1.42;
- FaRL face parsing label maps;
- existing crop/segmentation review artifacts.

The purpose is not to make a final product head yet. The purpose is to answer
three narrower questions:

1. Does FaceBuilder behave better on raw validated photos or on consistent
   FaceBoxes crops?
2. Does the previous V4 crop engine still look reliable enough to reuse?
3. If bad semantic regions are painted with impossible colors, do those colors
   enter the FaceBuilder baked texture?

### Version Definitions

Current active private versions:

```text
semantic_v1 = raw V4-validated photos + raw FaceBuilder texture
semantic_v2 = Pixel3DMM V4 crops + raw FaceBuilder texture
semantic_v3 = Pixel3DMM V4 crops for alignment + sentinel-colored semantic texture inputs
```

Sentinel colors are deliberately impossible skin colors:

- background: green;
- hair: purple;
- cloth: blue;
- eyeglasses: cyan;
- hat or miscellaneous region: yellow;
- accessory/unknown/uncovered/outlier: red, pink, or orange.

If those colors appear in the baked texture, the experiment proves FaceBuilder
is using or blending those pixels rather than semantically ignoring them.

### Input Scope And Important Caveat

The user asked to use the Desktop `내사진` and `은채사진` folders. For this
controlled semantic ablation, the implementation used the already validated
Pixel3DMM V4 manifest rows because those rows are the only ones with matching
old FaceBoxes crop and FaRL segmentation artifacts.

Current rows:

- Juseop: 19 V4 rows = 9 app-scan frames plus 10 selfie rows.
- Eunchae: 8 selfie rows.

There are Desktop-only Juseop images outside this V4 crop/segmentation set. They
were not added to this ablation because doing so would mix old trusted crop/seg
with a new unvalidated crop engine and would make v1/v2/v3 less comparable. If
the next experiment truly needs every Desktop image, the correct next step is
to rerun the V4 crop/FaRL preprocessing over that exact Desktop set first.

For Juseop, `scan_*` rows are alignment-only by default. They are still used to
help FaceBuilder fit the head, but they do not enter texture bake unless the
runner is called with `--texture-scan-frames`. This was necessary because full
19-camera texture bake with mixed scan and selfie cameras stalled in headless
FaceBuilder. It also matches the product plan: app scan stabilizes geometry,
while selfies provide appearance texture.

### Implemented Code

New tracked files:

```text
experiments/facebuilder_semantic_ablation/README.md
experiments/facebuilder_semantic_ablation/run_facebuilder_semantic_ablation.py
```

The runner:

- validates existing Pixel3DMM V4 crop/segmentation manifests;
- copies raw/crop/sentinel working inputs into private Drive output folders;
- builds crop/segmentation/sentinel review sheets;
- writes FaceBuilder input manifests for each version/person;
- calls the existing headless Blender FaceBuilder batch runner;
- exports OBJ and GLB through the existing bridge path;
- creates per-version `semantic_review_sheet.png` files;
- creates a global v1/v2/v3 comparison sheet;
- archives old retired FaceBuilder v1-v4 outputs when `--archive-old` is used.

Main command shape:

```powershell
python experiments\facebuilder_semantic_ablation\run_facebuilder_semantic_ablation.py `
  --drive-root "G:\내 드라이브\hair_app" `
  --archive-old `
  --clean
```

Review-only regeneration after the Blender work already exists:

```powershell
python experiments\facebuilder_semantic_ablation\run_facebuilder_semantic_ablation.py `
  --drive-root "G:\내 드라이브\hair_app" `
  --skip-existing
```

### Private Output Layout

Active private outputs:

```text
G:\내 드라이브\hair_app\output\facebuilder_semantic_v1\juseop\
G:\내 드라이브\hair_app\output\facebuilder_semantic_v1\eunchae\
G:\내 드라이브\hair_app\output\facebuilder_semantic_v2\juseop\
G:\내 드라이브\hair_app\output\facebuilder_semantic_v2\eunchae\
G:\내 드라이브\hair_app\output\facebuilder_semantic_v3\juseop\
G:\내 드라이브\hair_app\output\facebuilder_semantic_v3\eunchae\
G:\내 드라이브\hair_app\output\_semantic_preprocess\
G:\내 드라이브\hair_app\output\_preprocess_review\
G:\내 드라이브\hair_app\output\_comparison\facebuilder_semantic_v1_v3\
```

Important review sheets:

```text
G:\내 드라이브\hair_app\output\_preprocess_review\juseop\juseop_crop_segmentation_sentinel_review.png
G:\내 드라이브\hair_app\output\_preprocess_review\eunchae\eunchae_crop_segmentation_sentinel_review.png
G:\내 드라이브\hair_app\output\_comparison\facebuilder_semantic_v1_v3\facebuilder_semantic_v1_v3_comparison.png
```

Each version/person folder also contains:

```text
01_input_manifest/input_manifest.json
03_facebuilder_scene/<person>_<version>_facebuilder.blend
04_exports/<person>_<version>_bald_head.obj
05_postprocess/facebuilder_texture_bake.png
05_postprocess/facebuilder_texture_bald_cleanup.png
06_glb/<person>_<version>_bald_head.glb
07_review_sheets/render_yaw_*.png
07_review_sheets/semantic_review_sheet.png
run_manifest.json
logs/
```

### Latest Run Summary

| Version | Person | Input rows | Texture rows | Texture source | Result |
| --- | --- | ---: | ---: | --- | --- |
| semantic_v1 | Juseop | 19 | 10 | raw validated photos | complete |
| semantic_v1 | Eunchae | 8 | 8 | raw validated photos | complete |
| semantic_v2 | Juseop | 19 | 10 | V4 crops | complete |
| semantic_v2 | Eunchae | 8 | 8 | V4 crops | complete |
| semantic_v3 | Juseop | 19 | 10 | sentinel-colored V4 crops | complete |
| semantic_v3 | Eunchae | 8 | 8 | sentinel-colored V4 crops | complete |

### Visual Findings

The crop review sheets show that the old Pixel3DMM V4 crop engine is still
useful. Faces are consistently centered at a comparable scale, and this is a
better controlled input for FaceBuilder than arbitrary uncropped phone images.

The FaRL segmentation is useful for broad regions: skin, hair, background,
clothes, eyes, lips, nose, ears, and neck. However, it is not a complete
occlusion detector. Skin-colored hands/fingers, perfume bottles, phones, and
some accessories can still be partially mislabeled as skin or face-adjacent
regions. This matters most for Eunchae's perfume/hand images.

The sentinel v3 result is intentionally not visually usable. Purple/green/blue
sentinel colors appear in the baked texture and rendered head. That is useful
evidence: FaceBuilder does not semantically understand those painted regions;
it samples or blends the pixels. Therefore, replacing bad regions with fake
skin before bake is unsafe, and replacing them with sentinel colors before bake
is only diagnostic.

The best immediate baseline is semantic_v2, not because it is product quality,
but because it keeps real photo pixels while making input scale and face
position more consistent. The next quality step should be semantic post-bake
repair and occlusion-aware masking, not more pre-bake color filling.

### Next Decisions From This Experiment

1. Keep FaceBuilder automation as the near-term head engine.
2. Keep Pixel3DMM V4 crop/FaRL preprocessing as a reusable preprocessing
   source, but do not pretend FaRL alone detects hands/phones/perfume bottles.
3. Stop using skin-color fill as pre-bake cleanup.
4. Use sentinel coloring only as a diagnostic probe, not a product path.
5. Build post-bake cleanup around semantic masks, observed/fallback confidence,
   and separate eye/mouth/scalp materials.
6. If the user wants every Desktop image included, first rerun V4 crop/FaRL over
   the exact Desktop folders and then rerun semantic_v1/v2/v3 on the matching
   set.

## 2026-06-28 FaceBuilder Texture Parity Fix And v1-v4 Reset

This entry records an important reset of the FaceBuilder experiment line.

### Why The Previous FaceBuilder v1/v2/v3 Outputs Were Retired

The first private FaceBuilder v1/v2/v3 batch was generated before the automated
texture bake matched the Blender UI `Create Texture` path. The visible output
was therefore not a fair test of FaceBuilder or the planned Hair App pipeline.

The root problem was not the solved mesh. A manual Blender export and the
automated auto-align export were nearly identical in geometry. The problem was
that TextureBuilder depends on each photo camera's projection state, not only
on the final head mesh. The old automation added cameras and solved pins, but
it skipped parts of the UI import/auto-align update flow:

- EXIF/focal setup for each imported photo;
- `center_geo_camera_projection` after camera import;
- updating all FaceBuilder camera positions after auto-align;
- updating all FaceBuilder camera focal lengths after auto-align.

Because those camera/projection values were stale, the headless texture bake
sampled the same photos differently from the Blender UI. The user manually
created `ha.png` in Blender by pressing FaceBuilder Texture > `Create Texture`
after auto-aligning the same 10 Juseop photos. The old automated raw texture
differed from this manual reference by mean RGB error about `18.14`.

TextureBuilder option sweeps did not solve the mismatch. The best tested
settings variant still differed from `ha.png` by mean RGB error about `15.44`.
After the automation was changed to mirror the UI camera/projection update
path, the automated raw bake differed from `ha.png` by mean RGB error about
`0.12`, which is close enough to treat as the same FaceBuilder texture bake
path.

The old cleanup pass was also too aggressive. It replaced too much of the raw
texture and made the rendered head worse. Therefore the previous v1/v2/v3
private outputs were retired and should not be used for quality decisions.

### Drive Archive And Cleanup

The old bulk private outputs were removed from Drive. Representative private
review sheets and small manifests were preserved under:

```text
G:\내 드라이브\hair_app\output\history_archive\retired_facebuilder_v1_v2_v3_20260628\
```

Archived representative review sheets:

```text
v1/juseop/review_sheet.png
v1/eunchae/review_sheet.png
v2/juseop/review_sheet.png
v2/eunchae/review_sheet.png
v3/juseop/review_sheet.png
v3/eunchae/review_sheet.png
```

The images themselves are private biometric review assets and must stay in
Drive, not Git.

### New v1-v4 Experiment Definition

The version comparison was reset to isolate the effect of two variables:
texture-input preprocessing and texture-output post-processing. Photo quality
selection was intentionally disabled for this ablation. Every readable photo is
attempted in every version.

Current definitions:

```text
v1 = original photos + raw FaceBuilder texture
v2 = original photos for auto-align + same-size preprocessed photos for texture bake + raw FaceBuilder texture
v3 = original photos + postprocessed cleanup texture
v4 = preprocessed texture photos + postprocessed cleanup texture
```

Important implementation details:

- Auto-align always uses the original normalized photo.
- v2/v4 add a `texture_path` to the manifest candidate. After auto-align
  succeeds, Blender swaps the camera image to the same-size preprocessed image
  before texture bake.
- v1/v2 use `facebuilder_texture_bake.png` as the material texture.
- v3/v4 pass `--use-cleanup-texture` and use
  `facebuilder_texture_bald_cleanup.png` as the material texture.
- Raw FaceBuilder texture is always preserved.
- Cleanup texture is always saved for comparison, but is only applied in v3/v4.

### New v1-v4 Run Results

The new private batch completed successfully for Juseop and Eunchae.

```text
G:\내 드라이브\hair_app\output\facebuilder_v1\
G:\내 드라이브\hair_app\output\facebuilder_v2\
G:\내 드라이브\hair_app\output\facebuilder_v3\
G:\내 드라이브\hair_app\output\facebuilder_v4\
```

Summary:

| Version | Person | Selected | Rejected | Preprocessed | Aligned | Failed | Texture cameras |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| v1 | juseop | 11 | 0 | 0 | 10 | 1 | 10 |
| v1 | eunchae | 8 | 0 | 0 | 7 | 1 | 7 |
| v2 | juseop | 11 | 0 | 11 | 10 | 1 | 10 |
| v2 | eunchae | 8 | 0 | 8 | 7 | 1 | 7 |
| v3 | juseop | 11 | 0 | 0 | 10 | 1 | 10 |
| v3 | eunchae | 8 | 0 | 0 | 7 | 1 | 7 |
| v4 | juseop | 11 | 0 | 11 | 10 | 1 | 10 |
| v4 | eunchae | 8 | 0 | 8 | 7 | 1 | 7 |

Cross-version private comparison sheets:

```text
G:\내 드라이브\hair_app\output\_comparison\facebuilder_v1_v4\juseop_facebuilder_v1_v4_comparison.png
G:\내 드라이브\hair_app\output\_comparison\facebuilder_v1_v4\eunchae_facebuilder_v1_v4_comparison.png
```

Visual conclusion from this first reset batch:

- v1 is now the correct raw FaceBuilder baseline.
- v2 proves same-size preprocessed texture inputs can be swapped in, but the
  first heuristic preprocessor creates visible neutral-color patches on the
  rendered head.
- v3 proves cleanup texture routing works, but the current heuristic cleanup is
  still not product quality.
- v4 combines both effects, but the visible result confirms that semantic masks
  are needed before this approach becomes useful.

Next lesson: do not broaden color heuristics blindly. The next quality step
should use semantic masks for skin, hair, scalp, background, neck, ear, eye,
mouth, and occlusion regions.

## 1. Original Product Idea

The project started from a simple user problem: when someone finds a hairstyle
photo they like, they want to know whether that hairstyle would actually suit
their own face.

The first imagined product flow was:

```text
user face photo
  + desired hairstyle photo
  -> image where the user's face is preserved and only the hair changes
```

Common problems with ordinary hair-swap or portrait-editing services became
clear quickly:

- the face is regenerated along with the hair, so the user may look like a
  different person;
- eyes, nose, mouth, skin tone, clothes, and background can change;
- a single frontal result may look plausible while side and rear views remain
  inconsistent;
- real hairline, forehead, cheekbones, jawline, ears, and head depth are hard
  to preserve in one 2D edit;
- a reference hairstyle image usually does not contain real rear-head evidence.

From that point, the product problem became more specific:

```text
preserve identity while controlling hairstyle
```

## 2. Scan Foundation Before Generation

Before connecting a finished AI engine, the project built a foundation for
collecting user data in a structured way.

Early implementation:

1. React + Vite mobile web.
2. Browser camera with `getUserMedia`.
3. MediaPipe Face Landmarker for face position and quality checks.
4. Guided `front`, `left`, `right`, and `hairline` capture steps.
5. Automatic collection of accepted samples per step.
6. FastAPI `POST /api/scan` upload and file-based storage.
7. `base_profile.json` version `0.1` containing raw landmarks, representative
   image, quality metrics, and anchors.
8. Face landmark and hairline-guide previews.

The important point: `base_profile` was not a 3D avatar. It was a structured
scan foundation that could survive model changes.

Lessons from this stage:

- input quality and raw-data preservation come before model choice;
- face photos are biometric-sensitive data, so runtime storage and Git must be
  separated;
- do not keep only one representative image; preserve raw frames, landmarks,
  quality, and view meaning;
- a stable capture contract prevents the whole app from being rebuilt whenever
  the model changes.

## 3. First Direction: Hair-Specific 2D Models

The first research instinct was to use models built specifically for hair
editing. Candidates included StableHairV2, Stable-Hair, HairFusion,
HairFastGAN, and HairPort-style models.

### Why StableHairV2 Was Chosen First

- It directly targeted hairstyle transfer.
- It separated identity image and hairstyle reference.
- It had an official inference path and pretrained checkpoints.
- It looked more specialized than a general image editor.

### What Was Done

- Installed the official repository and checkpoints in Colab.
- Fixed dependency and fp16 dtype issues.
- Reproduced the official test-pair inference.
- Ran private Hair App-style tests with ordinary portraits and hairstyle
  references.

### Why The Result Was Not Acceptable

The official path ran, but ordinary user portraits showed severe product
issues:

- the face and background were strongly regenerated;
- identity was not preserved;
- artifacts appeared around the face and hair;
- the official identity input assumed something close to `bald.jpg`, meaning a
  bald or hair-removed input;
- ordinary user selfies did not match the model's clean demo assumptions.

Key lesson: a model being "hair-specific" does not mean it fits Hair App's real
input contract. A paper demo can work while product inputs fail.

StableHairV2 installation details were removed from active docs. They can be
recovered from Git history if needed, but that path is not active.

## 4. Second Direction: General 2D Image Editors

After hair-specific models failed the identity/product test, the project looked
at stronger general image editors combined with masks, landmarks, and hairline
information.

Reviewed candidates:

- Qwen Image Edit.
- HiDream.
- FLUX family.
- LongCat Image.
- Step1X Edit.
- HairPort-like final-transfer pipelines.

Planned flow at that time:

```text
user portrait + hairstyle reference
  -> multi-reference image editor
  -> identity and landmark checks
  -> protected-region compositing
  -> retry/ranking
  -> final 2D portrait
```

The plan included:

- face and hair masks;
- hairline anchors;
- protected face regions;
- identity embedding score;
- landmark displacement checks;
- background and clothing preservation checks;
- multi-seed ranking;
- possible LoRA or editing SFT after a baseline worked.

This could plausibly produce one good-looking image, but it still did not solve
multi-angle consistency or a reusable 3D head.

## 5. FLUX.2 As The First 2D Fine-Tuning Candidate

On 2026-06-20, `FLUX.2 [klein] base-9B` was selected as the first 2D tuning
candidate.

Reasons:

- the user saw editable quality in a public Space;
- multi-reference image conditioning was close to the product idea;
- the undistilled base model seemed more suitable for fine-tuning than a
  distilled checkpoint;
- H100 access made quality ceiling more important than picking the smallest
  model;
- LoRA, cached image latents, and cached text embeddings provided a realistic
  training path;
- the 9B model could be considered before the 4B model because compute was less
  constrained.

Expected training shape:

- LoRA on the transformer core;
- freeze VAE and text encoder;
- use portrait plus hairstyle reference as image conditions;
- target identity-preserving hairstyle edits;
- evaluate identity, landmarks, hairline, protected regions, and artifacts.

The user studied FLUX.2 model structure directly. The project did not reach
LoRA training, checkpointing, or quantitative 2D benchmarks before the product
goal shifted toward 3D.

Why this was still useful:

- it can become a 2D quality benchmark for 3D renders;
- it can generate plausible side/rear hairstyle hypotheses from a single
  reference;
- it can polish presentation renders after 3D geometry exists;
- it can serve as a temporary 2D preview path;
- multi-reference conditioning and identity-evaluation lessons transfer to
  other models.

Important limitation: generated side/rear views are not measured evidence, and
independently edited views are not a single consistent 3D geometry.

## 6. Decisive Shift: From One Image To Rotatable 3D

The user's desired flow became clearer:

1. Upload several photos of themselves.
2. Mark one or two best-looking photos with a star.
3. Use multiple photos to infer face ratio, nose depth, eye depth, cheekbones,
   jawline, and hairline.
4. Remove the current hair and create a personal hairless head.
5. Add a desired hairstyle reference.
6. Understand that hairstyle as independent 3D hair.
7. Combine the personal head and hair.
8. Let the user inspect the result from multiple angles or rotate it by touch.

In this requirement, changing 2D editors would not solve the core issue. 2D
models can draw pixels for one camera, but they do not naturally provide a
shared geometry and independent hair asset.

The source-of-truth representation changed to:

```text
editable hairless head mesh
  + actual-photo-derived face texture
  + independent 3D strand hair
  + scalp retargeting and collision correction
```

This is the key reason the project moved from 2D editing to real 3D.

## 7. Initial Three-Engine Structure

The early 3D plan had three large engines:

1. create a 3D head from user photos;
2. understand a hairstyle photo as 3D hair;
3. combine the head and hair.

That split was directionally right. Later work made the intermediate contracts
more explicit:

```text
user photos and scan
  -> preprocessing and camera/landmarks
  -> hairless head geometry
  -> multi-photo face texture

hairstyle reference
  -> mask/orientation/depth
  -> canonical strand hair

head + hair
  -> scalp correspondence
  -> hairline-aware deformation
  -> collision correction
  -> GLB/mobile LOD
```

The product became a set of geometry, texture, hair, and fitting contracts
rather than three giant AI models stitched together.

## 8. Pixel3DMM, FastAvatar, And UV Baker Decisions

### Pixel3DMM Clarification

At first, the final bald mesh shown in Pixel3DMM examples caused confusion: was
Pixel3DMM only producing an empty bald template without the user's face?

Correct interpretation:

- Pixel3DMM is not an empty head-template generator.
- It fits FLAME-family face/head geometry to the input photo evidence.
- The result may look hairless, but it includes estimated facial geometry:
  nose, cheeks, jaw, eyes, mouth, expression, and camera pose.
- Crown/rear scalp hidden under hair is prior-based estimation, not direct
  measurement.
- Multi-photo evidence can be used as a Hair App geometry baseline and possible
  teacher.

Pixel3DMM was selected as the first geometry baseline and possible teacher, not
as a permanently chosen commercial engine.

### Why FastAvatar Was Considered

The project considered using Pixel3DMM as a geometry teacher and adapting a
FastAvatar-like model as a Hair App-specific multi-image appearance model.

The idea:

```text
Pixel3DMM teacher geometry
  + Hair App data
  -> faster/lightweight student model
```

But Hair App needs editable mesh topology, UV textures, and replaceable
independent hair. Gaussian avatar representation can entangle face appearance
and existing hair, then require another transfer back to the Pixel3DMM/FLAME
mesh.

Therefore FastAvatar remained a reference/possible future benchmark, not the
core pipeline.

### Why A Custom UV Baker Was Planned

The product needed actual photographed skin, lips, brows, and other appearance
details to be attached to the 3D head.

The planned UV baker was supposed to:

- project each accepted photo onto the fitted head surface;
- use camera/visibility/angle/mask confidence to choose reliable pixels;
- merge multi-view evidence into one texture;
- keep observed and generated regions separate;
- fill unobserved areas only with labeled fallback/completion;
- preserve source-photo provenance.

This became the Texture Baker v1/v2/v3 line. It was valuable research, but it
did not reach product quality.

## 9. Why Pixel3DMM Crop Had To Change

### Original Pixel3DMM Assumption

Pixel3DMM's default examples were closer to a continuous video or controlled
sequence. A single static crop could make sense when frames are from the same
video and the face remains consistently framed.

Hair App's real input is different:

- unrelated selfies;
- different cameras;
- different distances and crops;
- different lighting;
- different poses and expressions;
- app scan frames mixed with ordinary photos.

### Why It Broke On Hair App Inputs

The early static/global crop behavior failed because independent photos had very
different face positions. A crop that worked for one photo could cut off the
face in another. This caused broken landmarks, segmentation, and tracking.

The project learned that each discontinuous photo needs its own persistent crop
with preserved metadata, rather than one crop inherited from another frame.

## 10. Crop v1, v2, v3 Experiments

### V1: Per-Image BBox And Two-Eye Roll

V1 tried per-image bounding boxes and roll normalization from the eyes.

Result:

- it was better than one shared crop;
- but crop-time landmarks were too weak to be trusted for rotation;
- interpolation and coordinate transforms added risk;
- downstream PIPNet/FLAME already had better rotation handling.

### V2: Landmark Plausibility And Safety

V2 added plausibility checks and safer handling.

Result:

- it reduced some extreme failures;
- but it still depended too much on crop-time landmarks;
- it made the pipeline more complex without proving downstream improvement.

### V3: Five-Point Eye/Nose/Mouth Geometry

V3 tried a fuller five-point geometry using eyes, nose, and mouth corners.

Result:

- the idea was reasonable;
- but the actual source audit showed this was solving the wrong problem;
- Pixel3DMM's official pipeline wants persistent square face crops, then PIPNet
  and tracking handle the stronger geometry later.

## 11. Source Audit And Final Crop Decision

Before continuing to tune crop heuristics, the project audited Pixel3DMM source
more carefully.

Important findings:

- Pixel3DMM uses FaceBoxes for face boxes.
- It runs PIPNet WFLW-98 after the crop.
- Sparse crop-time points are not the final landmark set.
- The tracker estimates camera/head pose after stronger landmarks exist.
- FaRL segmentation has its own model-specific alignment.

Final crop decision:

```text
for each independent source photo:
  -> detect face with FaceBoxes
  -> choose highest-confidence face
  -> create official-compatible square crop
  -> keep persistent 512x512 no-roll crop
  -> preserve metadata to map crop coordinates back to source
```

Why confidence-first returned:

- a wrong low-confidence side face or background detection is more dangerous
  than a slightly imperfect high-confidence crop;
- downstream PIPNet and FLAME fitting provide stronger geometry;
- roll normalization based on weak crop-time points created avoidable risk.

This changed the input contract, not the Pixel3DMM geometry model itself.

## 12. Pixel3DMM V4 Execution And Fixes

### Environment And Dependencies

The Pixel3DMM V4 notebook ran in a Colab/A100 environment with a dedicated
conda environment. Multiple compatibility issues had to be fixed before a
complete run succeeded.

### FLAME Asset Structure

FLAME assets had to be installed with the exact structure expected by
Pixel3DMM. Missing or misplaced FLAME files caused early failures.

### FaceBoxes Import

FaceBoxes legacy import behavior required compatibility handling. The project
patched the import path rather than replacing the detector.

### Crop Primary-Face Selection

One profile image selected the wrong face candidate at first. The pipeline was
changed back to a confidence-first FaceBoxes selection with safeguards.

### PIPNet And FaRL

PIPNet WFLW-98 landmarks and FaRL segmentation became required gates. The V4
run had to pass exact count checks before continuing.

### Private Artifact Preservation

The workflow preserved private inputs, crops, landmarks, masks, normal maps, UV
maps, tracking renders, and manifests outside Git.

### Checkpoint Error And First Mesh

PyTorch changed default checkpoint loading behavior. The trusted official
Pixel3DMM Lightning checkpoint required explicit safe handling. After this fix,
normal and UV inference completed, tracking ran, and the first mesh was
generated.

### First Personalization Diagnostic

The initial 8-photo run produced:

- `canonical.ply`;
- 5,023 vertices;
- 9,976 faces;
- fitted identity landmark error about `5.8803 px`;
- mean FLAME landmark error under the same fitted cameras/poses/expressions
  about `7.1109 px`;
- quick apparent gain about `1.2306 px`, roughly `17.3%`.

This diagnostic was useful but not final. It did not refit camera/expression
for every control condition.

Later mean-shape control and cross-context checks weakened the claim that the
no-MICA identity shape was clearly better than a refitted mean shape.

## 13. Structure Before The FaceBuilder Pivot

Before the FaceBuilder pivot, the working product hypothesis was:

1. MediaPipe for app capture guidance and cheap quality checks.
2. Pixel3DMM for the first multi-photo head geometry baseline.
3. Optional VGGT for camera/depth/point initialization.
4. Custom UV baker for observed photo pixels.
5. FreeUV or simpler completion for unobserved UV regions.
6. DiffLocks or another image-to-hair model for strand hair.
7. Custom scalp/root fitting and collision correction.
8. GLB/Three.js delivery.

Open work at that point:

- stronger Pixel3DMM validation across more identities;
- texture quality improvement;
- eye/mouth material handling;
- final base mesh selection;
- hair reconstruction bake-off;
- scalp retargeting and collision;
- production backend jobs and GLB viewer.

## 14. What Failed And What Remained Useful

Failures:

- hair-specific 2D models did not preserve identity reliably;
- general 2D editors did not provide a reusable 3D representation;
- Pixel3DMM crop assumptions did not match independent selfies until modified;
- no-MICA Pixel3DMM was not clearly proven better than refitted mean-shape
  control;
- Texture Baker v1/v2/v3 did not reach product-quality skin texture;
- filling missing texture could make review sheets cleaner while erasing
  identity detail.

Useful assets and lessons:

- app capture foundation;
- private data separation rules;
- Pixel3DMM preprocessing and artifact contracts;
- observed versus fallback region thinking;
- review-sheet tooling;
- photo/frame scoring ideas;
- the need to judge visual quality, not only numeric loss;
- the need to treat hidden scalp/rear head as plausible fallback unless
  actually observed.

## 15. Project Principles

Principles formed during the project:

- Do not trust a README demo as proof of product fit.
- Reproduce official inference before modifying a model.
- Use the same Hair App inputs across candidates.
- Preserve raw inputs and provenance.
- Keep private biometric data out of Git.
- Separate current implementation from future plans.
- Treat model choices as replaceable hypotheses.
- Do not fine-tune before a baseline works.
- Do not let lower loss override worse human-visible quality.
- Keep observed, inferred, and generated regions distinguishable.

## 16. Portfolio Narrative

The project story can be explained as:

1. Started from a common hair try-on problem.
2. Tested hair-specific 2D models and found identity/product mismatch.
3. Studied stronger 2D editing and FLUX.2, but recognized the need for
   rotatable 3D.
4. Built a scan/capture foundation.
5. Reproduced Pixel3DMM and fixed independent-photo preprocessing.
6. Built texture baker experiments and learned why direct UV splatting was not
   enough.
7. Found FaceBuilder/KeenTools as a stronger fitting engine.
8. Verified that Blender/KeenTools automation is possible.
9. Pivoted toward FaceBuilder automation plus Hair App-specific post-processing
   and hair fitting.

## 17. 2026-06-24 Private 19-View Geometry And Texture Handoff

The private data experiment combined selected selfies with app-scan selected
3DMM frames and reran Pixel3DMM V4 no-MICA plus the fully refitted mean-shape
control on 19 clean views.

Result:

- no-MICA Pixel3DMM generated a usable `canonical.ply`;
- fully refitted mean-shape control also ran;
- the cross-context landmark gate did not clearly validate no-MICA identity
  shape over the refitted mean-shape control;
- raw FLAME, mean-shape control, and no-MICA personal mesh were frozen as three
  texture-review candidates.

Private data layout rules were clarified:

```text
MyDrive/hair_app/input/
MyDrive/hair_app/output/
MyDrive/hair_app/shared/
MyDrive/hair_app/data_layout_manifest.json
```

Private photos, meshes, landmarks, masks, textures, renders, and review sheets
must never be committed.

## 18. 2026-06-26 Texture Baker v1 Review And Strategy Reset

Texture Baker v1 loaded private model-trio manifests and produced first review
sheets.

It showed:

- the loader and manifest path worked;
- private model candidates could be rendered;
- observed UV/segmentation evidence could be inspected;
- but the result had large black regions, weak coverage, crude eyes/mouth, and
  no product-quality identity.

Strategic decision:

- do not choose a base mesh from v1;
- build a more camera-aware Texture Baker v2;
- preserve all three mesh candidates.

## 19. 2026-06-26 Texture Baker v2 Hybrid Front-45 Run

Texture Baker v2 added:

- evidence quality report;
- segmentation confidence;
- Pixel3DMM UV correspondence use;
- fitted-camera projection diagnostics;
- z-buffer visibility;
- front-to-45 review sheets;
- material fallback;
- cleanup/completion experiments.

Result:

- fewer empty regions;
- easier diagnostic review;
- but visible seams, lighting mismatch, headwear/hair leakage, synthetic eyes,
  and low useful coverage remained;
- Eunchae had lower coverage and more occlusion risk than Juseop;
- base mesh selection still could not be trusted.

Decision:

- do not choose a mesh winner;
- focus on completion/occlusion cleanup and feature preservation.

## 20. 2026-06-26 Texture Baker v3 Iterative Bake

Texture Baker v3 was the last major custom baker experiment.

Implemented:

- `texture_baker_v3.py`;
- `v3_no_lighting` and `v3_lighting_normalized` variants;
- stricter frame filtering with default `--min-score 0.62`;
- weighted multi-frame UV seed texture;
- optional fitted-camera projection pass, disabled by default because it added
  forehead/mouth noise;
- neighbor fill, mirror fill, material fallback, seam smoothing, and skin
  coherence cleanup;
- per-iteration outputs for `0..5`;
- final selection from the earliest clean-enough iteration, usually `iter_01`.

Private metrics:

| Person | Variant | Selected final | Mean luma error | Seam score | Observed coverage |
| --- | --- | ---: | ---: | ---: | ---: |
| Juseop | no lighting | 1 | 27.48 | 0.640 | 34.2% |
| Juseop | lighting normalized | 1 | 27.12 | 0.631 | 34.3% |
| Eunchae | no lighting | 1 | 36.99 | 1.027 | 23.5% |
| Eunchae | lighting normalized | 1 | 37.16 | 1.114 | 23.6% |

What improved:

- black holes and extreme patching were mostly reduced;
- review sheets were easier to inspect;
- selected final iteration avoided the worst late-iteration flattening.

What failed:

- still not product-quality;
- face identity looked too soft and avatar-like;
- eyes, eyelids, mouth interior, lips, and brows needed dedicated material or
  geometry handling;
- repeated iterations could improve loss while visually worsening the face.

Decision:

- keep all three base mesh candidates active;
- do not choose a mesh winner from v3;
- do not keep tuning Texture Baker as the main path after FaceBuilder looks
  stronger.

## 21. Future Log Entry Template

Use this structure when adding major future experiments:

```text
Date:
Goal:
Chosen model or structure:
Reason for choice:
What was actually run:
What succeeded:
What failed:
Cause:
Fix or direction change:
Current remaining risk:
Next validation:
Related commit/document:
```

Do not record only the final result. Record the reason a decision changed.

## 22. 2026-06-27 FaceBuilder/KeenTools Pivot And Automation Verification

After Texture Baker v3, the user judged the output quality as far below the
product bar. This stopped the project from treating the custom
Pixel3DMM/FLAME texture baker as the main visual-quality path.

The user input constraint stayed the same:

```text
ordinary selfies + app scan frames
```

The app cannot require studio photographs, strict angle guides, manual pin
editing, or a human operator. The system must handle scoring, filtering,
alignment, and fallback internally.

### Why The Custom Texture Baker Was Demoted

Texture Baker v1/v2/v3 exposed a product-level mismatch:

- a segmented 2D face cannot simply be pasted onto a fixed 3D mesh;
- every photo must be aligned to the 3D head with accurate camera/pose;
- small projection errors create visible seams around the nose, mouth, forehead,
  and eyes;
- lighting differences make skin patches disagree;
- occlusions can poison the texture;
- filling holes can remove black regions but flatten identity detail;
- repair iterations can lower numeric loss while visually destroying details;
- the output quality was too low to choose among base mesh candidates.

Conclusion: v3 remains a research record and source of reusable
post-processing ideas, but it should not be the main engine for the next
product iteration.

### External Engine Review

The user asked about MetaHuman, Polycam, and KeenTools.

Assessment:

- MetaHuman can be useful as a high-quality avatar/reference ecosystem, but it
  is not the immediate lightweight server path for an automatic bald-head hair
  app pipeline.
- Polycam is useful as a scanning-product reference, but it is not directly
  aligned with the current selfie-plus-app-scan input contract.
- KeenTools FaceBuilder is the most relevant because it fits head geometry and
  photo camera positions from multiple images inside Blender.

Key difference:

```text
FaceBuilder:
  photos + pins/landmarks
  -> jointly adjusts face/head shape and per-photo camera alignment
  -> builds texture after model and photos match

Texture Baker v3:
  mostly fixed Pixel3DMM/FLAME mesh
  -> tries to paste/repair photo pixels on top
  -> does not strongly refit shape/cameras from all photos together
```

This explains why FaceBuilder can start from a visibly better head before
Hair App-specific post-processing.

### Manual FaceBuilder Result

The user manually used Blender + FaceBuilder with Juseop photos and exported
OBJ/MTL/texture files. The visible result was much stronger than custom Texture
Baker v3 review sheets.

That did not make FaceBuilder output production-ready. It made it a stronger
substrate. Hair App still needs automation, scoring, review sheets,
hair/headwear/shirt/background cleanup, scalp/neck/rear-head completion,
eye/mouth/material handling, GLB export, and hair fitting.

### Blender And KeenTools Code Investigation

Local paths:

```text
Blender executable:
C:\Program Files\Blender Foundation\Blender 5.1\blender.exe

KeenTools extension folder:
C:\Users\User\AppData\Roaming\Blender Foundation\Blender\5.1\extensions\user_default\keentools
```

The visible Python add-on files are mostly Blender integration, UI, operator,
loader, and control code. Core FaceBuilder solving logic is in the compiled
local `pykeentools` `.pyd` binary. It should be treated as a licensed black-box
dependency, not reverse-engineered.

Practical near-term server design:

```text
backend job
  -> launch Blender in background mode
  -> drive KeenTools/FaceBuilder via script
  -> save private mesh/texture/blend/review outputs
  -> post-process and export app-ready assets
```

Blender is the server-side 3D production engine, not the app viewer. The app
should receive GLB/mobile assets and display them with Three.js or a native 3D
viewer.

### Headless Automation Verification

Verified on 2026-06-27:

- Blender 5.1.2 runs in background mode.
- KeenTools 2026.2.0 loads in background mode.
- `pykeentools` imports successfully.
- A FaceBuilder object can be constructed from script.
- `detect_faces` is callable.
- `detect_face_pose` is reachable.
- preset pin solving is reachable.
- TextureBuilder APIs are visible and callable.

Existing-scene probe:

- the private `C:\Users\User\Desktop\blender.blend` scene had one FaceBuilder
  head, 11 cameras, and 6 pinned cameras;
- re-aligning an already pinned camera succeeded;
- four of five unpinned camera auto-align attempts succeeded;
- one no-face failure likely came from an eyeglasses selfie;
- texture baking ran in background mode and saved a private PNG.

Empty-scene automation v0:

- started from a blank Blender background session;
- created a FaceBuilder head;
- selected two private Juseop photos;
- added both as FaceBuilder cameras;
- one photo aligned and received preset pins;
- one photo failed face detection;
- texture baking succeeded from the aligned photo;
- private `.blend`, texture PNG, and `result.json` were saved under ignored
  `private_outputs/facebuilder_bridge/`.

Conclusion: full product automation is not solved, but the bridge is real.
Codex can run headless Blender, drive key FaceBuilder operations, inspect
results, and iterate scripts.

### Updated Project Decision

Current near-term direction:

```text
ordinary selfies + app scan frames
  -> photo/frame scoring
  -> automated FaceBuilder solve in headless Blender
  -> private mesh + texture + blend
  -> Hair App bald-head post-processing
  -> front-to-45 review sheets
  -> hairline/scalp fitting
  -> collision correction
  -> mobile GLB
```

Pixel3DMM/FLAME and Texture Baker v1/v2/v3 remain historical research,
fallbacks, and sources of reusable ideas. They are not the main quality path
unless FaceBuilder fails a specific gate or the user explicitly asks to return.

### Immediate Next Work

1. Build FaceBuilder automation v1 for Juseop/Eunchae private photo folders.
2. Add photo/frame scoring before FaceBuilder:
   - blur;
   - face detection confidence;
   - pose/yaw/pitch/roll;
   - lighting/exposure;
   - glasses, hair, headwear, hand, phone, shadow occlusion;
   - eyes closed;
   - mouth open;
   - landmark stability where available.
3. Add retry/reject logic for failed auto-align photos.
4. Save private manifests for selected/rejected/aligned/baked outputs.
5. Generate review sheets at 0, +-15, +-30, and +-45 degrees.
6. Implement bald-head post-processing:
   - remove hair/headwear/shirt/background leakage;
   - fill scalp, neck, rear head, and low-confidence skin regions;
   - improve eyes, mouth, lips, ears, brows, and skin material;
   - preserve confidence/provenance maps.
7. Decide whether to use FaceBuilder mesh directly or transfer to a controlled
   Hair App mesh after reviewing better exports.

## 23. Archive: Pixel3DMM V4 Baseline

This section preserves the former standalone `docs/pixel3dmm_v4.md` content in
organized English form. The standalone file was deleted because Pixel3DMM is no
longer the main engine path.

### 23.1 Document Role

The notebook and this archive have different roles:

- `experiments/milestone1_geometry_bakeoff/pixel3dmm_colab_v4.ipynb` is the
  executable, output-free Colab pipeline.
- This archive records the contract, source audit, error history, measured
  results, interpretation, and next experiment plan.
- Private input photos, crops, landmarks, masks, predicted maps, meshes,
  videos, and Drive folders stay outside Git.

Audited Pixel3DMM commit:

```text
fcd1fa973c7715b02a8948dfc679dff53cf85924
```

### 23.2 Executive Result

The first complete Pixel3DMM baseline worked from eight independent photos
through a reproducible FLAME geometry artifact:

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

Confirmed on NVIDIA A100-SXM4-80GB:

- environment and CUDA extension checks passed;
- all required FLAME assets passed;
- crop passed 8/8;
- PIPNet WFLW-98 landmarks passed 8/8;
- FaRL segmentation passed 8/8;
- normal inference passed 8/8;
- UV inference passed 8/8;
- multi-photo tracking completed;
- `canonical.ply` contains 5,023 vertices and 9,976 faces;
- official tracking video and all eight overlays were visually inspected;
- quick fixed-context diagnostic showed fitted identity shape beating mean
  FLAME on all 8/8 views.

Correct conclusion:

> V4 is a successful first geometry baseline. It personalizes the mean FLAME
> head in a diagnostic setting, but it does not prove production-grade identity
> or measured hidden-scalp accuracy.

### 23.3 Runtime And Pinned Components

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
| Landmark embedding fallback | pinned DECA `a11554ae2a2b0f3998cf1fa94dd4db03babb34a2` |
| DECA embedding SHA-256 | `8095348eeafce5a02f6bd8765146307f9567a3f03b316d788a2e47336d667954` |
| GPU used | NVIDIA A100-SXM4-80GB |

H100 access was available, but compute does not solve unobserved scalp geometry,
wrong representation, licensing, or data quality.

### 23.4 Final Crop And Preprocessing Configuration

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

### 23.5 Tracking Configuration

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
```

MICA was disabled for the baseline because the project first needed a clean
official no-MICA control.

### 23.6 Intermediate Outputs

- Crop: persistent 512x512 face crop used by downstream models.
- PIPNet landmarks: WFLW-98 landmarks used by tracking.
- FaRL segmentation: semantic face-part label map, not a UV map.
- Predicted normal map: per-pixel surface-normal prediction used as dense
  geometry supervision.
- Predicted UV map: dense correspondence map from visible image pixels to
  canonical FLAME surface points.
- FLAME tracking: joint optimization that estimates shared shape/identity and
  per-frame pose, expression, and camera.

### 23.7 Source Audit And Crop Change

Official order:

```text
source image
  -> FaceBoxes crop
  -> PIPNet landmarks
  -> FaRL segmentation
  -> Pixel3DMM normal/UV network
  -> FLAME tracking
```

The apparent "second crop" is internal to PIPNet/FaRL and should not be
confused with the persistent dataset crop.

Root cause of broken early crops:

- the original code assumed more continuous/video-like input;
- Hair App used independent photos;
- one global/static crop could cut faces in other photos;
- roll normalization with weak crop-time points added risk.

Final decision:

- each independent photo gets its own FaceBoxes crop;
- highest-confidence face is selected;
- square crop uses margin `1.42`;
- persistent crop remains no-roll;
- metadata records all source-to-crop transforms.

### 23.8 Live Error And Fix Record

Fixes and lessons:

- Colab conda restart can erase runtime state; install/restart/check gates must
  be explicit.
- Google Drive mount issues are environment/auth state, not model failures.
- FLAME asset distribution differs across archives; required file checks are
  mandatory.
- Manual embedding recovery can be lost if runtime disconnects; reproduce from
  pinned commits when possible.
- FaceBoxes legacy imports need compatibility handling.
- Wrong face selection in profile images required confidence-first safeguards.
- FaRL weight download interruption needs resumable or verified download logic.
- PyTorch 2.6+ changed `torch.load(weights_only=...)`; official trusted
  Lightning checkpoint needed explicit handling.
- Mesh preview packages can install into the wrong Python interpreter; verify
  interpreter paths.
- V4 retained compatibility hardening rather than replacing official logic
  blindly.

### 23.9 Generated Artifact Contract

Generated private artifacts include:

- source-photo manifest;
- crop images;
- crop metadata;
- PIPNet landmarks;
- FaRL segmentation;
- predicted normals;
- predicted UV maps;
- tracking config;
- `canonical.ply`;
- per-view fitted renders;
- tracking video;
- evaluation metrics;
- run manifest.

Never commit those private artifacts.

### 23.10 Geometry Validation Results

Mean FLAME versus fitted mesh displacement showed that the fitted shape was not
just an unchanged template.

Same-camera shape-swap diagnostic:

- fitted identity landmark error: about `5.8803 px`;
- mean FLAME fixed-context error: about `7.1109 px`;
- quick gain: about `1.2306 px`, roughly `17.3%`;
- fitted won 8/8 views in that diagnostic.

Limitations:

- camera and expression were not fully refitted for every control condition;
- this was a useful diagnostic, not final proof of identity accuracy;
- later refitted mean-shape control weakened the no-MICA identity claim.

### 23.11 Optimizer Loss Meaning

Important fit drivers:

- landmark loss;
- silhouette loss;
- normal supervision;
- expression regularization;
- shape regularization;
- general shape prior;
- optional mouth landmark terms, disabled in this configuration;
- camera and pose terms through the tracker.

Loss must be interpreted visually and with controls. A lower loss does not
automatically mean a better product head.

### 23.12 Limitations

Current limitations:

- hidden scalp/rear head is not directly measured;
- FLAME topology may not be ideal for all hair fitting needs;
- personal identity shape was not conclusively validated over mean-shape
  control;
- private data coverage is limited;
- texture quality was not solved by Pixel3DMM alone;
- product backend does not yet run the notebook;
- licensing for commercial deployment requires separate review.

### 23.13 Improvement Roadmap

Completed:

- MICA identity-prior and init-only A/B;
- fully refitted mean-shape control;
- cross-context no-MICA shape versus mean-shape validation;
- Texture Baker v1 diagnostic across frozen model trio;
- Texture Baker v2 camera-aware/front-focused path;
- Texture Baker v3 iterative avatar bake.

Remaining historical priorities:

- compare optimization resolution 256 versus 512;
- preserve prediction precision;
- add robust regional landmarks;
- improve masks and dense losses;
- fine-tune normal/UV networks only after baseline gaps are clear;
- add high-frequency face refinement;
- acquire actual scalp evidence if the product ever requires it.

### 23.14 Private 19-View Run

The private 19-view run combined selected selfies and selected app-scan frames.

It produced:

- no-MICA Pixel3DMM tracking;
- fitted mean-shape control;
- model trio for texture review;
- private manifests and outputs.

Result:

- no-MICA completed;
- mean-shape control completed;
- cross-context landmark gate did not justify locking no-MICA as final personal
  shape;
- all three candidates stayed active for texture review.

### 23.15 Notebook Gates

The notebook intentionally used gates:

1. GPU and CUDA architecture check.
2. Conda install/restart.
3. Pinned repository checkout.
4. Environment and CUDA extension build.
5. Dependency/checkpoint setup.
6. Drive and FLAME asset installation.
7. Private input discovery.
8. V4 independent no-roll crop.
9. Source/crop visual gate.
10. PIPNet and FaRL.
11. Preprocessing count/visual gate.
12. Drive preprocessing bundle.
13. `PREPROCESSING_APPROVED=True` only after human inspection.
14. Normal/UV inference and exact count gate.
15. Tracking.
16. Mesh/result visualization.
17. Full Drive save and manifest.
18. Quantitative evaluation.

Do not bypass a failed count gate merely because later cells can technically
run.

### 23.16 Repository And Privacy Rules

Active executable research files at that time:

- `experiments/milestone1_geometry_bakeoff/pixel3dmm_colab_v4.ipynb`
- `experiments/milestone1_geometry_bakeoff/freeze_model_trio_for_texture.py`

Never commit:

- private photos or scans;
- crop/landmark/segmentation outputs;
- embeddings, meshes, textures, or videos;
- private Drive paths containing identity information;
- notebook output cells containing user data.

### 23.17 Official Source Links

- Pixel3DMM repository: <https://github.com/SimonGiebenhain/pixel3dmm>
- Audited tracker:
  <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/src/pixel3dmm/tracking/tracker.py>
- Tracking configuration:
  <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/configs/tracking.yaml>
- Network inference:
  <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/scripts/network_inference.py>
- FLAME wrapper:
  <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/src/pixel3dmm/tracking/flame/FLAME.py>

## 24. Archive: Texture Baker Loader And v1-v3 Experiments

This section preserves the former standalone `experiments/texture_baker/README.md`
content in organized English form. The standalone README was deleted because
Texture Baker is no longer the main product-quality path.

### 24.1 Purpose

The Texture Baker experiments tried to place real photo pixels onto frozen
Pixel3DMM/FLAME mesh candidates and then fill missing regions.

Historical private entrypoint:

```text
output/<person>/models/model_trio_for_texture/model_trio_manifest.json
```

The loader expected private manifests and wrote private review outputs. It was
never supposed to commit photos, meshes, landmarks, masks, textures, renders, or
review sheets.

### 24.2 Local And Colab Checks

Local Windows checks verified that:

- model trio manifests could be discovered;
- required files existed;
- basic mesh statistics could be read;
- private paths stayed outside Git.

Colab checks verified that:

- Drive layout existed;
- private input/output/shared folders were preserved;
- expected manifests could be loaded;
- outputs stayed in private Drive folders.

Private Drive layout:

```text
MyDrive/hair_app/input/
MyDrive/hair_app/output/
MyDrive/hair_app/shared/
MyDrive/hair_app/data_layout_manifest.json
```

### 24.3 First Observed-Texture Smoke Test

The first smoke test used crop RGB plus Pixel3DMM UV maps and segmentation
labels to write coverage/confidence diagnostics.

Result:

- the concept was technically possible;
- but observed coverage was weak;
- black holes dominated review renders;
- eye/mouth regions were unusable as raw photo texture.

### 24.4 Current Preview Bake At That Time

Preview bake goals:

- use Pixel3DMM UV PNG red/green channels as U/V;
- combine segmentation and confidence;
- produce a visible `base_color` texture;
- generate coverage maps;
- provide quick review images.

This was diagnostic, not product quality.

### 24.5 Mesh Texture Preview

The preview renderer loaded:

- mesh vertices/faces;
- UV coordinates;
- candidate texture;
- confidence/fallback masks;
- simple material fallback.

It rendered yaw sheets so the user could inspect front and side views.

### 24.6 One-File 8-View Comparison Sheet

The review tool generated one sheet showing each person and mesh candidate at
multiple yaws. The goal was to let the user visually compare base mesh
candidates after texture was applied.

This failed as a base-mesh decision tool because texture quality was too low.

### 24.7 2026-06-26 Review Result

Observed v1/v2 review issues:

- large black regions;
- visible seams;
- poor eye/mouth material;
- lighting mismatch;
- low coverage;
- hair/headwear leakage;
- weak side-face confidence;
- hidden scalp and neck relying on fallback.

Decision:

- do not choose a mesh winner;
- improve texture/completion first.

### 24.8 Texture Baker v2 Plan

v2 aimed to be camera-aware and front-focused:

- score frames before use;
- favor front-to-45 degree evidence;
- use fitted camera projection where reliable;
- use z-buffer visibility;
- use view-angle weighting;
- use segmentation/occlusion confidence;
- preserve source photo provenance;
- separate observed and generated/fallback regions.

### 24.9 2026-06-26 Texture Baker v2 Hybrid Run

v2 used:

- camera pass;
- Pixel3DMM UV correspondence pass;
- segmentation confidence;
- fallback material;
- front-to-45 review sheet.

Because fitted camera projection was still inaccurate, central facial detail
relied heavily on Pixel3DMM UV correspondence. This hybrid approach reduced some
holes but left seams and bad regions.

### 24.10 Cleanup And Completion Pass

`texture_cleanup_completion.py` was implemented as a post-process over v2
atlases.

Outputs:

```text
base_color_cleanup_completed.png
cleanup_removed_mask.png
completion_replaced_mask.png
base_color_material_reference.png
cleanup_completion_manifest.json
```

What it did:

- removed low-confidence or skin-color-outlier texels;
- replaced unreliable forehead/scalp/neck/boundary/ear regions with simple
  skin-region materials;
- preserved central observed face detail when confidence allowed;
- kept lips/eyes separate for later dedicated assets.

Result:

- black holes and obvious contamination were reduced;
- hidden scalp/neck became plausible but flat;
- central seams, eye assets, lighting normalization, and render-to-selfie
  refinement remained unsolved.

### 24.11 Feature/Seam And Fitted-Camera Compare Pass

Added or extended:

- `texture_cleanup_completion.py`: feature/seam refinement after cleanup;
- `textured_mesh_preview.py`: material-like eye overlay and `selfie_optimized`
  lookup;
- `make_texture_comparison_sheet.py`: render `selfie_optimized` textures;
- `fitted_camera_selfie_compare.py`: fitted-camera crop/render comparison,
  lighting-matched renders, diff maps, and weak UV residual preview.

This was not neural-network training and did not change geometry.

Observed result:

- empty regions were mostly replaced by skin/scalp fallback;
- eyes and lips became more visible but synthetic;
- fitted-camera comparison became upright after `projection_flip_y`;
- residual pass reduced masked luma error but did not solve identity, seams, or
  lighting.

### 24.12 Texture Baker v3 Iterative Avatar Bake

`texture_baker_v3.py` was implemented after v2 cleanup and fitted-camera
comparison.

What v3 did:

- scored and filtered frames with `evidence_quality_report.py`;
- used Pixel3DMM UV correspondence maps as the main direct bake source;
- kept low-weight fitted-camera projection optional and disabled by default;
- wrote two variants: `v3_no_lighting` and `v3_lighting_normalized`;
- ran iterations `0..N`;
- saved texture, confidence, observed mask, filled mask, metrics,
  fitted-camera comparison sheet, and front-to-45 review sheet;
- used weighted multi-frame color rather than one best source texel;
- filled empty/bad texels across skin/scalp/neck/ear regions;
- applied neighbor fill, mirror fill, material fallback, seam smoothing, and
  skin coherence cleanup;
- selected the earliest clean-enough iteration, usually `iter_01`, to avoid
  over-smoothing.

Representative command shape:

```powershell
python experiments\texture_baker\texture_baker_v3.py `
  --private-root "<private_root>" `
  --person "<person_a>" `
  --person "<person_b>" `
  --variant v3_no_lighting `
  --variant v3_lighting_normalized `
  --output-prefix v3 `
  --iterations 5 `
  --min-score 0.62 `
  --max-abs-yaw 58 `
  --atlas-size 512 `
  --image-size 512
```

Private output shape:

```text
output/<person>/texture_baker/v3_v3_no_lighting/
output/<person>/texture_baker/v3_v3_lighting_normalized/
output/_comparison/v3_<person>_variant_overview.png
```

Metrics:

| Person | Variant | Selected final | Mean luma error | Seam score | Observed coverage |
| --- | --- | ---: | ---: | ---: | ---: |
| Juseop | no lighting | 1 | 27.48 | 0.640 | 34.2% |
| Juseop | lighting normalized | 1 | 27.12 | 0.631 | 34.3% |
| Eunchae | no lighting | 1 | 36.99 | 1.027 | 23.5% |
| Eunchae | lighting normalized | 1 | 37.16 | 1.114 | 23.6% |

Observed result:

- v3 was cleaner than raw v1/v2 sheets;
- it was still not product-quality;
- repeated iterations lowered some metrics while flattening identity;
- lighting normalization helped Juseop slightly in metrics;
- Eunchae remained harder because of lower coverage and forehead/hair/headwear
  contamination risk;
- eyes, eyelids, mouth interior, lips, and brows required dedicated material or
  geometry handling;
- base mesh winner should not be selected from v3 alone.

### 24.13 Lessons Preserved From Texture Baker

Reusable ideas:

- photo/frame scoring;
- observed versus fallback masks;
- confidence maps;
- front-to-45 review sheets;
- lighting-normalization tests;
- metrics plus human visual review;
- material fallback for scalp, neck, ears, and hidden regions;
- private manifest/output discipline.

Final decision:

Texture Baker remains a historical experiment and possible source of
post-processing ideas. It is not the current main product path after the
FaceBuilder pivot.

## 25. Detailed Retired-Engine Command And Metric Archive

This section preserves the operational details that were previously scattered
through the old standalone documents. Paths use placeholders when the original
path contained private Drive or person-specific information.

### 25.1 Pixel3DMM MICA A/B Metrics

MICA prior run:

- MICA preprocessing completed 8/8.
- MICA tracking produced `canonical.ply`, eight per-view meshes, and a result
  video.
- Canonical displacement versus no-MICA after centroid alignment:
  - mean: `4.2749 mm`;
  - median: `3.2221 mm`;
  - p95: `8.0128 mm`;
  - max: `17.0235 mm`.
- In the no-MICA camera/pose/expression context, MICA worsened average landmark
  error from `5.8803 px` to `7.2801 px`, losing 8/8 views.
- In the MICA camera/pose/expression context, MICA improved `6.0530 px` to
  `5.7006 px`, winning 5/8 views.
- Native-run comparison improved only `0.1797 px`; this was not a fixed-context
  comparison.

MICA init-only run:

- In the no-MICA context, MICA init-only worsened `5.8803 px` to `7.2036 px`,
  losing 8/8 views.
- In the MICA init-only context, it improved `5.9761 px` to `5.7245 px`,
  winning 5/8 views.
- Native-run comparison improved only `0.1558 px`.

Interpretation:

- MICA changes final geometry, but the fixed-context gate preferred no-MICA
  under the original no-MICA solution.
- The small native gain likely came from camera/pose/expression compensation
  around the MICA-shaped identity.
- Profile and contour-heavy views were risky.
- MICA remains a research reference, not the default Hair App geometry path.

Comparison helper:

```text
experiments/milestone1_geometry_bakeoff/validate_mica_vs_no_mica.py
```

### 25.2 Pixel3DMM Private 19-View Metrics

The mean-shape sanity check:

```json
{
  "no_mica_shape_l2": 10.628931045532227,
  "mean_shape_l2": 4.09764743380947e-06,
  "shape_difference_l2": 10.62893009185791,
  "shape_param_count": 300
}
```

Cross-context landmark comparison:

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

- The personal no-MICA mesh was visibly different from raw FLAME and from the
  fitted mean-shape control.
- It remained useful as a temporary development mesh.
- Landmark gates did not prove no-MICA identity shape was better than a refitted
  mean shape.
- The practical next test became visual texture comparison across the frozen
  raw FLAME, fitted mean-shape, and personal no-MICA candidates.

### 25.3 Texture Baker Loader Commands

Local Windows loader check:

```powershell
python experiments\texture_baker\texture_baker_loader.py `
  --private-root "<private_root>"
```

Colab loader check:

```python
from google.colab import drive
drive.mount("/content/drive")

%cd /content/hair_app
!git pull --ff-only
!python experiments/texture_baker/texture_baker_loader.py \
  --private-root /content/drive/MyDrive/hair_app
```

Expected historical bundles:

- Juseop: three frozen mesh candidates from
  `output/<person>/models/model_trio_for_texture/model_trio_manifest.json`.
- Eunchae: three frozen mesh candidates from
  `output/<person>/models/model_trio_for_texture/model_trio_manifest.json`:
  `raw_flame_template`, `base_flame2023`, and `personal_no_mica`.

### 25.4 Texture Baker v1 Preview Commands

First one-frame smoke test:

```python
!python experiments/texture_baker/observed_texture_baker.py \
  --private-root /content/drive/MyDrive/hair_app \
  --person "<person>" \
  --atlas-size 256 \
  --max-frames 1 \
  --output-name observed_v0_smoke \
  --splat-radius 1
```

Juseop preview shape:

```python
!python experiments/texture_baker/observed_texture_baker.py \
  --private-root /content/drive/MyDrive/hair_app \
  --person "<juseop>" \
  --atlas-size 512 \
  --output-name observed_v6_primary00000_faceonly_secondary0_preview \
  --splat-radius 1 \
  --blend-mode weighted \
  --primary-frame-id 00000 \
  --secondary-central-weight 0 \
  --mask-erode-iterations 2 \
  --preview-fill-iterations 8 \
  --preview-fill-min-neighbors 5
```

Eunchae preview shape:

```python
!python experiments/texture_baker/observed_texture_baker.py \
  --private-root /content/drive/MyDrive/hair_app \
  --person "<eunchae>" \
  --atlas-size 512 \
  --output-name observed_v15_primary00004_wideface_strict_occlusion_preview \
  --splat-radius 1 \
  --blend-mode weighted \
  --primary-frame-id 00004 \
  --secondary-central-weight 0.02 \
  --primary-side-weight 1.0 \
  --secondary-side-weight 0.0 \
  --mask-erode-iterations 2 \
  --occlusion-margin-iterations 10 \
  --skin-occlusion-filter \
  --skin-occlusion-chroma-threshold 30 \
  --skin-occlusion-luma-threshold 52 \
  --secondary-central-crop-radius-x 0.52 \
  --secondary-central-crop-radius-y 0.78 \
  --preview-fill-iterations 8 \
  --preview-fill-min-neighbors 5
```

Historical output shape:

```text
output/<person>/texture_baker/<output-name>/
  base_color_observed.png
  coverage.png
  confidence.png
  source_view_map.png
  base_color_preview_filled.png
  texture_manifest.json
```

### 25.5 Mesh Preview And Comparison Sheet Commands

Mesh preview command shape:

```python
!python experiments/texture_baker/textured_mesh_preview.py \
  --private-root /content/drive/MyDrive/hair_app \
  --person "<person_a>" \
  --person "<person_b>" \
  --texture-kind preview_filled \
  --uv-mode flip_y \
  --depth-mode max \
  --view front \
  --view left_35 \
  --view right_35 \
  --material-fallback \
  --fallback-confidence-threshold 5 \
  --eye-overlay \
  --write-obj
```

Expected UV asset:

```text
shared/models/pixel3dmm_assets/flame_uv_coords.npy
```

One-file 8-view comparison sheet:

```python
!python experiments/texture_baker/make_texture_comparison_sheet.py \
  --private-root /content/drive/MyDrive/hair_app \
  --texture-kind preview_filled \
  --image-size 512 \
  --padding 42 \
  --uv-mode flip_y \
  --depth-mode max \
  --mask-mode none \
  --material-fallback \
  --fallback-confidence-threshold 5 \
  --eye-overlay
```

Historical output:

```text
output/_comparison/face_texture_model_comparison_8view_wideface_eyes_conf5_v4.png
output/_comparison/face_texture_model_comparison_8view_wideface_eyes_conf5_v4.json
```

Texture completion A/B command:

```python
!python experiments/texture_baker/complete_texture_for_review.py \
  --private-root /content/drive/MyDrive/hair_app
```

### 25.6 Texture Baker v2 Front-Focused Sheet Command

Historical v2 output:

```text
output/<person>/texture_baker/observed_v2_camera_visibility_front45_preview/
output/_comparison/face_texture_model_comparison_front45_v2.png
output/_comparison/face_texture_model_comparison_front45_v2.json
```

Command shape:

```powershell
python experiments\texture_baker\make_texture_comparison_sheet.py `
  --private-root "<private_root>" `
  --texture-name observed_v2_camera_visibility_front45_preview `
  --texture-kind preview_filled `
  --image-size 512 `
  --padding 58 `
  --uv-mode flip_y `
  --depth-mode max `
  --mask-mode none `
  --material-fallback `
  --fallback-confidence-threshold 5 `
  --eye-overlay `
  --yaw-degree -45 --yaw-degree -30 --yaw-degree -15 `
  --yaw-degree 0 `
  --yaw-degree 15 --yaw-degree 30 --yaw-degree 45 `
  --output-path "<private_root>\output\_comparison\face_texture_model_comparison_front45_v2.png"
```

### 25.7 Cleanup, Feature/Seam, And Fitted-Camera Commands

Cleanup command:

```powershell
python experiments\texture_baker\texture_cleanup_completion.py `
  --private-root "<private_root>" `
  --person "<person_a>" `
  --person "<person_b>" `
  --texture-name observed_v2_camera_visibility_front45_preview `
  --save-debug-masks
```

Cleanup outputs:

```text
base_color_cleanup_completed.png
cleanup_removed_mask.png
completion_replaced_mask.png
base_color_material_reference.png
cleanup_completion_manifest.json
output/_comparison/face_texture_model_comparison_front45_v2_cleanup.png
output/_comparison/face_texture_model_comparison_front45_v2_cleanup.json
```

Feature/seam and selfie-optimized outputs:

```text
output/_comparison/face_texture_model_comparison_front45_v3_features.png
output/_comparison/face_texture_model_comparison_front45_v3_features.json
output/_comparison/face_texture_model_comparison_front45_v4_selfie_optimized.png
output/_comparison/face_texture_model_comparison_front45_v4_selfie_optimized.json
output/<person>/texture_baker/fitted_camera_selfie_compare_v1/
output/<person>/texture_baker/observed_v2_camera_visibility_front45_preview/base_color_selfie_optimized_preview.png
```

Fitted-camera comparison command:

```powershell
python experiments\texture_baker\fitted_camera_selfie_compare.py `
  --private-root "<private_root>" `
  --person "<person_a>" `
  --person "<person_b>" `
  --texture-name observed_v2_camera_visibility_front45_preview `
  --texture-kind cleanup_completed `
  --max-frames 4 `
  --tile-size 256
```

Feature review sheet command:

```powershell
python experiments\texture_baker\make_texture_comparison_sheet.py `
  --private-root "<private_root>" `
  --texture-name observed_v2_camera_visibility_front45_preview `
  --texture-kind cleanup_completed `
  --image-size 512 `
  --padding 58 `
  --uv-mode flip_y `
  --depth-mode max `
  --mask-mode none `
  --material-fallback `
  --eye-overlay `
  --yaw-degree -45 --yaw-degree -30 --yaw-degree -15 `
  --yaw-degree 0 `
  --yaw-degree 15 --yaw-degree 30 --yaw-degree 45 `
  --output-path "<private_root>\output\_comparison\face_texture_model_comparison_front45_v3_features.png"
```

### 25.8 Texture Baker v3 Command And Outputs

Command shape:

```powershell
python experiments\texture_baker\texture_baker_v3.py `
  --private-root "<private_root>" `
  --person "<person_a>" `
  --person "<person_b>" `
  --variant v3_no_lighting `
  --variant v3_lighting_normalized `
  --output-prefix v3 `
  --iterations 5 `
  --min-score 0.62 `
  --max-abs-yaw 58 `
  --atlas-size 512 `
  --image-size 512
```

Output shape:

```text
output/<person>/texture_baker/v3_v3_no_lighting/
output/<person>/texture_baker/v3_v3_lighting_normalized/
output/_comparison/v3_<person>_variant_overview.png
```

Final historical interpretation:

- v3 was cleaner than v1/v2;
- it still failed the product bar;
- repeated iteration could improve metrics while damaging visible identity;
- the current project should reuse its scoring, confidence, and review-sheet
  ideas, but not continue it as the main head-generation path.

## 26. 2026-06-27 FaceBuilder v1/v2/v3 Batch Automation

Retirement note: this section is preserved as a historical record of the first
FaceBuilder batch automation attempt. Its generated private outputs were
retired on 2026-06-28 after the texture-bake parity bug was found. The current
active FaceBuilder comparison is the v1/v2/v3/v4 reset described near the top
of this file.

### 26.1 User Request

The user asked for three comparable FaceBuilder versions for Juseop and Eunchae:

- `v1`: use all photos, plus post-processing, bald-head preparation, hair-app
  GLB conversion logic, and automatic review sheets.
- `v2`: v1 plus photo quality scoring.
- `v3`: v2 plus auto-align improvement.

The user also requested that all private generated data be organized under
Google Drive in clean `facebuilder_v1`, `facebuilder_v2`, and `facebuilder_v3`
folders, while source code and documentation are pushed to GitHub. Private
photos, meshes, textures, renders, and GLBs must remain out of Git.

### 26.2 Implemented Scripts

New tracked scripts:

```text
experiments/facebuilder_bridge/facebuilder_version_runner.py
experiments/facebuilder_bridge/blender_facebuilder_batch_scene.py
```

`facebuilder_version_runner.py` runs from normal Python. It:

- reads private Juseop and Eunchae photo folders;
- scores images;
- prepares Drive output folders;
- writes input manifests and quality reports;
- creates normalized working images and v3 alignment candidates;
- launches Blender in background mode;
- captures Blender stdout/stderr logs as bytes;
- creates review sheets from source thumbnails and yaw renders;
- writes batch summaries.

`blender_facebuilder_batch_scene.py` runs inside Blender. It:

- creates a FaceBuilder head;
- adds image candidates as FaceBuilder cameras;
- runs code-only detect-face, detect-pose, preset-pin solve, and mesh update;
- disables texture baking for failed or gated cameras;
- saves FaceBuilder state;
- bakes a texture;
- writes a cleanup texture and cleanup report;
- applies a Hair App material placeholder;
- exports OBJ and GLB;
- renders review images at `0, 15, 30, 45, -15, -30, -45` degrees;
- writes `run_manifest.json` and alignment reports.

### 26.3 Version Definitions

`v1`:

- all readable photos are attempted;
- no pre-score rejection;
- original photos are used as FaceBuilder cameras;
- all successful original cameras can contribute to texture.

`v2`:

- adds photo quality scoring and selection;
- scoring includes blur, exposure, contrast, clipping, resolution, OpenCV face
  size/center signals, and simple color-cast scoring;
- the current threshold was `0.80`.

`v3`:

- uses v2 selection;
- adds face-centered and wide face-crop alignment candidates;
- uses original/autocontrast/brightness-sharpness candidates as retry helpers;
- adds a texture gate:
  - frontal and color-clean crops can contribute to texture;
  - profile/side/heavily clipped candidates can still help alignment;
  - gated candidates are disabled for texture baking.

### 26.4 Private Output Layout

Output layout per version/person:

```text
<drive_root>/output/facebuilder_v1/<person>/
<drive_root>/output/facebuilder_v2/<person>/
<drive_root>/output/facebuilder_v3/<person>/
  00_input_manifest/
  01_working_images/
  02_alignment/
  03_facebuilder_scene/
  04_exports/
  05_postprocess/
  06_glb/
  07_review_sheets/
  logs/
```

Batch summaries:

```text
<drive_root>/output/facebuilder_versions_batch_manifest.json
<drive_root>/output/facebuilder_versions_summary.json
<drive_root>/output/facebuilder_versions_summary.md
```

These outputs are private and must not be committed.

### 26.5 Latest Private Batch Summary

Latest run summary:

| Version | Person | Selected | Rejected | Aligned | Failed | TexCams | Texture | Cleanup | OBJ | GLB | Review |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- |
| v1 | Juseop | 11 | 0 | 10 | 1 | 10 | yes | yes | yes | yes | yes |
| v1 | Eunchae | 8 | 0 | 7 | 1 | 7 | yes | yes | yes | yes | yes |
| v2 | Juseop | 7 | 4 | 6 | 1 | 6 | yes | yes | yes | yes | yes |
| v2 | Eunchae | 7 | 1 | 6 | 1 | 6 | yes | yes | yes | yes | yes |
| v3 | Juseop | 7 | 4 | 7 | 0 | 2 | yes | yes | yes | yes | yes |
| v3 | Eunchae | 7 | 1 | 7 | 0 | 1 | yes | yes | yes | yes | yes |

Important interpretation:

- v1 proves the baseline all-photo path but includes too much noisy texture
  evidence.
- v2 proves photo scoring and rejection reduce inputs, but original profile
  photos still contaminate texture.
- v3 is the best current automated baseline because all selected photos align,
  and profile/side photos can be used for alignment without necessarily entering
  texture baking.
- v3 still is not product quality.

### 26.6 Visual Quality Findings

Observed improvements:

- v3 reduced alignment failures to zero for both private people in the latest
  run.
- v3 reduced severe colored-light contamination by rejecting/gating bad texture
  sources.
- review sheets and GLBs are generated consistently for all six
  version/person combinations.

Remaining visible failures:

- hair/scalp patches remain on the bald head;
- heuristic cleanup can leave gray/white replacement islands;
- eyes are still not proper eye assets/materials;
- mouth, nostril, brow, and lip regions need semantic treatment;
- neck, ear, and shoulder boundaries can leak clothing/background texture;
- side/profile photos are useful for alignment but risky as texture sources;
- automatic FaceBuilder alignment is not yet as clean as careful manual pinning.

### 26.7 Next Technical Direction

The next improvement should not be another global color-threshold pass. The
needed step is semantic bald-head post-processing:

- face/skin/scalp/hair/background/neck/ear masks;
- eye, iris, eyelid, mouth, lip, brow, nostril materials;
- confidence/provenance maps for observed versus filled regions;
- better occlusion detection before a photo is allowed into texture baking;
- explicit scalp fallback material instead of trying to keep photographed hair;
- mesh strategy evaluation for FaceBuilder direct use versus transfer or
  retopology.

After the bald-head substrate is credible, continue to hair reconstruction,
hairline-aware fitting, collision correction, and mobile GLB viewer work.

## 27. FaceBuilder Mask-Aware Correction Experiment

Date: 2026-06-29.

The next active path is not another raw FaceBuilder texture bake. The project
now keeps FaceBuilder for what it does well, geometry/camera alignment, and
builds a separate mask-aware texture correction path around it.

Tracked experiment folder:

```text
experiments/facebuilder_mask_aware_correction/
```

### 27.1 Motivation

FaceBuilder's UI `Create Texture` can produce a much better baseline than the
earlier broken automated texture path, but its bake still blends whatever
pixels are present in the selected images. This means hair, clothing,
background, hands, phones, perfume bottles, cosmetics, headphones, and other
occluders can enter the raw texture.

The new plan is:

1. use the saved FaceBuilder `.blend` for mesh/camera/UV alignment;
2. prove that the mesh can be reprojected into each input crop;
3. compute which UV regions each image can actually see;
4. build `usable_skin` masks per image;
5. later project only clean skin pixels back into UV and arbitrate against the
   FaceBuilder raw texture.

### 27.2 Implemented Step 0-2 Checks

Step 0 extracted scene data from existing `facebuilder_semantic_v2` `.blend`
files. It verified that Juseop and Eunchae both have:

- FaceBuilder mesh object `FBHead`;
- UV layer `UVMap`;
- raw texture PNG;
- OBJ/GLB exports;
- camera image paths;
- per-camera projection matrices;
- per-camera model matrices;
- triangulated mesh/UV arrays for rasterization.

Private Step 0 output:

```text
G:/내 드라이브/hair_app/output/facebuilder_mask_aware_step0/20260629_194117
```

Step 1 projected the solved FaceBuilder mesh back onto the input crop images as
wireframe overlays. The visual result was good enough to proceed:

- Juseop: 19 cameras projected;
- Eunchae: 8 cameras projected, with one no-pin/failed align camera clearly
  marked.

Private Step 1 output:

```text
G:/내 드라이브/hair_app/output/facebuilder_mask_aware_step1/20260629_195513
```

Step 2 computed UV visibility and source-count maps from the same cameras:

- Juseop texture-enabled coverage: about 35.8% of the UV atlas;
- Juseop max source count: 10 texture cameras;
- Eunchae texture-enabled coverage: about 30.0% of the UV atlas;
- Eunchae max source count: 7 texture cameras.

Private Step 2 output:

```text
G:/내 드라이브/hair_app/output/facebuilder_mask_aware_step2/20260629_200519
```

### 27.3 Step 3 Parser/Object Mask Ablation

Step 3 creates per-image masks for four versions:

```text
v0_farl_only
v1_facexformer_only
v2_farl_grounded_sam
v3_facexformer_grounded_sam
```

Current implementation:

- `v0_farl_only` reads the existing Pixel3DMM V4 FaRL segmentation artifacts
  and creates `usable_skin`, `bad_mask`, `object_mask`, parser visualizations,
  overlays, per-image manifests, and review sheets.
- `v1_facexformer_only` waits for Colab-generated FaceXFormer label masks.
- `v2_farl_grounded_sam` waits for Colab-generated Grounded SAM2 object masks.
- `v3_facexformer_grounded_sam` waits for both external outputs.

Private Step 3 output:

```text
G:/내 드라이브/hair_app/output/facebuilder_mask_aware_step3/20260629_203236
```

The Colab instructions are tracked here:

```text
experiments/facebuilder_mask_aware_correction/STEP3_COLAB.md
```

Expected external mask root:

```text
G:/내 드라이브/hair_app/output/facebuilder_mask_aware_step3_external
```

Once Colab outputs exist, rerun:

```powershell
python experiments\facebuilder_mask_aware_correction\run_step3_masks.py --source-version facebuilder_semantic_v2
```

### 27.4 Step 3 Completion And Step 4 Clean-Pixel Projection

Later on 2026-06-29, the external Colab masks were generated and Step 3 was
rerun. The current Step 3 output is:

```text
<private_drive>/hair_app/output/facebuilder_mask_aware_step3/20260629_212612
```

Current Step 3 interpretation:

- `v0_farl_only`, `v1_facexformer_only`, `v2_farl_grounded_sam`, and
  `v3_facexformer_grounded_sam` are all generated.
- The best near-term candidate is `v2_farl_grounded_sam`.
- FaceXFormer remains experimental because it under-segments some nose/skin
  regions compared with FaRL on the current private photos.
- Grounded SAM is used conservatively. Broad face/head/hair detections and
  oversized masks are rejected before object masks enter `usable_skin`.

Step 4 was then implemented as a diagnostic clean-pixel UV projection stage.
It does not produce the final texture. Instead, it answers this question:

```text
Using FaceBuilder's solved mesh/cameras/UV, where can clean usable-skin pixels
from each input image land on the texture atlas?
```

Tracked Step 4 scripts:

```text
experiments/facebuilder_mask_aware_correction/blender_step4_uv_sample_coords.py
experiments/facebuilder_mask_aware_correction/blender_step4_render_texture.py
experiments/facebuilder_mask_aware_correction/run_step4_clean_projection.py
```

Private Step 4 outputs:

```text
texture-camera-only, active for texture correction:
<private_drive>/hair_app/output/facebuilder_mask_aware_step4/20260629_221621

include-alignment-cameras, diagnostic only:
<private_drive>/hair_app/output/facebuilder_mask_aware_step4/20260629_222438
```

Observed Step 4 numbers at 1024 atlas size:

- Juseop texture-camera-only clean coverage: about 19.9%.
- Juseop with alignment/scan cameras included: about 23.2%.
- Eunchae clean coverage: about 15.5% in both runs because there is no extra
  scan/alignment-only set in this baseline.

Current Step 4 conclusion:

- The FaceBuilder camera/mesh/UV data is usable for clean-pixel reprojection.
- The generated clean projection reduces many raw texture contaminations, but
  coverage is intentionally sparse because only trusted skin pixels are used.
- Eyes, mouth, hairline/scalp, neck, ears, and low-confidence regions still
  require arbitration and completion.
- Juseop scan frames improve frontal coverage but are not allowed to drive the
  active texture result. They remain diagnostic only.

Next active technical step:

```text
Step 5: raw FaceBuilder texture vs clean projected texture arbitration.
```

Step 5 should decide per UV region whether to keep raw FaceBuilder pixels, use
clean projected pixels, blend both, or mark the region for completion.

### 27.5 Step 5 Raw-Vs-Clean Arbitration

Date: 2026-06-30.

Step 5 was implemented after the user clarified two important constraints:

- do not use the old skin-filled cleanup texture;
- do not use Step 4 color-corrected texture for arbitration.

The active Step 5 script is:

```text
experiments/facebuilder_mask_aware_correction/run_step5_arbitration.py
```

Step 5 inputs:

```text
FaceBuilder raw texture
Step 4 projected raw texture
Step 4 coverage alpha
Step 4 confidence
Step 4 source count
```

Step 5 explicitly excludes:

```text
FaceBuilder cleanup texture
Step 4 projected color-corrected texture
Step 4 over-cleanup preview
```

Decision categories:

```text
red    = CLEAN_ONLY
blue   = RAW_ONLY
green  = BOTH_OK
yellow = COMPLETION_NEEDED
```

Two output texture variants are generated:

- `select`: BOTH_OK pixels choose the higher-trust source.
- `blend`: only BOTH_OK pixels blend raw and Step 4 projected raw.

COMPLETION_NEEDED pixels are black in the actual output textures. The yellow
color is used only in the decision-map diagnostic.

Private Step 5 output:

```text
<private_drive>/hair_app/output/facebuilder_mask_aware_step5/20260630_213625
```

Important tuning note:

The first documented Step 5 output at
`<private_drive>/hair_app/output/facebuilder_mask_aware_step5/20260630_200156`
used the scan/alignment-included Step 4 root
`<private_drive>/hair_app/output/facebuilder_mask_aware_step4/20260629_222438`.
That was corrected because scan/alignment frames should not drive final texture.
The active Step 5 output now uses the texture-camera-only Step 4 root
`<private_drive>/hair_app/output/facebuilder_mask_aware_step4/20260629_221621`.

The first Step 5 attempt trusted raw texture too much and let raw hair,
clothing, and background leakage survive. The raw trust logic was then made
more conservative: raw pixels are only accepted where Step 4 had at least some
projected clean-skin support, and obvious non-skin color casts are penalized.

Observed Step 5 category ratios at 1024 atlas:

| Person | CLEAN_ONLY | RAW_ONLY | BOTH_OK | COMPLETION_NEEDED | BOTH_OK near-tie share |
| --- | ---: | ---: | ---: | ---: | ---: |
| Juseop | 0.007 | 0.030 | 0.156 | 0.807 | 0.781 |
| Eunchae | 0.023 | 0.012 | 0.103 | 0.862 | 0.788 |

Interpretation:

- Step 5 is a diagnostic arbitration layer, not a final production texture.
- The high near-tie share means the blend variant is worth comparing visually
  against the select variant.
- The large completion-needed share is expected because the project no longer
  hides unknown regions with fake skin fill.
- Step 6 must now perform semantic completion and material-specific repair for
  scalp/hairline, skin holes, neck, ears, eyes, mouth, lips, nostrils, and brows.

### 27.6 Step 6 Planning Notes

Date: 2026-06-30.

The user reviewed Step 5 `select` and `blend` outputs and judged that the
`blend` variant looks more promising than `select`. The working Step 6 base is
therefore the Step 5 `blend` texture from:

```text
<private_drive>/hair_app/output/facebuilder_mask_aware_step5/20260630_213625
```

Important correction from visual review:

- The forehead artifact should not be assumed to be hair-mask leakage.
- The selected Step 3 mask version, `v2_farl_grounded_sam`, appears visually
  strong and does not obviously pass hair pixels into usable skin.
- The current forehead problem is more likely valid skin pixels with baked
  lighting/shadow/tone mismatch, made darker by texture blending and render
  lighting.
- Step 6 should therefore avoid aggressive forehead erasure. It should treat
  forehead repair as tone and lighting normalization unless source maps prove
  a true hair/occluder leak.

Step 6 will be run one element at a time, with review sheets after each element:

1. Establish baseline review sheets from Step 5 `blend`, with `select` kept
   only for comparison.
2. Fill hard black `COMPLETION_NEEDED` skin holes from nearby reliable observed
   skin, excluding eyes, mouth, brows, nostrils, scalp, and clothing.
3. Repair forehead tone by lifting dark valid skin toward nearby forehead and
   midface skin while preserving detail.
4. Repair mouth/lips as separate materials instead of diffusing face skin into
   the mouth.
5. Repair eyes, eyelids, and brows as separate materials so eye whites and brow
   darkness do not contaminate skin.
6. Remove neck/lower clothing leakage using semantic location, color outlier
   checks, and decision/source maps.
7. Fill ears and side-face gaps conservatively, using observed pixels first and
   fallback only for truly missing regions.
8. Build plausible scalp and hairline material, separate from forehead skin.
9. Apply only mild final color smoothing after the element-by-element repairs
   are visually accepted.

The key process rule is diagnostic isolation: do not batch many post-process
changes together. Each region-specific repair must produce before/after review
sheets so quality changes can be attributed to one logic change.

### 27.7 Step 6 v00/v01 Postprocess

Date: 2026-07-01.

Step 6 implementation started with the Step 5 `blend` texture fixed as the
baseline. The active script is:

```text
experiments/facebuilder_mask_aware_correction/run_step6_postprocess.py
```

Active private Step 6 output:

```text
<private_drive>/hair_app/output/facebuilder_mask_aware_step6/20260701_084010
```

Generated sub-steps:

```text
v00_baseline
v01_hard_skin_holes
```

v00 simply copies the active Step 5 `blend` texture and renders it for baseline
review. Step 5 `select` is saved only as a diagnostic comparison.

v01 targets only hard black `COMPLETION_NEEDED` skin holes. The first internal
attempt was too permissive: it filled thousands of texels but also marked
eye-region candidates in the changed overlay. That violated the rule that eyes,
mouth, brows, nostrils, scalp, and clothing must not be filled with skin. The
logic was therefore tightened before accepting the output.

Accepted v01 logic:

- find reliable observed skin from non-completion texels plus broad YCbCr/luma
  skin gates;
- close that reliable skin mask with a small radius;
- consider only nearby `COMPLETION_NEEDED` texels as skin-hole candidates;
- build a magenta feature-protection mask for dark completion regions near
  skin, covering eyes, mouth/lip gaps, brows, nostril-like fragments, scalp
  boundary, and lower non-skin islands;
- fill only the remaining tiny dot-like holes from nearest reliable skin;
- smooth only changed texels locally.

Accepted v01 metrics at 1024 atlas:

| Person | Filled texels | Feature-protected texels | Result |
| --- | ---: | ---: | --- |
| Juseop | 39 | 80,403 | Very conservative, visually tiny |
| Eunchae | 13 | 85,922 | Very conservative, visually tiny |

Interpretation:

- v01 is intentionally a safety pass, not a visible quality leap.
- It proves the Step 6 review/diagnostic scaffold works and that skin diffusion
  can be prevented from entering eyes/mouth/brows.
- The current large visible problems are forehead tone mismatch, mouth/eye
  materials, neck/clothing leakage, and scalp/hairline material. Those should be
  handled as separate Step 6 sub-steps rather than by widening v01.

Next Step 6 sub-step:

```text
v02_forehead_tone
```

v02 should treat the forehead artifact as a tone/lighting mismatch in valid
skin unless masks/source maps prove true occluder leakage.

### 27.8 Step 6 v02 Forehead Tone

Date: 2026-07-01.

Active private Step 6 output after v02:

```text
<private_drive>/hair_app/output/facebuilder_mask_aware_step6/20260701_111008
```

Implemented sub-step:

```text
v02_forehead_tone
```

Goal:

- start from the accepted Step 5 `blend` texture plus v01 hard-hole fill;
- repair only forehead tone/lighting mismatch;
- protect eyes, eyebrows, mouth, nostrils, scalp, hairline, clothing, and lower
  face from being treated as forehead skin;
- output UV review sheets, render review sheets, and `light`/`medium`/`strong`
  variants.

Important iteration:

- The first v02 ROI was too broad. It selected an atlas rectangle that rendered
  onto forehead plus upper face/ears.
- The ROI was narrowed from a broad atlas range to a central upper-forehead
  range.
- A connected-component filter was then added so only the component overlapping
  the central forehead is kept. Side UV islands are rejected instead of being
  tone-normalized.

Accepted v02 logic:

- build reliable skin from the v01 texture and Step 5 decision map;
- build a magenta guard from dark feature-like completion regions near skin;
- create a central forehead candidate window;
- remove guard regions from the forehead candidate;
- keep only the central connected forehead component;
- derive a target tone from reliable forehead pixels and stable midface pixels;
- produce three strengths:
  - `light`: small tone nudge;
  - `medium`: default diagnostic candidate;
  - `strong`: aggressive diagnostic candidate;
- save changed masks, weight maps, UV sheets, and 0/+-15/+-30/+-45 render
  sheets.

Accepted v02 metrics at 1024 atlas:

| Person | Forehead skin texels | Tone candidates | Components kept | Medium changed texels | Strong changed texels |
| --- | ---: | ---: | ---: | ---: | ---: |
| Juseop | 13,220 | 4,309 | 1 / 9 | 10,157 | 10,939 |
| Eunchae | 11,468 | 6,514 | 1 / 3 | 10,168 | 10,679 |

Visual read:

- The v02 mask is much safer than the first ROI attempt. It no longer tries to
  repair the whole upper face as forehead.
- The actual visible improvement is small. Juseop's forehead patch shape
  remains visible in `medium` and `strong`; Eunchae's major quality issues are
  still lower-face/neck/occlusion related.
- This means simple tone correction is not enough for the forehead patches.
  The next useful repair should replace or locally inpaint the contaminated
  yellow v02 candidate regions while preserving nearby reliable skin detail.

Next Step 6 sub-step:

```text
v03_forehead_patch_completion
```

Suggested v03 direction:

- use the accepted v02 central-forehead mask and tone-candidate mask;
- replace only the yellow candidate islands, not the whole forehead;
- prefer nearby reliable forehead pixels, symmetric forehead pixels, or
  source-aware clean projections before generated fallback;
- keep eyes, eyebrows, hairline, and scalp under the existing guard;
- compare against the v02 `medium` texture in review sheets before moving on to
  mouth/lips.
