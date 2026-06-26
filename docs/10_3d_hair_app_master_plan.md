# Hair App 3D Master Plan

Last synchronized: 2026-06-27
Status: working architecture and experiment plan; not a frozen specification

> 2026-06-27 update: the long-term product contracts in this document are still
> useful, but the current near-term head-generation engine candidate has moved
> from Pixel3DMM/FLAME + custom Texture Baker to FaceBuilder/KeenTools
> automation through headless Blender. See section 21 for the current override.

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

### Product Problem and User Value

사용자는 마음에 드는 헤어스타일 사진을 찾아도 그 스타일이 자신의 실제 얼굴, 두상, 헤어라인, 이마, 귀, 옆모습과 어울릴지 판단하기 어렵다. 한 장짜리 2D 합성은 빠른 미리보기에는 유용하지만 얼굴 깊이와 좌우 비대칭, 실제 hairline, 측면·후면의 일관성, 머리카락과 얼굴·귀·두피의 충돌을 안정적으로 표현하지 못한다.

Hair App이 해결하려는 핵심 문제는 다음과 같다.

> 여러 사용자 사진과 가이드 스캔으로 재사용 가능한 개인 3D 머리를 만들고, 실제 사진 기반 얼굴 표면과 독립된 3D 헤어스타일을 결합해 여러 각도에서 확인할 수 있게 한다.

사용자에게 필요한 가치는 다음과 같다.

- 미용실 방문 전에 원하는 스타일을 정면뿐 아니라 측면과 후면에서도 확인;
- 실제 얼굴형, 이마, hairline과 temple 모양을 반영;
- 헤어스타일을 바꿀 때마다 얼굴을 다시 만들지 않는 reusable personal head;
- 사진에서 관측된 부분과 모델이 추정한 부분을 구분하는 정직한 결과;
- 휴대전화에서 회전·확대할 수 있는 결과와 필요한 경우 고품질 still render.

### Working Product Hypotheses

1. **Multi-photo geometry:** 정면·좌우·profile·hairline-visible 입력을 함께 사용하면 한 장보다 얼굴 깊이와 side contour가 좋아진다.
2. **Observed UV texture:** 보이는 얼굴을 AI가 다시 그리는 것보다 실제 사진 픽셀을 공통 UV에 투영하는 편이 identity를 잘 보존한다.
3. **Independent hair:** head mesh, face UV, strand hair를 분리해야 스타일 교체와 collision correction이 가능하다.
4. **Pulled-back-hair capture:** 머리를 뒤로 넘긴 사진은 hairline·temple·귀 주변을 개선하지만 계속 가려진 crown/rear scalp는 여전히 prior 추정이다.
5. **Star plus regional quality:** 사용자가 고른 대표 사진은 appearance에 bonus를 주되, 측면 영역에서는 실제 측면 사진의 관측을 우선한다.
6. **3D before 2D polish:** 먼저 일관된 3D geometry를 만들고 필요할 때만 2D model을 presentation refinement에 사용한다.

이 가설은 고정된 진리가 아니다. 동일 입력 비교에서 실패하면 capture, representation, model, fine-tuning 순서를 바꾼다.

### Research Success and First-Prototype Non-Goals

초기 성공은 단순히 notebook이 실행되는 것으로 판정하지 않는다. neutral render에서 사용자가 자신을 알아볼 수 있어야 하고, observed texture가 실제 얼굴색과 특징을 유지해야 하며, hair silhouette·part·length·volume이 여러 view에서 일관되어야 한다. Hair root가 scalp와 hairline에 붙고 명백한 penetration이 없어야 하며, observed/generated 영역과 confidence를 manifest로 구분할 수 있어야 한다.

첫 3D prototype의 목표가 아닌 것:

- 의료용 두개골·두피 측정 정확도;
- 실시간 물리 기반 strand simulation;
- 모든 braid와 모든 모발 유형의 완전한 지원;
- 처음부터 foundation model 전체 학습;
- 연구용 비상업 모델을 그대로 commercial production에 배포하는 것.

