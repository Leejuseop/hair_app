# Hair App 3D Master Plan

Last synchronized: 2026-06-23
Status: working architecture and experiment plan; not a frozen specification

## 1. Document Purpose

This document is the current technical source of truth for the intended 3D Hair App architecture. It records the product goal, the proposed runtime pipeline, candidate models, custom modules, data contracts, experiments, fine-tuning direction, risks, and decision gates.

Every choice in this document is a **working hypothesis**. `Pixel3DMM`, `VGGT`, `FreeUV`, `DiffLocks`, `Im2Haircut`, `PERM`, `KaoLRM`, and every other named component may be replaced when controlled tests show that another option is better. The project should preserve stable input/output contracts so that a model can be swapped without rebuilding the whole application.

The project should not commit months of training effort merely because a paper or README looks promising. The required order is:

1. reproduce official inference;
2. test the model on the same Hair App inputs;
3. measure geometry, identity, hairstyle, failure rate, runtime, and license fit;
4. choose the temporary winner;
5. fine-tune only after the baseline is understood;
6. revisit the choice whenever new evidence appears.

## 2. Current Product Goal

The target user experience is:

1. The user uploads several selfies and completes a guided head and hairline scan.
2. Hair App reconstructs an editable, hairless 3D head that resembles the user.
3. Hair App builds a realistic face texture from the user's actual photographed skin, lips, brows, and other visible facial appearance.
4. The user uploads one or more images of a desired hairstyle.
5. Hair App reconstructs or generates that hairstyle as independent 3D hair.
6. Hair App fits the hair to the user's head and hairline without penetrating the face, ears, or scalp.
7. The app returns a rotatable 3D result and, optionally, high-quality rendered still images.

Compactly:

```text
user photos and scan
  -> editable hairless head mesh
  -> multi-photo face UV texture
  -> textured personal 3D head

hairstyle reference image(s)
  -> independent 3D strand hair

personal head + strand hair
  -> retargeting and collision correction
  -> mobile-ready GLB and optional high-quality renders
```

## 3. What Is Already Implemented

The repository currently implements the scan and structured-profile foundation, not the final 3D pipeline.

Implemented:

- React and Vite mobile web frontend.
- Browser camera access with `getUserMedia`.
- MediaPipe Face Landmarker in the browser.
- Guided `front`, `left`, `right`, and `hairline` capture steps.
- Automatic frame-quality checks and capture of 20 accepted samples per step.
- FastAPI scan upload and file-based storage.
- `base_profile.json` version `0.1` with raw landmarks, selected frames, derived metrics, anchors, and preview data.

Not implemented:

- Manual upload of several existing selfies with one or two starred images.
- A dedicated pulled-back-hair head scan beyond the current hairline capture step.
- Pixel3DMM, VGGT, KaoLRM, or another 3D reconstruction backend.
- UV texture projection and completion.
- 3D hairstyle reconstruction.
- Hair-to-scalp retargeting and collision handling.
- GLB generation and interactive 3D viewer.
- Production storage, job queue, authentication, privacy controls, billing, or deployment.

## 4. Core Architectural Decision

The current preferred representation is:

- **Head:** editable triangle mesh with stable topology and UV coordinates.
- **Face appearance:** UV texture maps attached to that mesh.
- **Hair:** independent 3D strands during reconstruction and high-quality rendering.
- **Mobile hair:** optimized strands, mesh, or hair cards derived from the master strand representation.
- **Final interactive asset:** glTF/GLB containing the head mesh, textures, eyes as needed, and mobile-ready hair.

This representation is preferred over one monolithic Gaussian avatar because Hair App must replace hairstyles, fit roots to a specific hairline, detect collisions, and export an asset that ordinary mobile 3D viewers can rotate.

### Why FastAvatar Is Not the Current Core

`FastAvatar` produces a photorealistic Gaussian head representation from a single image. It can be useful as a quality reference or fast visual preview, but it is not the current core because:

- its output is Gaussian splats rather than the conventional UV-mapped mesh required by the planned fitting pipeline;
- appearance, face, and existing hair can be entangled;
- transferring its appearance back to the Pixel3DMM or FLAME mesh creates an extra conversion problem;
- the app does not need another full avatar generator merely to copy photographed skin color onto an already reconstructed mesh;
- one-image reconstruction does not naturally exploit the user's full multi-photo and scan bundle.

