# Idea Evolution

Last synchronized: 2026-06-21
Status: decision history; current direction is the true 3D pipeline in `10_3d_hair_app_master_plan.md`

Hair App의 방향은 실패한 시도를 지우는 대신, 무엇을 배워 다음 구조로 이동했는지를 보존한다. 아래 stage는 영구적인 선형 roadmap이 아니라 당시의 판단 기록이다.

## Stage 1: Structured Scan Foundation

첫 구현은 generation보다 reusable data collection에 집중했다.

1. `front`, `left`, `right`, `hairline` 가이드 scan.
2. MediaPipe Face Landmarker로 quality check.
3. 단계별 양질 frame 자동 수집.
4. frame, landmarks, pose proxy, quality를 backend 저장.
5. `base_profile.json` version `0.1` 생성.

이 foundation은 구현됐다. 현재 profile은 3D avatar가 아니라 이후 geometry, texture, masking, validation에 재사용할 structured 2D scan data다.

## Stage 2: Hair-Specific 2D/Multi-View Model Experiment

초기에는 StableHairV2, Stable-Hair, HairFusion, HairFastGAN, HairPort 같은 hair-specific research model을 우선 검토했다.

StableHairV2 공식 inference를 Colab에서 실행하는 데 성공했지만, normal portrait + hairstyle reference에서는:

- 얼굴과 배경까지 심하게 재생성;
- identity 보존 실패;
- severe artifacts;
- bald/hair-cleared source에 강한 입력 가정;
- product가 원하는 controlled replacement와 mismatch

가 나타났다.

이 단계의 핵심 교훈은 `hair-specific`이라는 이름만으로 product fit이 보장되지 않는다는 것이다. 재현 recipe와 failure는 `07_hair_engine_experiment_plan.md`에 보존한다.

## Stage 3: General 2D Image Editing Foundation

다음으로 Qwen Image Edit, HiDream, FLUX.2, LongCat, Step1X 같은 general image editor를 Hair App controls와 결합하는 방향을 검토했다.

계획은:

- user portrait와 style reference를 별도 input으로 사용;
- masks, landmarks, hairline anchors 활용;
- identity score, protected-region compositing, retry/ranking;
- winning baseline에 LoRA 또는 editing SFT 적용

이었다.

2026-06-20에는 `FLUX.2 [klein] base-9B`를 첫 2D tuning target으로 선택했다. 사용자가 Space에서 가능성을 확인했고, single H100에서 fine-tuning 가능한 undistilled base와 multi-reference 구조가 매력적이었다. 다만 이 선택 이후 제품 목표 자체가 더 명확해졌다.

## Stage 4: Editable True 3D Architecture

사용자가 원하는 결과는 한 장의 합성 사진이 아니라:

- 여러 각도에서 회전 가능;
- 사용자의 실제 얼굴·두상 반영;
- 원하는 hair를 독립적으로 교체;
- hairline에 맞춰 root fitting;
- face/ear/scalp penetration 제거

가 가능한 3D asset이라는 결론에 도달했다.

이에 따라 core representation을 다음처럼 바꿨다.

```text
editable head mesh
  + actual-photo-derived face UV texture
  + independent 3D strand hair
  + geometric retargeting/collision
```

### Why Pixel3DMM Entered the Plan

Pixel3DMM은 visible face evidence와 screen-space priors를 사용해 FLAME-family geometry를 fit할 수 있어 첫 hairless-head baseline으로 적합하다. 여러 user images를 shared identity로 활용할 수 있고 mesh/camera output은 UV baking의 출발점이 된다.

단, 출력은 사진 아래 실제 skull을 그대로 scan한 것이 아니다. 가려진 scalp는 model prior의 추정이며, pulled-back-hair scan은 hairline과 visible scalp만 더 잘 constrain한다.

### Why FastAvatar Was Considered and Then Removed From the Core

처음에는 Pixel3DMM을 geometry teacher로 쓰고 FastAvatar 계열을 Hair App multi-image model로 개조하는 생각이 있었다. 이는 photorealistic full avatar가 목표일 때 합리적인 가설이었다.

그러나 Hair App은 stable UV mesh와 replaceable hair가 필요하다. FastAvatar의 Gaussian output은:

- mesh/UV와 representation이 다르고;
- 기존 hair와 appearance가 entangle될 수 있고;
- face color만 얻기 위해 또 하나의 full 3D avatar를 만든 뒤 다시 mesh로 옮겨야 한다.

따라서 compute와 무관하게 core에서 제외했다. visual benchmark 또는 future alternative로는 남는다.

### Why Hair App Builds a UV Baker

여러 사진에서 실제로 보이는 얼굴은 AI가 새로 상상할 필요가 없다. Pixel3DMM mesh와 camera를 사용해 visible pixels를 common UV atlas로 옮기면 된다.

Hair App이 직접 구현하는 부분은 새 rasterizer를 처음부터 만드는 것이 아니라:

- visibility and occlusion;
- regional view suitability;
- sharpness/exposure/white-balance;
- star bonus;
- segmentation;
- seams and de-lighting;
- coverage/confidence

를 product input에 맞게 조합하는 UV pipeline이다. FreeUV 계열은 unobserved holes를 보완한다.

### Why DiffLocks Is the First Hair Candidate

Hair App은 style을 교체하고 scalp에 맞춰야 하므로 strand representation이 유리하다. DiffLocks는 single-image strand generation, training code, synthetic data pipeline을 제공해 첫 research baseline으로 선택했다.

확정은 아니다. Im2Haircut, UniHair와 동일 test set으로 비교하고, 장기적으로 PERM 기반 clean model도 검토한다.

## Current Decision

현재 첫 연구 pipeline:

1. user multi-photo + hairline/head scan;
2. Pixel3DMM head baseline, optional VGGT support;
3. Hair App multi-photo UV baker;
4. FreeUV-style completion only for missing regions;
5. DiffLocks strand hair;
6. custom geometric fitting/collision;
7. GLB/Three.js and optional server renders.

FLUX.2 연구는 헛수고가 아니다. 2D quality benchmark, auxiliary hairstyle views, presentation render refinement, fallback에 재사용한다. 다만 interactive 3D geometry의 source of truth는 아니다.

모든 model choice는 controlled Hair App test 결과에 따라 교체 가능하다. 상세 decision gate는 `10_3d_hair_app_master_plan.md`를 따른다.
