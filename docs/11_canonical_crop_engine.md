# Canonical Face Crop Engine

Last synchronized: 2026-06-23
Status: v1~v3 historical roll experiments; V4 Pixel3DMM-compatible no-roll path implemented, live validation pending

> **Current decision:** v1~v3의 RetinaFace 5-point roll을 Pixel3DMM 기본 전처리에 연결하지 않는다. 공식 upstream code를 다시 감사한 결과 실제 fitting landmark는 persistent crop 이후 PIPNet이 만드는 WFLW 98점이고, tracker가 camera/head rotation을 직접 최적화한다. 최종 통합 설계는 `docs/12_pixel3dmm_preprocessing_contract.md`가 source of truth다. 이 문서의 v1~v3 내용은 실패 원인과 아이디어 진화를 보존하는 실험 기록이다.

## Purpose

Hair App은 한 영상의 연속 frame만 받는 것이 아니라, 해상도·얼굴 위치·촬영 거리·각도·장애물이 서로 다른 독립 사진을 여러 장 받는다. 따라서 각 사진에서 얼굴을 따로 찾고 Pixel3DMM 전처리에 들어갈 일정한 512×512 입력으로 바꿔야 한다.

v1~v3 historical crop은 다음 정보를 정규화하려 했다.

- 얼굴의 대략적인 중심 위치;
- 얼굴이 crop에서 차지하는 크기;
- 카메라 평면 안에서 기울어진 roll.

yaw와 pitch는 여러 각도의 3D 단서이므로 없애지 않았다. 이후 official source audit에서 default roll normalization도 제거하기로 결정했다. 원본은 항상 보존하며 crop은 derived asset이다.

## What Is Open Source and What Is Hair App Code

현재 얼굴 검출 AI 자체를 Hair App이 새로 학습한 것은 아니다.

- **Open source / pretrained:** `facer`의 `retinaface/mobilenet` detector. bbox, detection score, 5개 point(두 눈·코·두 입꼬리)를 출력한다.
- **Hair App code:** 사진별 독립 처리, 다중 얼굴 선택, landmark plausibility 검사, roll 적용/생략 판단, crop 크기와 중심 계산, affine resampling, reflect padding, observed-source validity mask, 원본↔crop 행렬, metadata/manifest, Pixel3DMM용 디렉터리 구성, 단위 테스트와 Colab 실험 notebook.

즉, 얼굴을 찾는 pretrained detector는 가져다 쓰고 그 결과를 Hair App과 Pixel3DMM의 입력 계약에 맞추는 crop pipeline은 이 저장소에서 작성했다. Pixel3DMM 공식 crop을 복사해 약간 수정한 것이 아니라, 공식 `static_crop` 경로가 독립 사진에 맞지 않아 별도 모듈로 교체한 것이다. affine crop 수학 자체는 일반적인 영상 기하 방식이며 독점적인 새 학습 모델은 아니다.

실험에서 사용하는 Facer commit은 다음으로 고정한다.

```text
FacePerceiver/facer@ddd35c76ff840174b8a5403ad1c1255e37b8782b
```

코드 라이선스와 pretrained weight 라이선스는 상용화 전에 별도로 다시 확인해야 한다.

## Why Pixel3DMM Upstream Crop Was Replaced

Pixel3DMM 공식 전처리의 `static_crop=True`는 동일한 피사체가 비슷한 frame 안에서 움직이는 영상에는 유용하지만, 서로 다른 독립 사진의 bbox 절대 좌표를 평균내면 잘못된 공통 crop이 만들어진다. 실제 8장 입력에서는 일부 얼굴이 잘려 눈 주변만 남았고, 이 잘못된 crop이 이후 FaRL 재검출·segmentation 실패의 상위 원인이 되었다.

Hair App crop은 사진마다 detector를 다시 실행하고 사진마다 별도의 affine transform을 만든다.

## V1 Result and Problems

파일:

- `experiments/milestone1_geometry_bakeoff/canonical_face_crop.py`
- `experiments/milestone1_geometry_bakeoff/canonical_crop_test_colab.ipynb`

8장 private-photo 시각 검사 결과:

- 모든 사진에서 눈·코·입·턱이 포함되어 upstream static crop보다 크게 개선됐다.
- 정면과 3/4 사진의 위치·크기 정규화는 usable했다.
- 약 24.6° 기울어진 정면 사진은 두 눈을 기준으로 정상적으로 roll이 제거됐다.
- 강한 profile에서는 RetinaFace가 가려진 눈을 코 근처에 추정했다. v1은 이를 실제 두 눈으로 믿어 약 -10.4°의 잘못된 roll을 적용했다.
- profile landmark가 불합리한데도 `warnings=[]`였으므로 v1 검사는 “주어진 점을 수평으로 만들었는가”만 확인하고 “그 점이 해부학적으로 믿을 만한가”는 확인하지 못했다.
- 원본 경계에 가까운 얼굴을 회전하면 검은 fill 영역이 생길 수 있다.
- 여러 얼굴이 검출돼도 detector confidence가 가장 큰 얼굴 하나만 골랐다. 작은 배경 얼굴을 선택할 가능성이 남아 있었다.
- bbox 기준만 사용해 pose에 따라 얼굴의 체감 크기와 세로 위치가 조금씩 달랐다.