## 3. What Is Already Implemented

The repository currently implements the scan and structured-profile foundation. In addition, the offline research notebook now reproduces one complete Pixel3DMM geometry baseline. The 3D baseline is **not** connected to the FastAPI product flow and is not yet a production result pipeline.

Implemented:

- React and Vite mobile web frontend.
- Browser camera access with `getUserMedia`.
- MediaPipe Face Landmarker in the browser.
- Guided `front`, `left_45`, `right_45`, `left_profile`, `right_profile`, and `hairline` geometry capture steps.
- Automatic frame-quality checks and capture of 8~12 accepted samples per step.
- FastAPI scan upload and file-based storage.
- Backend-created `selected_3dmm/` reconstruction input bundle and `selected_3dmm_manifest.json`.
- Automatic desktop copy of the selected 3DMM input frames under `C:\Users\User\Desktop\내사진\{scan_id}\selected_3dmm\`.
- `base_profile.json` version `0.2` with raw landmarks, selected frames, derived metrics, anchors, preview data, and reconstruction-bundle summary.
- A reproducible A100 Pixel3DMM V4 research notebook for eight independent photos.
- V4 preprocessing with FaceBoxes per-photo no-roll crop, PIPNet WFLW-98, and FaRL, confirmed 8/8.
- Pixel3DMM normal and UV inference, multi-photo FLAME tracking, and `canonical.ply` generation.
- A measured no-MICA geometry baseline: 5,023 vertices, 9,976 faces, and approximately 17.3% lower quick landmark error than mean FLAME under fixed fitted cameras/poses/expressions.
- Same-input MICA prior and MICA init-only A/B runs were completed; neither passed the fixed-context adoption gate, so no-MICA remains the active Pixel3DMM V4 baseline.
- A fully refitted mean-shape control reached `5.7423 px` average landmark error, matching or slightly beating the no-MICA fitted-shape value `5.8803 px`; therefore the current identity-shape personalization claim is weak under the landmark metric.
- A later private 19-view run from selected selfies plus app scan frames generated the no-MICA mesh and the fitted mean-shape control, but cross-context landmarks still did not validate no-MICA identity shape over the refitted mean-shape control.
- Raw FLAME, fitted mean-shape control, and personal no-MICA are frozen as three private mesh candidates for texture review.
- Texture Baker v3 now exists as the latest iterative research baker. It is cleaner than v1/v2 and writes no-lighting plus lighting-normalized private outputs, but it is still diagnostic and not product-usable.
- The next product-facing research step is dedicated eye/mouth material work, better feature preservation, and safer fitted-camera texture refinement before any base-mesh decision.

Not implemented:

- Manual upload of several existing selfies with one or two starred images. Until this exists, selected selfies are kept in a private folder outside the repository and joined with app-scan frames offline.
- A dedicated pulled-back-hair head scan beyond the current hairline capture step.
- Any 3D reconstruction backend connected to the product API or storage model.
- production-quality UV texture projection, confidence-aware completion, and render-to-selfie refinement.
- 3D hairstyle reconstruction.
- Hair-to-scalp retargeting and collision handling.
- GLB generation and interactive 3D viewer.
- Production storage, job queue, authentication, privacy controls, billing, or deployment.

The exact V4 configuration, errors, validation metrics, limitations, MICA A/B result, mean-shape control, private 19-view result summary, and texture-baker records are now archived in `docs/history.md`.

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

For the first Pixel3DMM reproduction, persistent crop preprocessing stays close to the official distribution: detect a bbox independently for every discontinuous photo, make an official-compatible square crop, and do not normalize roll by default. Crop-time sparse points are not the tracker's final landmarks. Pixel3DMM runs PIPNet after the persistent crop to produce WFLW 98 landmarks and then optimizes camera/head rotation during FLAME fitting. MediaPipe may cross-check those results, but it should not silently replace PIPNet topology. The V4 run confirmed this contract 8/8; the detailed record is now archived in `docs/history.md`.

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

- **Current:** the first Pixel3DMM V4 no-MICA run completed end to end on one eight-photo set, MICA prior/init-only did not beat it under the fixed-context decision gate, and fully refitted mean-shape control matched or slightly beat it on landmarks.
- **Measured:** fitted identity beat mean FLAME on all 8/8 views in a same-camera quick landmark diagnostic, improving average error from `7.1109 px` to `5.8803 px`, but the stronger refitted mean-shape control reached `5.7423 px`.
- **Private 19-view follow-up:** no-MICA and the mean-shape control both completed, and cross-context landmarks still did not validate no-MICA identity shape over the refitted mean-shape control.
- Freeze raw FLAME, fitted mean-shape control, and personal no-MICA as private mesh candidates and texture all three before choosing a temporary development head.
- Then decide whether to improve shape constraints or test 256 versus 512 tracking resolution.
- Expand Pixel3DMM evaluation to representative multi-photo sets.
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

## 18. Current Mobile Web, Scan, API, and Storage Contract

This section absorbs the former standalone mobile MVP and scan documents so the current product boundary and future 3D plan stay together.

### 18.1 Current user flow

1. The user opens the React/Vite mobile web app.
2. The browser requests camera permission and starts MediaPipe Face Landmarker.
3. The app guides `front`, `left_45`, `right_45`, `left_profile`, `right_profile`, and `hairline` capture steps.
4. Each step collects 8~12 accepted samples after quality checks.
5. The completed bundle is uploaded with `POST /api/scan`.
6. FastAPI stores the scan under `backend/storage/scans/{scan_id}/`.
7. The backend creates `selected_3dmm/` and `selected_3dmm_manifest.json` by choosing the best stepwise geometry frames.
8. The backend also copies those selected frames to `C:\Users\User\Desktop\내사진\{scan_id}\selected_3dmm\` for local manual handoff.
9. The backend creates `base_profile.json` version `0.2`.
10. The frontend shows representative images, landmark overlays, a hairline guide, selected 3DMM frame count, and summary metrics.

Current capture checks include face presence, distance/size, center alignment, brightness, sharpness, yaw, roll, and short-term stability. The exact thresholds are implementation details and must be checked in code when this document and code disagree.

The current hairline step improves frontal hairline and temple evidence. The left/right 45-degree and profile steps are meant to give Pixel3DMM/VGGT-style geometry models stronger profile evidence than arbitrary selfies. This is still not a complete crown/rear scalp scan. A future pulled-back-hair flow should explicitly request:

- frontal hairline with hair fully pulled back;
- left and right temple/profile views;
- both ears where possible;
- crown and rear coverage when the chosen geometry model can use it;
- recapture when a required region remains unobserved.

### 18.2 Current sample and bundle meaning

Each accepted sample preserves the camera frame plus raw face-landmark and quality metadata needed to reproduce later decisions. Raw data should be retained independently from derived previews so a future model can rerun from original evidence.

The six guided steps, automatic samples, and backend 3DMM selected-frame bundle are implemented. Existing-selfie multi-upload, star selection, region-aware photo ranking across uploaded selfies, and persistent style-reference upload remain planned.

For the completed private-data geometry experiment, the operational handoff was:

1. the user selects selfies manually and stores them outside the repository;
2. the user completes the app scan;
3. the backend creates `backend/storage/scans/{scan_id}/selected_3dmm/`;
4. the backend also exports the selected app-scan frames to `C:\Users\User\Desktop\내사진\{scan_id}\selected_3dmm\`;
5. an offline preparation step combines private selfies and selected app-scan frames into one Pixel3DMM input folder;
6. no-MICA Pixel3DMM and the mean-shape control were rerun on that combined set.

The future star behavior should be:

- user star is an appearance-quality bonus, not an absolute override;
- at most one or two photos may receive a strong global bonus;
- a clear side photo still wins in its visible side region even if a frontal photo is starred;
- automatic blur, occlusion, pose, lighting, and regional-coverage scores combine with the star;
- low-quality or contradictory photos may be excluded with an explanation.

### 18.3 Implemented API

- `POST /api/scan`
- `GET /api/scan/{scan_id}`
- `GET /api/base-profile/{scan_id}`

Current placeholders, not completed generation routes:

- `POST /api/style-reference`
- `POST /api/generate`
- `GET /api/result/{result_id}`

Future GPU work must be asynchronous. Long head, UV, or hair inference must not run directly inside the web request process. A future job boundary needs explicit queued/running/succeeded/failed states, retry behavior, artifact IDs, logs, and user-visible deletion.

### 18.4 Current storage

File-based local storage remains the current implementation until a database/object-store decision is made. `backend/storage/` is runtime data and never belongs in Git.

Conceptually:

```text
backend/storage/scans/{scan_id}/
  request and scan metadata
  accepted frame images
  raw landmark samples
  selected_3dmm/
    curated geometry input frames
    manifest.json
  selected_3dmm_manifest.json
  selected representative images
  base_profile.json
  preview assets
