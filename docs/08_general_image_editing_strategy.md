# General Image Editing Strategy in the 3D Hair App

Last synchronized: 2026-06-21
Status: auxiliary 2D path and quality benchmark; no longer the core product architecture

## Current Decision

Hair App의 core는 editable 3D head mesh, actual-photo-derived UV texture, independent 3D hair, geometric fitting이다. General image editor가 core geometry나 interactive result의 source of truth가 되지는 않는다.

하지만 Qwen Image Edit, HiDream, FLUX.2, LongCat, Step1X, HairPort-like pipelines에 대한 연구는 다음 역할로 계속 유효하다.

- true 3D pipeline과 비교할 visual-quality ceiling;
- 3D 기능이 완성되기 전 빠른 2D fallback;
- hairstyle reference의 auxiliary side/rear hypothesis 생성;
- input cleanup, segmentation aid, background normalization;
- server-rendered still image의 presentation refinement;
- training target bootstrap 연구;
- marketing mockup과 user concept validation.

한 camera에서 diffusion으로 수정한 결과는 다른 camera와 3D consistency가 보장되지 않는다. 따라서 independently edited images를 rotatable geometry처럼 취급하지 않는다.

## Historical Direction

2026-06-20까지의 primary hypothesis는:

```text
user portrait + hairstyle reference + scan controls
  -> general multi-reference image editor
  -> identity/landmark checks
  -> final 2D portrait
```

였다. 이 방향에서 `FLUX.2 [klein] base-9B`를 first tuning target으로 선택했지만 실제 training은 시작하지 않았다. 이후 user requirement가 rotatable, editable, independent-hair 3D로 명확해져 이 전략을 보조 경로로 이동했다.

이전 decision은 실패나 낭비로 버리지 않는다. FLUX.2 architecture, LoRA, multi-reference input, identity evaluation, data-pair thinking은 2D refinement와 auxiliary-view research에 재사용한다.

## Current Candidate Roles

### FLUX.2

Potential uses:

- hairstyle reference cleanup;
- one-image style의 여러 plausible view 생성;
- neutral renderer output refinement;
- 2D fallback;
- HairPort-like final presentation.

주의:

- generated side/rear view는 hidden style의 true observation이 아님;
- per-view diffusion은 camera consistency를 깰 수 있음;
- face identity가 변할 수 있으므로 original head render와 embedding/landmark/protected-region 비교 필요;
- 9B public model license는 research/commercial path를 구분해야 함.

### Qwen Image Edit

- high-quality multi-image editing reference;
- portrait + hairstyle reference 2D benchmark;
- text/image semantic encoder가 강하게 결합되어 lightweight text-removal 가정과는 맞지 않을 수 있음;
- 3D geometry output이 아니므로 core replacement가 아님.

### HiDream

- multi-reference personalization과 layout/skeleton-like controls 비교;
- renderer refinement 또는 2D fallback candidate;
- exact model availability, license, training ecosystem은 사용 시점에 재검증.

### LongCat and Step1X

- difficult edit instruction comparison;
- training recipe와 LoRA/DPO reference;
- multi-reference exact hairstyle transfer와 identity 성능은 Hair App test로 검증.

### HairPort

- bald conversion, 3D-aware alignment, final 2D refinement 아이디어가 current 3D direction과 연결됨;
- FLUX-family knowledge의 실용성을 보여주는 reference;
- output은 editable 3D hair가 아니라 final 2D transfer이므로 core hair engine이 아님;
- public license restriction을 확인해야 함.

## 2D Evaluation Protocol

2D model을 다시 비교할 때는 3D pipeline과 분리된 label을 사용한다.

### Input

- same user portrait or same rendered personal-head view;
- same hairstyle reference set;
- same instruction;
- same output size;
- multiple fixed seeds where supported;
- original and 3D-render baseline saved together.

### Scores

- face identity similarity;
- landmark displacement;
- protected-region preservation;
- hairline and temple fit;
- hairstyle silhouette, part, curl, length, volume;
- background/clothing preservation;
- visible artifacts;
- cross-view consistency if several views are edited;
- runtime, VRAM, failure rate;
- license and fine-tuning feasibility.

Cross-view inconsistency should be measured explicitly. A beautiful front image with incompatible side/rear images is not a successful 3D substitute.

## Auxiliary-View Policy

If a style reference has one view:

1. record the original observed view;
2. generate several side/rear hypotheses rather than one alleged truth;
3. keep generation seeds and model versions;
4. use hypotheses only as conditioning/prior evidence;
5. let strand model and geometry constraints decide a plausible 3D asset;
6. expose uncertainty or variant choices to the user when practical.

Do not train the system to treat generated views as equivalent to real multi-view capture without confidence weighting and validation.

## Render Refinement Policy

When refining a render:

- preserve the geometry render and depth/normal/mask inputs;
- lock face and protected regions where possible;
- compare the refined image with the unrefined render;
- reject identity or hairline drift;
- do not feed refined pixels back into the head UV unless explicitly validated;
- mark the image as a presentation render, not geometry evidence.

## Fine-Tuning Decision

General image-editing fine-tuning is not the immediate next step. It becomes active when one of these conditions is met:

- users need a temporary high-quality 2D preview before 3D completion;
- auxiliary style views materially improve strand reconstruction;
- raw 3D renders are accurate but visually insufficient for presentation;
- controlled tests show a clear business value separate from true 3D.

If active, start from a fresh license and model audit. `09_flux2_klein_tuning.md` preserves the earlier FLUX.2 plan but should not be executed automatically as the current top priority.

## Relationship to the Main Plan

Current priority:

1. Pixel3DMM/KaoLRM head bake-off.
2. direct multi-photo UV prototype.
3. DiffLocks/Im2Haircut/UniHair hair bake-off.
4. geometric retargeting and collision.
5. GLB/viewer.
6. optional 2D benchmark/refinement where measured useful.

이 순서는 결과로 수정할 수 있다. 2D path가 unexpectedly strong product value를 보이거나 3D stage가 장기간 막히면 parallel MVP로 승격할 수 있지만, true 3D와 혼동하지 않는다.

## Research Links

- Qwen Image: <https://github.com/QwenLM/Qwen-Image>
- DiffSynth Studio: <https://github.com/modelscope/DiffSynth-Studio>
- FLUX.2: <https://github.com/black-forest-labs/flux2>
- LongCat Image: <https://github.com/meituan-longcat/LongCat-Image>
- Step1X Edit: <https://github.com/stepfun-ai/Step1X-Edit>
- HairPort: <https://github.com/deepmancer/HairPort>