v1 판정은 `bbox/scale PASS`, `frontal/three-quarter roll PASS`, `profile roll/warning gate FAIL`이다. 비교 기준으로 보존하며 삭제하지 않는다.

## Obstacles Are Not Crop Rejection Reasons

모자, 손가락, 휴대전화, 향수병, 헤드폰, 머리카락 같은 장애물은 실제 사용자 입력에서 흔하다. 이런 사진을 crop 단계에서 일괄 거절하면 제품 입력 조건이 비현실적으로 좁아진다.

현재 원칙:

1. 얼굴을 찾을 수 있으면 crop을 만든다.
2. detector/landmark/pose/padding 불확실성은 metadata warning으로 남긴다.
3. 뒤 segmentation에서 skin, hair, accessory, hand, phone, unknown occluder 등의 영역을 구분한다.
4. geometry loss와 UV bake에서 가려진 픽셀의 weight를 낮추거나 0으로 둔다.
5. 다른 사진에서 같은 얼굴 영역이 보이면 그 관측을 우선한다.
6. 모든 사진에서 가려진 영역만 추정 영역으로 남긴다.

따라서 obstacle detection과 segmentation은 crop을 대체하지 않고 crop 이후의 regional confidence를 만든다. 정확한 obstacle class와 segmentation 모델은 별도 A/B 후 결정한다.

## V2 Design

파일:

- `experiments/milestone1_geometry_bakeoff/canonical_face_crop_v2.py`
- `experiments/milestone1_geometry_bakeoff/test_canonical_face_crop_v2.py`
- `experiments/milestone1_geometry_bakeoff/canonical_crop_v2_test_colab.ipynb`

### 1. Five-Point Observation

v1은 두 눈만 저장했다. v2는 RetinaFace의 두 눈·코·두 입꼬리를 모두 저장한다. roll에 사용할 눈 좌표가 얼굴의 나머지 구조와 일치하는지 검사할 수 있다.

### 2. Roll Plausibility Gate

v2는 다음 proxy를 계산한다.

- eye span / bbox width;
- 코에서 왼쪽·오른쪽 눈까지 거리의 균형;
- eye line 아래에 코가 있는지;
- 코 아래에 입이 있는지;
- 5개 point가 확장 bbox 안에 있는지;
- eye line이 비현실적으로 45° 이상인지.

한 조건이라도 실패하면 사진을 버리지 않고 roll만 `0°`로 둔다.

```text
roll_skipped_unreliable_landmarks
profile_candidate
```

위 warning을 metadata에 남긴다. 이 규칙은 profile을 완벽하게 분류하는 모델이 아니라, 잘못된 두 눈으로 사진을 더 망치는 것을 막는 보수적인 gate다. threshold는 8장 결과에 대한 첫 가설이며 고정값이 아니다.

### 3. Multi-Face Primary Selection

v1의 최고 detector score만 사용하는 방식 대신 모든 후보를 보존하고 아래 실험 점수로 주 피사체를 선택한다.

```text
selection_score =
  0.65 * relative_face_area
  + 0.20 * detector_confidence
  + 0.15 * image_center_score
```

셀카에서는 가장 큰 얼굴을 우선하되 confidence와 중앙 위치가 close call을 보조한다. 후보가 둘 이상이면 `multiple_faces_detected`를 남긴다. 미래 앱에서는 scan session의 identity embedding이나 사용자가 선택한 얼굴을 사용해 이 heuristic을 대체할 수 있다.

### 4. Crop Scale and Vertical Context

v2 첫 A/B 기본값:

```text
output_size = 512
bbox_margin = 1.50
vertical_center_offset = -0.04 * bbox_height
```

v1의 `1.42`보다 여백을 조금 늘리고 crop 중심을 bbox 중심에서 약간 위로 이동해 forehead/hairline context와 회전 여유를 늘린다. 이 값이 Pixel3DMM normal/UV 추론에 실제로 더 좋은지는 아직 검증되지 않았다. v1과 동일 입력으로 비교해 필요하면 1.42로 되돌리거나 pose별 margin을 사용한다.

### 5. No Artificial Black Fill

회전된 crop이 원본 밖을 참조하면 필요한 가장자리만 reflect padding한다. 그러나 reflect 픽셀은 실제 관측이 아니므로 별도의 512×512 validity mask를 저장한다.