This is a representation mismatch, not a GPU limitation. H100 availability does not change it. FastAvatar remains an optional benchmark and may return to the active path if future experiments show a robust mesh/texture extraction or a product requirement changes.

## 5. Runtime Pipeline

### Stage 1: User Capture

#### Inputs

- Several existing selfies, preferably five or more.
- Front, left three-quarter, right three-quarter, left profile, and right profile views when possible.
- A guided capture with hair pulled back to expose the natural hairline and temples.
- Optional higher-angle and rear/side head views for better scalp constraints.
- One or two user-starred photos that best represent the person's identity and normal skin appearance.

#### Capture Guidance

- Use neutral expression for geometry frames.
- Avoid beauty filters, portrait-mode warping, and strong wide-angle distortion.
- Prefer even, diffuse lighting without colored lights.
- Require sharp focus and adequate resolution.
- Ask the user to remove glasses or large occlusions for at least some frames.
- Preserve EXIF and camera metadata when available, but do not depend on them.
- Keep all original photos; derived crops and summaries must not replace the raw inputs.

#### Meaning of the Star

The star is not an absolute override. It is a user-provided quality and identity prior.

- For frontal skin, lips, brows, and central facial appearance, a starred frontal image may receive a moderate boost.
- For a side region, a clean side image should beat a starred frontal image that cannot see that region.
- For geometry, diverse viewpoints remain essential; a starred frontal image must not erase side-view evidence.
- The exact boost will be tuned experimentally rather than fixed permanently.

### Stage 2: Input Quality, Segmentation, and Calibration

The preprocessing service should calculate:

- face detection and landmark confidence;
- pose, approximate intrinsics, and camera distortion confidence;
- sharpness, motion blur, exposure, white balance, and dynamic range;
- face, skin, hair, ears, eyes, lips, brows, glasses, hands, and background masks when possible;
- duplicate-frame and near-duplicate detection;
- expression consistency;
- occlusion and visible-region maps.

Frames with severe problems should be rejected or given low regional weights rather than silently averaged into the result.

MediaPipe remains useful for live guidance and inexpensive quality checks. It is not expected to be the final high-accuracy 3D reconstruction engine.

For the first Pixel3DMM reproduction, persistent crop preprocessing should stay close to the official distribution: detect a bbox independently for every discontinuous photo, make an official-compatible square crop, and do not normalize roll by default. The crop-time RetinaFace five points are not the tracker's final landmarks. Pixel3DMM runs PIPNet after the persistent crop to produce WFLW 98 landmarks and then optimizes camera/head rotation during FLAME fitting. MediaPipe may cross-check those results, but it should not silently replace PIPNet topology. See `docs/12_pixel3dmm_preprocessing_contract.md` for the audited order and coordinate contract.

### Stage 3: Hairless 3D Head Reconstruction

#### First Research Baseline

The current first baseline is `Pixel3DMM` with a FLAME-family head model.

Expected inputs:

- a folder or sequence of user images;
- face crops and masks;
- camera and landmark initialization;
- a shared-identity constraint across the user's images;
- optional normal, depth, and silhouette evidence;
- Hair App quality and star weights.

Expected outputs:

- FLAME or compatible identity and expression parameters;
- an editable triangle head/face mesh;
- camera parameters for every accepted image;
- projected landmarks and masks;
- confidence values and reconstruction diagnostics.

`Pixel3DMM` should be understood as a fitted parametric face/head reconstruction, not a literal CT-like scan. Facial geometry such as jaw, cheeks, nose, mouth, and eye sockets is estimated from visible evidence and the model prior. The scalp hidden under hair is not directly observed.

#### Scalp and Hairline Reality

The pulled-back-hair scan improves:

- the natural front hairline;
- temple recession and asymmetry;
- forehead height;
- the transition around the ears;
- any scalp surface that becomes visible.

It does not reveal the crown or rear skull still covered by hair. Those regions remain prior-based or depth-estimated. Hair App should store a confidence map so the UI and later hair fitting know which regions are measured, constrained, or inferred.