```

The backend also writes a convenience copy of the selected 3DMM input frames to:

```text
C:\Users\User\Desktop\내사진\{scan_id}\selected_3dmm\
  selected frame images
  manifest.json
```

Any `base_profile.json` schema change must increment its version and document migration or backward compatibility. A future 3D artifact tree should not overwrite the `0.2` scan profile; it should reference it as an immutable parent.

### 18.5 Planned mobile states

The future UI should distinguish:

- upload/capture;
- automatic quality review;
- user star and recapture decisions;
- head reconstruction queued/running/failed/complete;
- hairstyle-reference review and hidden-region uncertainty;
- hair reconstruction and fit progress;
- final touch rotation, zoom, reset, fixed camera presets, and still-render selection;
- deletion and training opt-in controls.

The app must not imply that a one-image hairstyle contains known back geometry. Generated or prior-driven regions should be labeled as estimates.

## 19. Personal Base Asset Contract

This section absorbs the former base-model design document. It separates the current 2D profile from the future reusable 3D personal asset.

### 19.1 Current `base_profile.json` version 0.2

The current profile is structured scan data and preview information, not a 3D mesh. It contains or references:

- scan ID and schema version;
- current capture steps and selected representative frames;
- raw face-landmark samples;
- selected 3DMM reconstruction bundle summary;
- derived face/head metrics and anchors;
- hairline guide information;
- preview asset paths and summary metadata.

It is useful as capture provenance and a future worker input, but it must never be presented as the finished personal base model.

### 19.2 Future reusable personal head asset

The future asset should be hairstyle-independent and versioned:

```text
personal_head/{head_id}/
  manifest.json
  source_scan_reference.json
  geometry/
    neutral_head.glb or neutral_head.ply
    topology.json
    flame_parameters.npz
    scalp_region_mask
    cameras.json
  texture/
    base_color_observed.png
    base_color_completed.png
    coverage.exr or npy
    confidence.exr or npy
    generated_region_mask.png
    optional_normal_roughness_specular_maps
  hairline/
    curve_3d.json
    temple_anchors.json
    confidence.json
  quality/
    geometry_report.json
    texture_report.json
    uncertainty.json
