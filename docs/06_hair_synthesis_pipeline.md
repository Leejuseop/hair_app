# 3D Hair Synthesis and Fitting Pipeline

Last synchronized: 2026-06-24
Status: planned research pipeline; not implemented and not frozen

## 한 문장으로 설명

사용자가 원하는 헤어스타일 사진을 넣으면 그 머리를 **얼굴 이미지에 바로 합성하는 것이 아니라 독립된 3D 머리카락 가닥으로 만들고**, 그 가닥의 뿌리를 사용자의 두피와 헤어라인에 맞춘 다음 얼굴·귀·두피를 뚫는 부분을 고쳐서 회전 가능한 결과로 만드는 미래 단계다.

현재 구현된 기능이 아니라 Pixel3DMM으로 개인 head를 만든 뒤 진행할 hair 쪽 설계다. DiffLocks·Im2Haircut 같은 후보 중 어떤 엔진을 쓸지 비교하고, 최종 strand 결과를 사용자 두상에 옮기는 방법을 정리한다.

## Purpose

이 문서는 hairstyle reference에서 independent 3D hair를 만들고 personal head에 맞추는 부분을 상세히 설명한다. 전체 product architecture와 head/UV 계획은 `10_3d_hair_app_master_plan.md`를 기준으로 한다.

현재 repository에는 실제 hair reconstruction, strand export, fitting, collision, GLB build가 없다. `POST /api/generate`와 result route는 placeholder다.

## Target Flow

```text
hairstyle reference image(s)
  -> input analysis and masks
  -> 3D hairstyle reconstruction
  -> canonical strand representation
  -> source-to-user scalp correspondence
  -> hairline-aware deformation
  -> collision correction
  -> validation renders
  -> master strands + mobile hair cards
```

## Stage 1: Hairstyle Input

### Preferred Inputs

- front style view;
- left/right three-quarter or profile;
- rear view;
- clean background when possible;
- enough resolution to see strand flow and silhouette;
- optional metadata: length, part, bangs, curl, density, volume.

### One-Image Limitation

한 장만 입력하면 rear length, hidden layers, crown, occluded roots는 복원할 수 있는 관측 정보가 없다. Model은 learned prior로 plausible hypothesis를 만든다.

UI와 result manifest는:

- observed views;
- inferred hidden regions;
- confidence;
- auxiliary generated view 사용 여부

를 구분해야 한다.

FLUX.2 같은 image model로 side/rear hypotheses를 만들 수 있지만 이를 사실로 간주하지 않는다. 여러 plausible variants를 만들고 user가 선택하는 방식도 future option이다.

## Stage 2: Preprocessing

가능한 처리:

- head/face/hair/background segmentation;
- hair silhouette and alpha matte;
- strand orientation map;
- depth estimate;
- source-camera and head-pose estimate;
- scalp/head proxy;
- accessories and occlusion mask;
- style attribute extraction;
- crop and color normalization.

Preprocessing output도 model-independent하게 저장해 candidate 비교에 재사용한다.

## Stage 3: Candidate 3D Hair Models

### DiffLocks: First Baseline

현재 첫 research baseline이다.

선택 이유:

- RGB image에서 strand-based 3D hair 목표;
- StrandVAE와 scalp-space diffusion 구조;
- full training code;
- synthetic hairstyle data pipeline;
- Alembic/Blender로 이어질 수 있는 strand output.

검증할 점:

- official output을 stable하게 재현하는가;
- real phone hairstyle image에서 strand 방향과 silhouette가 맞는가;
- source scalp에서 strands를 분리할 수 있는가;
- arbitrary user scalp로 retarget할 때 root order가 유지되는가;
- curly/coily/braided/short hair coverage가 충분한가;
- public license와 commercial option이 project 요구에 맞는가.

### Im2Haircut: Mandatory Comparison

- single-image strand reconstruction 후보;
- real-reference fitting 품질 비교;
- per-subject optimization 시간과 failure rate 측정;
- non-commercial dependency와 complex setup audit;
- DiffLocks보다 좋은 style fidelity가 나오면 stage별 hybrid 가능.

### PERM: Long-Term Foundation Candidate

- MIT code의 parametric strand-hair prior;
- interpolation, generation, model training에 유용;
- 공개된 single-image end-to-end reconstruction은 아직 완전한 product engine이 아님;
- 장기적으로 Hair App-owned image encoder + PERM-like decoder를 만들 때 참고.

### UniHair and Other Alternatives

- UniHair: braid와 complex style에 대한 Gaussian-hair comparison.
- GaussianHaircut/NeuralHaircut: future video/multi-view style input path.
- HairPort: final 2D transfer benchmark와 3D-aware alignment 아이디어.
- 새로운 2026+ strand model이 공개되면 같은 artifact contract로 비교.

DiffLocks는 확정 winner가 아니다. 동일 hairstyle set으로 candidates를 비교한 뒤 temporary baseline을 선택한다.

## Stage 4: Canonical Hair Contract