#### Auxiliary and Competing Geometry Models

- `VGGT`: candidate for multi-view camera, depth, point-map, and track initialization. It is an auxiliary geometry model, not a face-specific parametric head by itself.
- `KaoLRM`: 2026 candidate that predicts FLAME parameters and surface-aligned colored 2D Gaussians. It has training code and should be compared with Pixel3DMM, but its public inference path is not a direct multi-photo identity fusion engine and its effective license is non-commercial.
- `DF_MVR`: multi-view 3DMM and texture comparison candidate, but it uses an older BFM-oriented stack, lacks a clear repository license, and does not currently outrank the primary path.
- `MICA`, `DECA`, `EMOCA`, `NextFace`, and related older methods: useful baselines and fitting references, not the assumed final winner.
- `FastAvatar`, `FaceLift`, `Avat3r`, `FATE`, `MeGA`, and similar Gaussian head methods: visual-quality references or future alternatives if editable hair separation becomes reliable.

#### Teacher and Future Student

Pixel3DMM is currently treated as a high-quality research baseline and possible teacher, not a guaranteed production runtime.

If its optimization is accurate but too slow, Hair App may later train a feed-forward multi-image student that predicts the same mesh parameters from the full photo set. A KaoLRM-like transformer is one architectural reference, but any student must be evaluated and licensed independently. Distillation from non-commercial software or weights requires legal review and permission before commercial use.

### Stage 4: Multi-Photo Face UV Texture

This stage gives the hairless mesh the user's visible skin, lips, brows, facial marks, and other stable appearance.

#### Why Hair App Implements the Core UV Baker

The observed parts of the user's face do not need to be invented by a generative model. Once the mesh and per-image cameras are known, photographed pixels can be projected into a common UV atlas.

There is no current open-source package that cleanly provides all of the following as a production-ready Hair App component:

- multiple arbitrary user photos;
- per-region visibility and occlusion handling;
- user-starred quality weights;
- direct use of Pixel3DMM/FLAME cameras and topology;
- lighting normalization across phone photos;
- identity-preserving fusion that keeps actual observed pixels;
- seam correction, confidence maps, and product-safe output contracts;
- clear training and commercial licensing for the complete pipeline.

The project is not implementing a rasterizer or all 3D mathematics from scratch. It should assemble proven components such as PyTorch3D, nvdiffrast, OpenCV, segmentation models, and the mesh's existing UV coordinates into a Hair App-specific pipeline.

#### UV Baking Steps

1. Normalize accepted photos into a common color space.
2. Estimate or refine the camera for every image.
3. Rasterize the fitted mesh into every source view.
4. Determine which mesh triangles and UV texels are visible.
5. Reject pixels hidden by hair, glasses, hands, extreme shadows, or back-facing geometry.
6. Project valid source pixels to the shared UV atlas.
7. Accumulate multiple observations per UV texel.
8. Blend observations using regional confidence weights.
9. Correct exposure, white balance, shading, and seams.
10. Produce an observed-coverage mask and uncertainty map.
11. Complete only the remaining holes using a learned or procedural completion method.
12. Render the textured mesh back into all source cameras and calculate reconstruction errors.

Conceptual weighting:

```text
texel weight =
  visibility
  x front-facing surface score
  x sharpness
  x exposure and white-balance confidence
  x segmentation confidence
  x expression consistency
  x regional camera suitability
  x optional star bonus
```

The exact function is intentionally not frozen. It should be learned or tuned from validation results.

#### Lighting and Material Outputs

The first working version may output only a `baseColor` texture. A more realistic version should separate:

- base color or diffuse albedo;
- normal or high-frequency detail;
- roughness;
- specular intensity;
- optional subsurface-scattering parameters.

Phone photos mix skin color, shadows, highlights, makeup, and camera processing. De-lighting is therefore a real quality problem, not merely a color average. The pipeline should preserve an unmodified observed-texture layer and a normalized render-ready layer so corrections are reversible.

#### Hole Completion Candidates