```

Exact file formats may change, but the semantic separation is required.

### 19.3 Geometry contract

The head representation should expose:

- stable topology and a documented coordinate system;
- neutral identity shape separate from expression and pose;
- UV coordinates;
- scalp, face, ears, neck, and eye-region masks;
- camera calibration or per-view projection information;
- source-view visibility and confidence;
- hairline and temple anchors;
- provenance for model, weights, code commit, config, and parent inputs.

The current Pixel3DMM V4 `canonical.ply` is an initial geometry artifact. It does not yet satisfy the full production contract because texture, observed/inferred confidence, product storage, and commercial licensing are unresolved.

### 19.4 Face texture contract

Observed and generated appearance must remain distinct:

- `observed` preserves actual sampled photo evidence;
- `completed` fills seams and unseen regions;
- `coverage` records how many and which views contribute;
- `confidence` combines angle, resolution, segmentation, sharpness, exposure, occlusion, and cross-view agreement;
- `generated_region_mask` identifies every area changed or invented by completion.

Never overwrite the raw observed texture with the completed texture. A later model should be reproducible from the raw inputs and manifests.

### 19.5 Hairline contract

Hairline is shared between head reconstruction, UV masking, and hair fitting. Store it as a 3D curve or ordered scalp-surface anchors with:

- frontal, temporal, sideburn, and optional rear regions;
- source-view support;
- observed versus inferred labels;
- regional confidence;
- coordinate transforms into the canonical head and final fitted head.

### 19.6 Reuse principle

The personal head is generated once and reused across hairstyle experiments. Changing hair must not require reconstructing the user's face unless new evidence or a new head-model version is intentionally introduced.

### 19.7 Texture baker status and next experiment

The custom observed-photo texture baker has a first diagnostic implementation.
It runs on the same private photo set and applies identical evidence to three
frozen mesh candidates:

1. raw FLAME template, with no photo-derived values;
2. fitted mean-shape control, where identity shape is mean but camera, pose, expression, jaw, eyes, eyelids, and intrinsics were fit to the user's photos;
3. personal no-MICA candidate, where identity shape was also fit to the user's photos.

The personal no-MICA mesh, fitted mean-shape control, and raw FLAME template have been frozen in the private Drive data layout. The texture baker should start from the private `output/<person>/models/model_trio_for_texture/model_trio_manifest.json` entrypoint, not from ad hoc Colab runtime files. The generated PLY files, private manifests, crops, segmentations, landmarks, textures, and renders must not be committed.

Texture Baker v1 result:

- implemented loader, observed UV splat atlas, coverage map, confidence map,
  source-view map, simple preview fill, material fallback, low-confidence
  fallback, diagnostic eye overlays, and a six-row comparison sheet;
- current representative private sheet:
  `output/_comparison/face_texture_model_comparison_8view_wideface_eyes_conf5_v4.png`;
- visual quality is not product-usable, so no base mesh should be selected from
  this v1 comparison alone.

Texture Baker v2 should be camera-aware and front-focused:

- preserve the input UX: unconstrained selfies plus app scan only;
- use app scan frames as the stable geometry/camera coordinate source and
  selfies as high-detail texture evidence;
- score each photo/frame for blur, face size, pose, exposure, expression,
  segmentation reliability, landmarks, and occlusion;
- fit or load per-image camera, expression, and lighting before comparing a
  render to a photo;
- project mesh triangles into source photos with z-buffer visibility;
- weight samples by view angle, texel resolution, sharpness, exposure,
  segmentation confidence, occlusion, and cross-view consistency;
- preserve observed texture, confidence, source-photo provenance, and
  observed-versus-fallback masks separately;
- focus review on `0`, `±15`, `±30`, and `±45` degrees because this is the
  product-critical range for hair try-on;
- treat rear head and hidden scalp as plausible fallback/completion regions
  rather than pretending they are observed.

After v2 observed baking is stable, add per-user render-to-selfie optimization:
render the current textured head into the useful selfie cameras, compare only
trusted face regions, and iteratively refine camera, lighting, texture, and
very small safe geometry/detail terms. This is first an explicit optimization
loop for one user, not a trained neural network. A learned model may later
approximate this optimization for speed.

Texture Baker v3 current status:

- `experiments/texture_baker/texture_baker_v3.py` is now the latest research
  texture baker.
- It keeps geometry fixed and produces two private variants:
  `v3_no_lighting` and `v3_lighting_normalized`.
- It runs per-person iterations `0..5`, writes per-iteration textures,
  confidence, observed/fill masks, metrics, fitted-camera comparison sheets,
  and front-to-45 review sheets.
- It uses frame-quality filtering, weighted multi-frame UV evidence, whole-face
  bad/empty texel repair, region material fallback, seam smoothing, and skin
  coherence cleanup.
- It selects the earliest clean-enough final iteration, currently `iter_01` in
  the private run, because later iterations reduce numeric error but over-smooth
  visible identity detail.
- Current private outputs are under
  `output/<person>/texture_baker/v3_v3_no_lighting/`,
  `output/<person>/texture_baker/v3_v3_lighting_normalized/`, and
  `output/_comparison/v3_<person>_variant_overview.png`.

The v3 decision is still negative for product readiness. It is cleaner than
v1/v2 and good enough to expose the next bottlenecks, but not good enough for
users. The next texture milestone is dedicated eye/iris/eyelid and mouth
materials, better feature preservation for brows/lips, and stronger masked
fitted-camera texture refinement. Base mesh selection remains blocked by
texture quality.

### 19.8 Private research data layout

Private Colab/Drive artifacts are organized outside Git under a cleaned layout:

```text
MyDrive/hair_app/
  input/<person>/
    selfies/
    scan/
    pixel3dmm_input/
  output/<person>/
    preprocessing/
    models/
    tracking/
    validation/
  shared/models/
  data_layout_manifest.json