Candidate model의 internal output을 그대로 app 전체에 퍼뜨리지 않는다. 중간 format을 정의한다.

가설 contract:

```text
canonical_hair/
  strands.abc
  curves.npz
  source_scalp.glb
  source_hairline.json
  style_attributes.json
  reconstruction_confidence.npy
  model_manifest.json
  previews/
```

각 strand:

- root position;
- ordered 3D points/control points;
- tangent or orientation;
- width/radius profile;
- group/clump ID if available;
- confidence;
- observed/inferred classification.

Coordinate system, units, handedness를 명시한다.

## Stage 5: Scalp Correspondence

Source hairstyle scalp와 personal head scalp 사이 mapping이 필요하다.

Potential methods:

- common FLAME/scalp topology;
- canonical scalp UV coordinates;
- landmarks: centerline, front hairline, temples, ears, crown, nape;
- non-rigid surface registration;
- learned deformation field if geometry-only mapping fails.

첫 버전은 deterministic geometry를 우선한다. Model output이 다른 head topology에 묶여 있으면 conversion layer를 둔다.

## Stage 6: Hairline-Aware Retargeting

1. source root를 canonical scalp에 parameterize.
2. user scalp의 corresponding point로 root 이동.
3. head width/depth/height에 맞춰 global deformation.
4. local tangent, curl, clump, volume을 최대한 보존.
5. front roots를 user hairline에 style-aware하게 정렬.
6. ears, forehead, neck, shoulder relation을 조정.

Hairline은 무조건 노출되는 hard boundary가 아니다. Bangs, fringe, loose strands는 hairline 앞을 덮을 수 있다. Root attachment와 visible silhouette를 구분한다.

## Stage 7: Collision Correction

검출 대상:

- scalp penetration;
- forehead/face penetration;
- ear intersection;
- neck/shoulder intersection;
- floating roots;
- impossible root direction;
- extreme stretching or collapsed curls.

후보 기법:

- signed-distance field around user mesh;
- root projection to scalp;
- iterative point/curve displacement;
- local Laplacian/elastic regularization;
- strand-group optimization;
- Blender physics-assisted relaxation for difficult cases.

Collision correction는 hairstyle identity를 무너뜨리지 않아야 한다. Penetration count만 줄이고 volume과 silhouette를 망가뜨리는 해법은 실패다.

## Stage 8: Hair Appearance

Geometry와 material을 분리해 관리한다.

- base color/melanin proxy;
- roughness/specular;
- root-to-tip color variation;
- alpha/width;
- anisotropic shader parameters;
- highlight direction.

Reference lighting을 그대로 bake하면 다른 view와 light에서 부자연스러울 수 있다. 첫 prototype은 neutral material로 geometry를 검증하고, 이후 appearance extraction을 추가한다.

## Stage 9: Validation

### Geometry and Style

- front/side/rear silhouette similarity;
- part direction;
- length and layer distribution;
- curl/wave/coily attributes;
- volume and crown height;
- bangs/fringe geometry;
- strand orientation;
- scalp coverage.

### Fit

- floating roots count;
- penetration length/count;
- ear/forehead collision;
- hairline alignment;
- severe deformation ratio;
- several head-shape robustness.

### Product

- total runtime;
- H100 VRAM;
- failure and manual fix rate;
- master asset size;
- hair-card GLB size and mobile FPS;
- user preference.

## Stage 10: Mobile Conversion

Full strand asset은 server render와 master storage에 유지할 수 있다. Mobile web에는 다음을 비교한다.

- reduced strand count;
- converted mesh tubes for limited styles;
- clustered hair cards;
- multiple LODs;
- compressed textures;
- Three.js anisotropic approximation.

Mobile conversion은 strand master를 파괴하지 않는 derived artifact여야 한다.

## Fine-Tuning Plan

현재 순서:

1. DiffLocks official inference 재현.
2. Hair App-like real references로 baseline failure 수집.
3. Im2Haircut/UniHair와 같은 style set으로 비교.
4. output strand contract와 retarget feasibility 확인.
5. 그 뒤 data gap이 명확한 component부터 fine-tune.

가능한 fine-tuning target:

- image feature encoder;
- StrandVAE;
- scalp diffusion/flow model;
- style attribute conditioning;
- diverse hair type coverage;
- multi-view consistency;
- collision-aware post-fit refinement.

데이터와 license가 가장 큰 위험이다. H100 availability는 training을 쉽게 하지만 legal strand datasets와 representative real-image validation을 대신하지 않는다.

## Failure and Fallback

- single-image ambiguity가 크면 multiple style photos를 요구.
- strand model이 style을 못 맞추면 multiple candidates를 생성하고 user selection.
- 특정 braid/complex style은 UniHair 또는 specialized path로 routing.
- 3D output이 아직 부족하면 FLUX.2/HairPort-like 2D preview를 명확한 fallback으로 제공.
- geometry fit가 실패하면 user에게 다른 style view 또는 hairline scan을 요청.

어떤 fallback도 실패 사실을 숨기거나 2D result를 rotatable true 3D로 표현하면 안 된다.