- `FreeUV`: current quality-first research baseline for completing a facial UV map. Use only for unobserved or rejected areas where possible.
- `FFHQ-UV`: useful dataset and pipeline reference for normalized UV textures, subject to upstream data-license review.
- `UV-IDM`: inference reference, currently weak as a fine-tuning base because complete training and licensing are unclear.
- `NextFace`: older optimization and material reference.
- A Hair App-owned UV completion model: likely long-term path. It can be trained with synthetic missing-region masks, photometric rendering losses, seam losses, identity losses, and uncertainty-aware supervision after a legally usable dataset is secured.

### Stage 5: Textured Personal Head

The geometry and UV stages should produce a versioned personal asset independent of any hairstyle.

Minimum artifact contract:

```text
personal_head/
  head_mesh.glb or head_mesh.obj
  flame_params.npz
  cameras.json
  hairline.json
  geometry_confidence.exr or .npy
  base_color.png
  uv_coverage.png
  uv_confidence.exr or .npy
  material.json
  reconstruction_report.json
```

This separation is important: hairstyle experiments should not require reconstructing the user's identity every time.

### Stage 6: Hairstyle Reference Capture

The user may submit one hairstyle image, but the app should explain the ambiguity:

- one frontal image cannot reveal the back length, layers, or crown shape;
- occluded roots and overlapping curls are uncertain;
- lighting and pose can make volume appear different;
- a style may depend on hair type, density, product, and salon technique.

Preferred input:

- front hairstyle view;
- left or right three-quarter view;
- rear view when available;
- optional written constraints such as length, bangs, part direction, curl, and volume.

If only one image is supplied, the system should expose that hidden regions are model-generated hypotheses, not recovered facts. FLUX.2 or another image model may generate auxiliary view hypotheses for experimentation, but those generated views must not be treated as guaranteed ground truth.

### Stage 7: 3D Hairstyle Reconstruction

#### Primary Research Candidate: DiffLocks

`DiffLocks` is the first candidate because it is designed to generate strand-based 3D hair from an RGB image and provides training code and a substantial synthetic-hair data pipeline.

Expected output:

- strand roots;
- ordered 3D points or curves per strand;
- strand direction and grouping information;
- scalp-space coordinates or enough metadata to align them;
- Alembic, Blender curves, or a convertible strand representation.

#### Competing Candidates

- `Im2Haircut`: strong single-image strand reconstruction baseline; likely heavier per-subject optimization and non-commercial constraints.
- `PERM`: MIT-licensed parametric strand-hair prior and training foundation. It is promising for a long-term Hair App-owned model, but its public single-image reconstruction path is not as complete as DiffLocks.
- `UniHair`: useful for complicated or braided styles, but Gaussian hair is less convenient than strands for root retargeting and mobile conversion.
- `GaussianHaircut` and `NeuralHaircut`: multi-view or video references if the product later accepts hairstyle videos.
- `HairPort`: important 3D-aware 2D hairstyle-transfer reference, not a rotatable 3D hair-asset generator. Its use of FLUX-family refinement confirms that FLUX knowledge remains useful as a secondary path.

The first selected model is not guaranteed to remain the winner. DiffLocks, Im2Haircut, and UniHair should be tested on the same hairstyle set before fine-tuning.

### Stage 8: Geometric Hair-to-Head Integration

This is primarily a geometry and optimization system, not necessarily another generative AI model.

Required operations:

1. Convert the source hairstyle and user head into a common coordinate system.
2. Identify the source scalp, part, front hairline, temples, crown, and ear anchors.
3. Map hair roots from the source scalp to the user's scalp using canonical scalp UVs or surface correspondences.
4. Scale and deform the hairstyle while preserving local strand direction, curl, and volume.
5. Align the front roots to the user's actual hairline where the style permits.
6. Detect intersections between strands and the head, forehead, ears, neck, and shoulders.
7. Resolve collisions with a signed-distance field, local optimization, or physics-assisted relaxation.
8. Preserve deliberate occlusions such as bangs while removing impossible penetration.
9. Run silhouette and style-similarity validation from several rendered cameras.
10. Save both the full-quality master hair and a mobile representation.

Potential outputs:

```text
fitted_hair/
  strands.abc
  strands.json or curves.npz
  hair_cards.glb
  hair_materials/
  fitting_report.json
```

### Stage 9: Rendering and Delivery