```

This layout is the source of truth for the next texture work. Older staging and trash-review folders are not part of the active pipeline once `input/`, `output/`, `shared/`, and `data_layout_manifest.json` have been checked.

## 20. 3D Hair Reconstruction and Fitting Contract

This section absorbs the former hair-synthesis document. It remains a plan: no strand-hair model or fitting module is implemented in this repository yet.

### 20.1 Target flow

```text
hairstyle reference image(s)
  -> reference validation and segmentation
  -> hairstyle geometry reconstruction
  -> canonical strand representation
  -> scalp/root correspondence
  -> hairline-aware retargeting to personal head
  -> collision correction
  -> appearance/material estimation
  -> master strand asset + mobile LOD/hair cards
```

### 20.2 Preferred inputs and uncertainty

Preferred hairstyle inputs are consistent front, oblique, side, and back images of the same style. One image remains supported as a research case, but hidden back volume, internal strand flow, part continuation, and root placement are estimates. The product should expose that uncertainty rather than presenting generated geometry as observed truth.

Before reconstruction, validate:

- whether all references show the same hairstyle;
- face/head orientation and crop quality;
- hair, face, background, accessory, and occluder masks;
- visible hairline and parting;
- approximate length, volume, curl type, bangs, and tied/loose state;
- whether the reference can support a 3D claim.

### 20.3 Candidate models

**DiffLocks** is the first strand baseline because it directly targets 3D hair geometry, but it is not preselected as the long-term winner. It must export usable curves/strands and survive retargeting.

Mandatory comparisons:

- Im2Haircut for image-to-hair reconstruction;
- UniHair or another current multi-view/strand candidate;
- PERM as a longer-term parametric or training foundation;
- newly available models with clearer commercial paths.

The same references, render cameras, head assets, and fit metrics must be used across candidates.

### 20.4 Canonical hair contract

The master representation should preserve:

- ordered root-to-tip points per strand;
- root position and normal in canonical scalp coordinates;
- strand grouping or guide/follower relationships;
- widths, color/material attributes, and confidence;
- reference-view visibility and generated-region labels;
- hairstyle descriptors such as part, length, volume, curl, bangs, and ponytail/bun groups;
- model/version/license/config provenance.

Possible files include `strands.abc`, curve-based USD, or a documented `curves.npz`; the semantic contract matters more than the first container format.

### 20.5 Scalp correspondence and retargeting

Hair generated on a canonical head cannot simply be translated onto a user head. The custom fitting module should:

1. map canonical scalp vertices or UV coordinates to the personal scalp;
2. align frontal and temporal hairline anchors;
3. transport strand roots and local frames;
4. deform guide curves with a smooth scalp-aware field;
5. preserve parting, length, curl, and overall silhouette;
6. update follower strands;
7. report regions whose roots are inferred or unsupported.

### 20.6 Collision correction

After retargeting, detect intersection with scalp, forehead, ears, face, neck, and shoulders when modeled. Correct in stages:

- push penetrated roots to the valid scalp surface;
- repair early strand segments while preserving tangent continuity;
- move long strands along collision gradients or a signed-distance field;
- regularize neighboring guides together to prevent noisy separation;
- recheck collision after every deformation pass;
- record penetration count, depth, affected strands, and residual failure regions.

Collision correction must not silently destroy bangs, volume, or curl to obtain a low penetration score. Visual style metrics and fit metrics are both required.

### 20.7 Hair appearance

Geometry and appearance remain separable. Estimate or expose:

- root-to-tip color variation;
- melanin/dye parameters where the renderer supports them;
- width and roughness;
- highlight and anisotropy parameters;
- reference-lighting uncertainty.

Do not bake a reference photograph's background illumination into geometry. A master material may target Blender/server rendering, while a simplified material or hair-card atlas targets mobile GLB.

### 20.8 Validation

Geometry/style metrics:

- front/side/back silhouette similarity;
- part-line location;
- length, volume, curl, and strand-flow agreement;
- multi-view consistency;
- hidden-region uncertainty.

Fit metrics:

- root-to-scalp distance;
- hairline alignment error;
- penetration count and maximum/mean depth;
- detached roots;
- ear/face collision by region;
- change in style metrics before versus after fitting.

Product metrics:

- runtime and failure/recapture rate;
- mobile GLB size and frame rate;
- touch rotation, zoom, reset, and fixed-view usability;
- user judgment that the result resembles both their identity and the requested hairstyle.

### 20.9 Mobile conversion and fallback

Keep a high-quality master strand asset. Derive mobile LODs, optimized guide/follower strands, meshes, or hair cards from it. Do not make the mobile representation the only source of truth.

If 3D hair reconstruction is uncertain, acceptable fallbacks include asking for more views, offering a lower-confidence preview, generating server-side still turntables, or using a clearly labeled 2D refinement. A fallback must not be described as measured 3D truth.

### 20.10 Hair fine-tuning order

1. reproduce official inference;
2. verify export and retargeting contracts;
3. score fixed Hair App references;
4. identify the dominant failure mode;
5. confirm data and model licensing;
6. fine-tune only the stage whose measured gap justifies it;
7. keep the original baseline for regression testing.
## 21. 2026-06-27 Current Override: FaceBuilder Automation

The earlier sections preserve the full product architecture and research plan.
They are intentionally not deleted because they contain useful contracts for
capture, personal head assets, UV texture, 3D hair, scalp retargeting,
collision, GLB delivery, privacy, licensing, evaluation, and milestones.

However, the near-term implementation priority changed after Texture Baker v3.
The current main head-generation candidate is now:

```text
ordinary selfies + app scan frames
  -> photo/frame scoring
  -> automated FaceBuilder/KeenTools solve in headless Blender
  -> private mesh + texture + blend
  -> Hair App bald-head post-processing
  -> front-to-45 review sheets
  -> hairline/scalp fitting
  -> collision correction
  -> mobile GLB
