# Problem Definition

Last synchronized: 2026-06-21
Status: current working problem definition; success criteria may change after user tests

## Problem

사용자는 마음에 드는 헤어스타일 사진을 찾아도 그 스타일이 자신의 실제 얼굴, 두상, 헤어라인, 이마, 귀, 옆모습과 어울릴지 판단하기 어렵다.

일반적인 한 장짜리 2D 헤어 합성은 빠른 데모에는 유용하지만 다음 정보를 약하게 다룬다.

- 코 높이, 광대, 턱선, 얼굴 폭과 깊이.
- 좌우 profile과 비대칭.
- 실제 hairline과 temple shape.
- 머리카락에 가린 scalp와 skull의 불확실성.
- 기준 헤어스타일의 뒤쪽 길이, 층, volume.
- 여러 각도에서 같은 얼굴과 같은 헤어가 유지되는 3D consistency.
- 머리카락이 이마·귀·두피를 뚫지 않는 물리적 plausibility.

Hair App의 현재 핵심 문제는 단순히 그럴듯한 한 장의 이미지를 만드는 것이 아니다.

> 여러 사용자 사진과 가이드 스캔을 이용해 편집 가능한 개인 3D 머리와 실제 사진 기반 얼굴 표면을 만들고, 독립된 3D 헤어스타일을 사용자의 두상과 헤어라인에 안정적으로 맞추는 것.

## Target User Need

- 미용실 방문 전 원하는 스타일을 자신의 여러 각도에서 확인.
- 정면뿐 아니라 측면·후면에서의 적합성 비교.
- 자신의 실제 hairline, forehead, face shape를 반영한 결과.
- 다른 스타일로 바꿀 때 얼굴 모델을 매번 다시 만들지 않는 reusable profile.
- 결과 중 어떤 부분이 사진에서 관측됐고 어떤 부분이 AI가 추정했는지에 대한 정직한 안내.

## Product Hypotheses

### H1. Multi-photo geometry

한 장의 selfie보다 정면·좌우·profile·hairline-visible 입력을 함께 사용하면 얼굴 깊이, side contour, hairline, camera consistency가 좋아질 것이다.

### H2. Direct observed texture

사용자 얼굴 전체를 AI가 다시 그리게 하는 것보다 실제 사진의 visible skin pixels를 공통 UV atlas에 직접 투영하면 identity와 세부 특징이 더 잘 보존될 것이다.

### H3. Independent hair representation

얼굴과 현재 머리카락을 하나의 Gaussian avatar로 묶는 것보다 head mesh, UV texture, strand hair를 분리하면 스타일 교체, hairline fitting, collision correction, mobile export가 쉬울 것이다.

### H4. Guided pulled-back-hair scan

머리를 뒤로 넘긴 scan은 실제 hairline, temples, forehead, ear 주변 geometry를 개선할 것이다. 다만 계속 가려진 crown/rear scalp는 measured truth가 아니라 inferred prior로 남는다.

### H5. Quality and star weighting

사용자가 선택한 1~2장의 star photo와 자동 quality score를 regional visibility와 결합하면 피부색·입술·눈썹 같은 appearance 품질이 좋아질 것이다. Star는 side evidence를 무시하는 global override가 되어서는 안 된다.

### H6. 3D hair before 2D polish

DiffLocks/Im2Haircut/PERM 계열로 independent 3D hair를 만들고 geometry로 맞춘 뒤, 필요하면 FLUX.2 같은 2D model을 presentation render에만 사용하는 것이 multi-view consistency를 지키는 데 유리할 것이다.

이 가설들은 아직 검증되지 않았다. 어느 하나가 실패하면 capture, representation, model, fine-tuning 순서를 바꿀 수 있다.

## Current MVP Problem Statement

현재 저장소에서 이미 해결된 문제:

1. mobile browser에서 guided 4-step scan 실행;
2. MediaPipe로 frame quality와 landmark 수집;
3. accepted frame과 JSON을 backend에 저장;
4. reusable `base_profile.json` version `0.1` 생성;
5. 대표 frame과 landmarks/hairline preview 표시.

다음 검증 문제:

1. 기존 selfie upload와 star 선택을 capture model에 어떻게 추가할지 결정;
2. Pixel3DMM이 Hair App의 multi-photo set에서 usable hairless mesh를 만드는지 확인;
3. KaoLRM 및 보조 VGGT가 geometry를 개선하는지 비교;
4. actual pixels 기반 multi-photo UV baker의 identity 보존 확인;
5. DiffLocks와 competing hair models가 retarget 가능한 strands를 제공하는지 확인;
6. strand hair를 reconstructed scalp에 맞추고 collision을 제거;
7. mobile GLB로 acceptable quality와 frame rate 달성.

## Success Criteria

초기 연구 성공은 논문 benchmark 하나로 결정하지 않는다.

- 사용자가 neutral render에서도 자신을 알아본다.
- source views로 render-back했을 때 landmarks와 silhouette가 안정적이다.
- central face texture가 generative redraw 없이 실제 사용자 색과 세부를 유지한다.
- observed/generated UV 영역과 confidence를 구분할 수 있다.
- 원하는 hairstyle의 silhouette, part, length, curl, volume이 여러 view에서 유지된다.
- roots가 scalp/hairline에 붙고 명백한 penetration이 없다.
- 한 장 style input의 hidden back이 추정임을 명확하게 표시한다.
- asset이 GLB 또는 안정적인 viewer format으로 export된다.
- 전체 실패율, latency, cost, manual correction을 측정할 수 있다.
- research license와 commercial path를 구분한다.

## Non-Goals For The First 3D Prototype

- 의료용 두개골 또는 두피 측정 정확도.
- 실시간 AR hair simulation.
- 모든 모발 종류와 복잡한 braid를 첫 버전부터 완벽하게 처리.
- 스마트폰에서 full strand simulation을 직접 실행.
- 처음부터 foundation model 전체 학습.
- 연구용 비상업 모델을 그대로 commercial launch에 사용.

## Current Working Direction

첫 end-to-end 연구 조합은 다음과 같다.

```text
MediaPipe guidance
  -> Pixel3DMM head baseline (+ optional VGGT initialization)
  -> Hair App multi-photo UV baker (+ optional FreeUV completion)
  -> DiffLocks strand-hair baseline
  -> custom scalp retargeting and collision correction
  -> server render + mobile GLB/Three.js
```

이 조합은 실험 시작점일 뿐이다. 상세한 대체 후보와 decision gate는 [`10_3d_hair_app_master_plan.md`](10_3d_hair_app_master_plan.md)에 있다.