Server or research rendering may use Blender, PyTorch3D, nvdiffrast, or another differentiable/offline renderer.

Mobile delivery should normally use:

- glTF/GLB;
- compressed textures;
- mesh LODs;
- hair cards or reduced strands;
- Three.js or a comparable WebGL/WebGPU viewer;
- touch rotation, zoom, and reset controls;
- fixed front, side, rear, and three-quarter camera presets.

Full strands may remain server-side for high-quality turntables and still renders. The interactive viewer does not need to carry the full training-quality representation.

### Stage 10: Optional 2D Refinement

FLUX.2, Qwen Image Edit, HiDream, HairPort-like pipelines, or another high-quality image editor may be used for:

- presentation-grade still renders;
- cleanup of renderer artifacts;
- auxiliary style views;
- comparison against the true 3D pipeline;
- a faster 2D fallback while 3D quality is still under development.

Diffusion output should not be the source of truth for interactive geometry. Independently edited camera views can be inconsistent with each other.

## 6. Model Decision Table

### Head and Face Geometry

| Candidate | Primary input | Primary output | Training status | Current role |
| --- | --- | --- | --- | --- |
| Pixel3DMM | one or multiple face images | fitted FLAME-family geometry, cameras, priors | code available; productized training recipe requires audit | first research geometry baseline and possible teacher |
| VGGT | multiple images | cameras, depth, point maps, tracks | training and fine-tuning examples available | optional multi-view initializer and consistency signal |
| KaoLRM | single face image in public inference | FLAME parameters, mesh, colored surface Gaussians | training code released | 2026 comparison candidate and student-architecture reference |
| FastAvatar | single image | Gaussian head avatar | training code available | visual benchmark, not current mesh/UV core |
| DF_MVR | multiple views | BFM-oriented 3D face and texture | training code; custom weights and license concerns | secondary comparison only |
| FaceLift / Avat3r / MVCHead | one or several images depending on model | high-fidelity Gaussian head | availability and licenses vary | future visual alternatives, not current editable core |

### Face Appearance

| Candidate | Role | Strength | Limitation | Current decision |
| --- | --- | --- | --- | --- |
| Hair App UV baker | observed multi-photo texture | preserves real user pixels and custom star/quality weights | product-quality de-lighting and seams require work | core custom module |
| FreeUV | UV hole completion | strong single-image UV completion | training/license clarity insufficient for product dependency | research completion baseline |
| FFHQ-UV | dataset and normalized-texture reference | large UV collection and pipeline | upstream data and commercial rights require review | research data reference |
| UV-IDM | generative UV reference | fast diffusion UV generation | incomplete training/license story | not primary |
| NextFace | fitting/material reference | multi-image material estimation | older, slow, restrictive use | reference only |
| FastAvatar | complete neural appearance | photorealistic novel views | wrong representation for core mesh/UV workflow | optional benchmark |

### Hair

| Candidate | Output | Fine-tuning value | Main limitation | Current role |
| --- | --- | --- | --- | --- |
| DiffLocks | 3D strands | full training code and synthetic pipeline | non-commercial research license unless separately licensed | first research baseline |
| Im2Haircut | 3D strands | strong reconstruction reference | optimization complexity and non-commercial dependencies | mandatory comparison |
| PERM | parametric 3D strands | MIT code and trainable hair prior | incomplete public image-to-hair system | long-term own-model foundation candidate |
| UniHair | Gaussian hair | complex hairstyle coverage | less convenient editing/retargeting; data access limits | special-style comparison |
| HairPort | final 2D hairstyle transfer | valuable 3D-aware and FLUX-based design ideas | not an editable 3D asset; restrictive license | 2D benchmark/reference |

## 7. Fine-Tuning Strategy

GPU is not the current bottleneck. The user has access to Colab H100 and can spend more on compute. Therefore the project should optimize first for output quality, observability, and clean representations rather than premature model compression.

### Do Not Fine-Tune Before a Baseline Works

For every candidate:

1. reproduce official examples;
2. run private Hair App-like cases;
3. record failure cases;
4. establish fixed validation inputs and seeds where applicable;
5. confirm that the output representation can enter the next stage;
6. audit code, weight, dataset, and dependency licenses;
7. only then start fine-tuning.