```

### 21.1 Why this overrides the previous head/texture plan

The previous custom path was:

```text
Pixel3DMM/FLAME model trio
  -> custom Texture Baker
  -> cleanup/completion
  -> base mesh comparison
```

That path produced useful diagnostics but not product-quality results. The main
observed failure was not one small bug. It was a combination of camera alignment
error, fixed-geometry limits, occlusion, lighting mismatch, low observed UV
coverage, eye/mouth material problems, and completion passes that could flatten
identity while improving numeric metrics.

The user's manual FaceBuilder test produced a much stronger starting head, so
the next work should automate and post-process FaceBuilder instead of continuing
to tune the custom baker as the main engine.

### 21.2 What stays valid from the old master plan

Keep these parts of the old plan:

- simple user input contract;
- app scan and selfie provenance;
- privacy rules;
- stable asset manifests;
- observed versus inferred region tracking;
- front-to-45 visual review focus;
- hairline/scalp contracts;
- hair retargeting and collision requirements;
- mobile GLB delivery;
- evaluation gates and baseline comparisons.

The model choice changed, but the product contract did not.

### 21.3 Current v1/v2/v3 automation status

The first FaceBuilder comparison pipeline now exists in
`experiments/facebuilder_bridge/`.

Implemented:

- `facebuilder_version_runner.py` runs the local private v1/v2/v3 comparison
  batch from normal Python.
- `blender_facebuilder_batch_scene.py` runs inside headless Blender, creates the
  FaceBuilder head, adds image candidates, auto-aligns, bakes texture, saves a
  private `.blend`, exports OBJ/GLB, and renders review yaw images.
- v1 uses all photos and baseline FaceBuilder auto-align.
- v2 adds photo scoring and selection.
- v3 adds face-crop alignment candidates and a strict texture gate: frontal,
  color-clean crops can contribute to texture, while profile/side photos can
  still help alignment but are disabled for texture baking.
- Private output folders are created under:

```text
<drive_root>/output/facebuilder_v1/<person>/
<drive_root>/output/facebuilder_v2/<person>/
<drive_root>/output/facebuilder_v3/<person>/
```

Latest private comparison summary:

| Version | Person | Selected | Rejected | Aligned | Failed | TexCams |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| v1 | Juseop | 11 | 0 | 10 | 1 | 10 |
| v1 | Eunchae | 8 | 0 | 7 | 1 | 7 |
| v2 | Juseop | 7 | 4 | 6 | 1 | 6 |
| v2 | Eunchae | 7 | 1 | 6 | 1 | 6 |
| v3 | Juseop | 7 | 4 | 7 | 0 | 2 |
| v3 | Eunchae | 7 | 1 | 7 | 0 | 1 |

The important interpretation is that v3 is currently the best automated
baseline, but it is still not product quality. It improves alignment reliability
and reduces some texture contamination, but visible defects remain around
scalp/hair patches, eyes, mouth/nostrils, neck/ear seams, and occasional
background or clothing leakage.

### 21.4 New near-term milestones

1. Human review of v1/v2/v3:
   - inspect private review sheets and GLBs;
   - decide whether v3 is the right base for the next iteration;
   - record what fails visually before changing more logic.

2. Semantic bald-head post-processing:
   - remove hair, headwear, glasses, shirt, and background leakage;
   - fill scalp, neck, rear head, and low-confidence skin;
   - improve eyes, iris, eyelids, mouth interior, lips, ears, brows, and skin
     material;
   - preserve confidence/provenance maps.

3. Stronger input analysis before FaceBuilder:
   - robust landmarks;
   - pose/yaw;
   - eye closed / mouth open;
   - glasses, phone, hand, hair, and headwear occlusion;
   - segmentation confidence;
   - lighting and color normalization.

4. Mesh strategy decision:
   - use FaceBuilder mesh directly if it supports hair fitting, scalp mapping,
     collision, and mobile GLB constraints;
   - transfer/retopologize only if the direct mesh fails those gates.

5. Hair fitting:
   - proceed after the bald-head substrate is credible;
   - keep hair reconstruction, scalp retargeting, and collision requirements
     from section 20.

### 21.5 Archived old-engine docs

The standalone active docs for Pixel3DMM V4 and Texture Baker have been moved
into `docs/history.md` as detailed archives. They are no longer active source
of truth documents because they describe engines that are not the current main
path.

Use `docs/history.md` for the full record of:

- Pixel3DMM V4 preprocessing, execution, errors, fixes, and results;
- Texture Baker loader/v1/v2/v3 commands, outputs, failures, and lessons;
- FaceBuilder/KeenTools pivot and automation verification.

### 21.6 Current active implementation references

Current active references:

- `README.md` for the high-level current state;
- `newchat.md` for compact handoff;
- `AGENTS.md` for agent rules;
- `docs/history.md` for detailed project history and archived old-engine docs;
- `experiments/facebuilder_bridge/README.md` for FaceBuilder automation tools.