```text
white = real source pixel
black = reflected context pixel
```

검은 fill이 segmentation이나 network inference를 방해하는 것은 막되, reflect 픽셀이 실제 얼굴 증거로 UV나 geometry loss에 들어가지 않도록 한다.

### 6. Reversible Coordinates

v1과 마찬가지로 `source_to_crop`과 `crop_to_source` 3×3 행렬을 모두 저장한다. validity mask와 segmentation mask도 이 좌표 계약을 공유해야 한다.

## V2 Output Contract

```text
crop_test_512_v2/
  rgb/                 # Pixel3DMM adapter용 crop
  cropped/             # 같은 canonical crop
  crop_validity/       # 실제 원본 관측 여부, PNG mask
  crop_meta/
    00000.json
    ...
    manifest.json
```

주요 metadata:

- all 5 landmarks and selected bbox;
- all face candidate rankings;
- raw eye roll and actually applied roll;
- landmark plausibility metrics and failure reasons;
- profile candidate flag;
- reflected padding fraction;
- observed source fraction;
- bidirectional affine matrices;
- warnings.

## Verification Status

2026-06-23 local unit test:

- reliable frontal roll correction;
- profile-like fake-eye roll skip;
- transform reversibility;
- multi-face primary selection;
- reflected padding without artificial black fill;
- observed-source mask generation;
- invalid observation rejection.

기존 v1 3개와 v2 5개를 합쳐 총 8개 test가 통과했다. 이는 합성 좌표에 대한 코드 계약 검사이며 실제 8장 결과 품질을 증명하지 않는다.

## Immediate A/B Gate

다음 순서로 진행한다.

1. `canonical_crop_v2_test_colab.ipynb`를 같은 8장에 실행한다.
2. v1과 v2의 원본/crop을 나란히 비교한다.
3. 특히 기존 `00003`의 큰 roll이 계속 올바르게 보정되는지 확인한다.
4. 기존 profile `00006`, `00007`에서 roll이 생략되고 얼굴이 더 자연스러운지 확인한다.
5. 검은 fill이 없어지고 validity mask가 그 부분을 검게 표시하는지 확인한다.
6. 배경 인물이 있는 사진에서 주 피사체가 선택되는지 확인한다.
7. 얼굴·턱·이마·필요한 귀 coverage와 체감 크기를 비교한다.
8. v2가 이 gate를 통과한 뒤에만 Pixel3DMM safe notebook의 기본 crop을 v1에서 v2로 바꾼다.

## Failure and Revision Conditions

다음 중 하나가 보이면 v2를 고정하지 않고 수정한다.

- 정면/3/4 사진의 실제 roll 보정이 지나치게 자주 생략됨;
- profile인데 잘못된 eye roll이 계속 적용됨;
- margin 1.50 때문에 Pixel3DMM 얼굴 입력이 지나치게 작아짐;
- vertical offset 때문에 턱 또는 머리 위쪽이 더 많이 잘림;
- 크고 가까운 다른 사람이 주 사용자를 빼앗음;
- reflect 영역이 넓어 모델 입력을 왜곡함;
- warning은 많지만 downstream weight로 연결할 수 없음.

향후 대안은 MediaPipe pose/landmark를 roll verification에 추가하는 것, identity embedding으로 주 피사체를 연결하는 것, pose별 crop template을 사용하는 것이다. 다만 8/8 얼굴 검출에 성공한 RetinaFace를 바로 교체하기보다 v2 A/B에서 남는 실패를 먼저 측정한다.

## Decision Status

v2는 production 또는 Pixel3DMM 기본 전처리로 채택하지 않았다. v3 비교를 위해 보존한다.

## V3: Five-Point Constellation Roll

사용자 제안에 따라 눈선 하나가 아니라 아래 5점의 전체 배치를 roll 기준으로 사용하는 v3를 별도 구현했다.

```text
left eye       right eye
        nose tip
left mouth     right mouth
```

파일:

- `experiments/milestone1_geometry_bakeoff/canonical_face_crop_v3.py`
- `experiments/milestone1_geometry_bakeoff/test_canonical_face_crop_v3.py`
- `experiments/milestone1_geometry_bakeoff/canonical_crop_v3_test_colab.ipynb`

### V3 Mathematics

v3는 코끝을 중심 anchor로 둔다. 검출된 코끝에서 두 눈과 두 입꼬리로 향하는 4개 vector를 만들고, 이 vector들이 정방향 canonical 5점 template의 vector들과 가장 잘 겹치도록 least-squares similarity fit을 수행한다.

fit이 추정하는 값은 다음 두 개다.

- 하나의 공통 scale: roll 계산용으로만 사용하며 실제 얼굴 크기를 이 값으로 바꾸지 않는다.
- 하나의 공통 rotation: 사진 전체에 적용할 roll.