### Proposed Fine-Tuning Order

1. **No-training geometry and UV prototype.** Prove that the complete data path works.
2. **Hair model adaptation.** The hairstyle domain and source-image ambiguity are likely the largest model gap. Compare DiffLocks and Im2Haircut first.
3. **UV completion and de-lighting.** Train only after direct UV baking establishes real missing-area and seam failure patterns.
4. **Fast multi-image head student.** Train only after Pixel3DMM/KaoLRM comparisons define a trusted target and latency becomes a real problem.
5. **Optional 2D refinement LoRA.** Keep separate from the geometric source of truth.

### Hair Fine-Tuning Data

Useful samples should contain as much of the following as legally available:

- one or more hairstyle reference renders;
- ground-truth strands or curves;
- source scalp and canonical scalp correspondence;
- hairstyle attributes such as length, part, curl, density, bangs, and volume;
- multiple camera views and masks;
- diversity across straight, wavy, curly, coily, braided, short, long, sparse, and high-volume hair;
- collision-free fits to multiple head shapes.

Synthetic rendering can expand pose, lighting, background, and camera diversity, but the validation set must include real phone images.

### UV Model Data

The custom UV completion/de-lighting model may use:

- legally usable complete UV textures;
- synthetic occlusion masks modeled after hair, glasses, shadow, and profile visibility;
- paired shaded and de-lit renders;
- multi-photo observations with known cameras;
- identity-preserving render-back supervision;
- UV seam and symmetry-aware losses without forcing real facial asymmetry to disappear.

## 8. Evaluation Protocol

### Geometry Metrics

- landmark reprojection error in every source view;
- silhouette overlap;
- multi-view depth and normal consistency;
- identity similarity between rendered views and accepted user images;
- scan-to-mesh distance when ground-truth scans become available;
- hairline curve error;
- user and expert preference;
- failure rate, runtime, and manual intervention rate.

### Texture Metrics

- render-back photometric error in visible regions;
- identity embedding similarity;
- color consistency across seams and cameras;
- preservation of stable marks and lip/brow appearance;
- percentage of observed versus generated texels;
- lighting leakage and highlight artifacts;
- expert review across varied skin tones and lighting.

### Hair Metrics

- hairstyle-reference similarity from several rendered views;
- silhouette similarity;
- strand orientation agreement;
- length, part, curl, density, and volume attributes;
- scalp coverage;
- penetration and floating-root counts;
- rear-view plausibility for single-image inputs;
- manual correction time.

### Product Metrics

- total job success rate;
- time from upload to first preview;
- percentage of users asked to recapture;
- interactive GLB size and frame rate;
- user confidence that the style resembles both their identity and the reference;
- privacy deletion success and storage cost.

### Baseline Test Set

Before large-scale training, create a small controlled set that deliberately contains:

- frontal and side photos with even light;
- difficult shadows and mixed white balance;
- glasses and partial occlusion;
- different skin tones;
- short, long, straight, curly, coily, and braided styles;
- visible and hidden hairlines;
- one-reference and multi-reference hairstyle cases.

The same set must be reused across model candidates. New difficult cases should be added, not substituted for older cases, so regressions remain visible.

## 9. Development Milestones and Decision Gates

### Milestone 0: Data and Contracts

- Add existing-selfie upload and star selection to the product design.
- Define immutable raw-input storage and derived-artifact versioning.
- Define the head mesh, cameras, hairline, UV, strand, and GLB contracts.
- Add explicit user consent and deletion requirements before collecting real training data.

Gate: one scan bundle can be replayed reproducibly through preprocessing.

### Milestone 1: Hairless Geometry Bake-Off

- Run Pixel3DMM on representative multi-photo sets.
- Run KaoLRM on the best comparable inputs.
- Optionally use VGGT camera/depth initialization.
- Render all outputs from the same cameras and score them.

Gate: choose the temporary geometry baseline from measured results. If none is adequate, broaden the search or change capture requirements before proceeding.

### Milestone 2: Direct UV Prototype

- Implement visible-triangle and UV projection.
- Blend several photos using confidence weights.
- Save observed coverage and confidence.
- Render the texture back to the source views.

Gate: central face identity and color must be preserved without a generative model.

### Milestone 3: UV Completion and Materials

- Add seam correction and lighting normalization.
- Compare FreeUV with simpler inpainting.
- Produce base color first; add PBR details only when useful.

Gate: completed areas must not noticeably change the user's identity.

### Milestone 4: Hair Reconstruction Bake-Off

- Reproduce DiffLocks, Im2Haircut, and at least one alternative.
- Use identical hairstyle references.
- Store strands and render consistent comparison turntables.

Gate: choose a temporary strand representation and baseline. Do not fine-tune a model that cannot reliably export usable hair.

### Milestone 5: Retargeting and Collision

- Fit baseline hair to several reconstructed heads.
- Implement canonical scalp mapping and hairline anchors.
- Add collision statistics and visual debugging.

Gate: hair roots remain attached and obvious penetrations are removed across standard views.

### Milestone 6: End-to-End Offline Demo

- Run the full pipeline from private user input to head, texture, fitted hair, and rendered turntable.
- Keep the backend offline or notebook-based if that accelerates learning.

Gate: users recognize themselves and the requested hairstyle often enough to justify product integration.

### Milestone 7: App and Queue Integration

- Add persistent style-reference upload.
- Add asynchronous reconstruction jobs and progress states.
- Add 3D result storage and Three.js viewer.
- Add retries, failure messages, and deletion controls.

Gate: stable end-to-end jobs with acceptable cost, latency, and mobile performance.

### Milestone 8: Fine-Tuning and Scale

- Fine-tune the stage with the clearest measured gap.
- Train a fast student only if latency or cost is proven to be a bottleneck.
- Quantize, cache, batch, and optimize only after quality baselines exist.

Gate: every training change must beat the fixed baseline set without unacceptable regressions.

## 10. Planned Service Boundaries

The exact APIs are not implemented and may change. A model-independent boundary may look like:

```text
capture service
  -> scan bundle and quality report

head reconstruction worker
  -> head mesh, cameras, parameters, confidence

texture worker
  -> UV maps, material maps, coverage, confidence

hair reconstruction worker
  -> strands and hairstyle metadata

retargeting worker
  -> fitted master hair and collision report

asset builder
  -> mobile GLB, thumbnails, turntable, manifest
```

Possible future routes, clearly distinct from the currently implemented API:

- `POST /api/uploads/selfies`
- `POST /api/uploads/style-references`
- `POST /api/reconstruction/head`
- `GET /api/reconstruction/head/{job_id}`
- `POST /api/reconstruction/hair`
- `POST /api/fits`
- `GET /api/results/{result_id}`
- `DELETE /api/users/{user_id}/biometric-assets`

Do not expose these as real routes until implemented.

## 11. Versioned Artifact Manifest

Every generated result should record:

- source scan ID and accepted image IDs;
- code commit and pipeline version;
- model names, weight versions, and licenses;
- prompts and random seeds where generative models are used;
- all preprocessing parameters;
- head topology and UV version;
- user star selections and final regional weights;
- confidence maps;
- runtime, GPU, and failure warnings;
- whether each region is observed, reconstructed, or generated;
- parent artifact IDs so a result can be reproduced.

This metadata prevents silent model changes from making old and new results incomparable.

## 12. H100 and Colab Strategy

The user has Colab H100 access and can purchase more compute. The project should therefore:

- use high-quality bf16/fp32-sensitive baselines before aggressive quantization;
- cache checkpoints and private outputs in persistent storage because Colab runtimes are ephemeral;
- save environment lock files and exact notebook cells for every reproduced model;
- write checkpoints frequently during fine-tuning;
- benchmark runtime but not reject a model solely because it is initially slow;
- avoid assuming that one H100 makes full foundation-model training cheap or that data quality no longer matters.

Compute availability reduces iteration constraints. It does not solve missing viewpoints, ambiguous hidden hair, incorrect representations, data rights, or model licensing.

## 13. Licensing and Commercialization

The current research stack contains important restrictions.