얼굴 점을 각각 따로 움직이거나 정면 얼굴처럼 warp하지 않는다. 따라서 yaw·pitch와 개인 얼굴 비율은 보존되고, 이미지 전체에 단 한 번의 rotation만 적용된다.

이 방식은 눈 한 점이 코 주변으로 잘못 검출돼도 다른 눈·코·입꼬리 관계가 회전 추정에 함께 참여한다. 코는 단순히 다섯 점의 평균에 포함되는 것이 아니라 네 개 상대 vector의 원점으로 직접 사용된다.

### Diagnostics

v3는 최종 5점 roll 외에 다음 개별 roll 단서도 metadata에 저장한다.

- eye line;
- mouth line;
- eye midpoint → nose tip vertical axis;
- nose tip → mouth midpoint vertical axis;
- eye midpoint → mouth midpoint vertical axis.

5점 template fit residual이 `0.30`보다 크면 `five_point_shape_mismatch`, 개별 축의 roll 범위가 `20°`보다 크면 `five_point_axis_disagreement`를 남긴다. 이 warning이 있어도 crop은 유지하고 5점 fit roll을 적용한다. 다만 fit이 `45°`를 넘으면 detector ordering 실패 가능성이 크다고 보고 회전만 생략한다.

threshold와 canonical template 비율은 첫 가설이며 개인의 얼굴형 정답으로 사용하지 않는다. 실제 8장 결과에서 바뀔 수 있다.

### What V3 Reuses From V2

v3의 실험 변수는 roll 계산뿐이다. 다음은 v2와 동일하다.

- Facer RetinaFace/MobileNet detector;
- 다중 얼굴 주 피사체 ranking;
- 512×512 출력;
- `bbox_margin=1.50`;
- `vertical_center_offset=-0.04`;
- reflect padding;
- observed-source validity mask;
- 원본↔crop affine metadata;
- 장애물 사진 보존과 warning 방식.

따라서 v2/v3 차이가 보이면 주로 two-eye plausibility gate와 five-point roll fit의 차이로 해석할 수 있다.

### Local Verification

v3 합성 단위 test 5개가 통과했다.

- 알려진 `27°` 5점 도형에서 `27°` roll 복원;
- 한쪽 눈을 의도적으로 틀리게 옮겼을 때 eye-only보다 실제 roll에 가까운 결과;
- yaw를 흉내 낸 가로 압축·코 이동에서도 roll 유지;
- crop/validity/양방향 행렬 계약 유지;
- `45°`를 넘는 극단 fit에서 사진은 유지하고 roll만 생략.

이는 합성 검증이며 실제 사진에서 v3가 v1/v2보다 낫다는 뜻은 아직 아니다.

### V3 Visual Gate

다음 즉시 단계는 같은 8장으로 `canonical_crop_v3_test_colab.ipynb`를 실행하는 것이다.

1. title의 `eye`와 `five` roll을 비교한다.
2. 기존 약 `24.6°` 정면 기울기가 v3에서도 자연스럽게 바로 서는지 확인한다.
3. 기존 profile 두 장에서 코 주변의 가짜 눈 하나가 전체 roll을 지배하지 않는지 확인한다.
4. 눈선과 입선이 서로 다른 각도일 때 얼굴 전체가 더 자연스럽게 보이는지 확인한다.
5. `fit residual`과 `axis disagreement` warning이 실제 이상 사례와 대응하는지 확인한다.
6. v2와 동일 margin·center·validity이므로 crop 크기 차이보다 얼굴 회전 차이에 집중한다.

실제 v3 crop-only 결과에서 RetinaFace 5점이 exact pupil center, nose tip, mouth corner가 아니라 근사 alignment point라는 한계가 확인됐다. 5점 fit 공식은 입력 점에 대해 정상 동작했지만 입력 landmark 자체가 부정확해 시각적인 roll 개선이 제한됐다.

이 결과만 보면 MediaPipe dense landmark나 robust loss로 roll을 계속 개선할 수 있다. 하지만 공식 Pixel3DMM code를 다시 확인한 결과 이 sparse 5점은 최종 fitting landmark가 아니며, crop 이후 PIPNet이 별도의 98점을 생성하고 tracker가 roll을 포함한 camera/head pose를 최적화한다. 공식 crop도 roll normalization을 하지 않는다.

따라서 v3 뒤의 현재 결정은 다음과 같다.

- persistent crop 단계에서는 per-image bbox·scale·translation만 정규화;
- 기본값은 no-roll;
- official PIPNet 98 landmark를 final crop에서 실행;
- MediaPipe는 우선 quality cross-check로 사용;
- optional roll은 no-roll Pixel3DMM end-to-end 결과가 실제로 실패할 때만 two-pass A/B.

상세 근거와 단계별 계약은 `docs/12_pixel3dmm_preprocessing_contract.md`를 따른다.