- Pixel3DMM: CC BY-NC 4.0 in the public repository.
- FLAME: research use by default; commercial use requires appropriate licensing.
- KaoLRM: source portions are permissive, but weights and several dependencies make the effective public stack non-commercial.
- DiffLocks: non-commercial research use in the public release; commercial licensing is offered separately.
- Im2Haircut and several dependencies: non-commercial restrictions.
- FreeUV: do not assume commercial permission without an explicit license audit.
- FFHQ-UV: code license does not automatically grant unrestricted commercial rights to all derived data and upstream assets.
- PERM: code is MIT, but datasets and third-party assets still require separate review.
- VGGT: use only a checkpoint and dependency set whose license matches the intended product.

Research path and commercial path must be tracked separately. Before commercialization, obtain licenses, replace restricted components, or train clean alternatives on legally usable data. Do not assume that rewriting a wrapper or distilling outputs automatically removes upstream restrictions.

## 14. Privacy and Safety Requirements

User face photos, landmarks, embeddings, 3D head geometry, and textures are biometric-sensitive data.

The production design should include:

- explicit informed consent;
- purpose limitation;
- encryption in transit and at rest;
- strict access controls and audit logs;
- short default retention;
- user-visible deletion;
- separation of product inference data from training data;
- separate opt-in for training use;
- no public repository storage of private inputs or outputs;
- redaction of private paths and IDs from experiment logs;
- regional legal review before launch.

## 15. Open Questions

- How many user photos are the minimum for acceptable geometry and texture?
- Is a continuous guided video better than several still photos for Pixel3DMM and VGGT?
- How much additional scalp coverage should the capture flow require?
- Should the star be user-visible only, or combined with automatic quality ranking?
- Can Pixel3DMM's topology represent the required full scalp and ears well enough?
- Is a custom scalp residual mesh needed beyond FLAME?
- Does direct UV baking preserve makeup, freckles, and asymmetric facial details under varied lighting?
- Which UV completion approach changes identity the least?
- Does DiffLocks export hair that can be reliably retargeted to arbitrary reconstructed heads?
- How should one-image hairstyle uncertainty be communicated?
- When should full strands be converted to hair cards?
- Is the first product better as server-rendered turntables before interactive GLB?
- Which restricted research components need licenses versus clean replacements?

These questions are not blockers to experimentation, but their answers may change the architecture.

## 16. Current Working Recommendation

The first end-to-end research stack to test is:

```text
MediaPipe capture guidance
  + Pixel3DMM multi-photo head reconstruction
  + optional VGGT camera/depth initialization
  + Hair App multi-photo UV baker
  + FreeUV only for missing UV regions
  + DiffLocks strand-hair reconstruction
  + Hair App scalp retargeting and collision correction
  + Blender/server validation renders
  + GLB/Three.js mobile delivery
```

Required comparisons before this stack becomes a longer-term commitment:

- Pixel3DMM versus KaoLRM and any newly available multi-image head model;
- direct UV baking with simple completion versus FreeUV-assisted completion;
- DiffLocks versus Im2Haircut and UniHair;
- full 3D output versus a FLUX.2/HairPort-like 2D quality reference.

This recommendation is intentionally revisable. The stable part is the product contract: an editable personal head, a faithful face texture, independent 3D hair, a geometric fit, and a viewable result. The individual models are replaceable tools used to reach that contract.

## 17. Primary Research Links

- Pixel3DMM: <https://github.com/SimonGiebenhain/pixel3dmm>
- FastAvatar: <https://github.com/hliang2/FastAvatar>
- VGGT: <https://github.com/facebookresearch/vggt>
- KaoLRM: <https://github.com/CyberAgentAILab/KaoLRM>
- FreeUV: <https://github.com/YangXingchao/FreeUV>
- FFHQ-UV: <https://github.com/csbhr/FFHQ-UV>
- UV-IDM: <https://github.com/Luh1124/UV-IDM>
- NextFace: <https://github.com/abdallahdib/NextFace>
- DiffLocks: <https://github.com/Meshcapade/difflocks>
- Im2Haircut: <https://github.com/Vanessik/Im2Haircut>
- PERM: <https://github.com/c-he/perm>
- UniHair: <https://github.com/PAULYZHENG/UniHair>
- HairPort: <https://github.com/deepmancer/HairPort>
