# Pixel3DMM-Compatible Preprocessing Contract

Last synchronized: 2026-06-23
Status: V4 notebook implementation complete; private-photo Colab validation pending
Audited upstream: `SimonGiebenhain/pixel3dmm@fcd1fa973c7715b02a8948dfc679dff53cf85924`

## Why This Document Exists

Hair App의 첫 3D geometry baseline은 Pixel3DMM이다. 따라서 crop의 목표는 사람이 보기에 모든 얼굴을 똑바로 세우는 것이 아니라 다음을 만족하는 것이다.

1. 독립적으로 촬영된 여러 사진에서 얼굴을 안정적으로 포함한다.
2. Pixel3DMM normal/UV network가 기대하는 square face-crop 분포를 크게 바꾸지 않는다.
3. Pixel3DMM tracker가 사용할 landmark, segmentation, camera 좌표계가 서로 일치한다.
4. 원본 사진과 모든 derived artifact 사이의 좌표 변환을 보존한다.
5. 모자·손·휴대전화·헤드폰·머리카락 같은 실제 장애물을 버리지 않고 지역별 confidence로 처리한다.

초기 v1~v3 crop 실험은 RetinaFace가 제공하는 sparse 5-point alignment 좌표로 roll을 정규화했다. 실제 8장 v3 시각 결과에서 눈 점이 동공 중심이 아니라 눈 주변에 놓이고 코끝·입꼬리도 근사치임을 확인했다. 더 중요한 사실은 이 5점이 Pixel3DMM tracker가 사용하는 최종 landmark가 아니라는 점이다.

따라서 문제는 roll 공식만이 아니라 **잘못된 단계의 landmark를 사용해 공식 pipeline에 없는 추가 회전을 넣으려 한 구조**였다.

## Audited Official Sources

2026-06-23에 다음 official source를 확인했다.

- repository/README: <https://github.com/SimonGiebenhain/pixel3dmm/tree/fcd1fa973c7715b02a8948dfc679dff53cf85924>
- preprocessing order: <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/scripts/run_preprocessing.py>
- crop launcher: <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/scripts/run_cropping.py>
- FaceBoxes crop and PIPNet landmark code: <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/src/pixel3dmm/preprocessing/pipnet_utils.py>
- FaRL segmentation: <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/scripts/run_facer_segmentation.py>
- normal/UV inference: <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/scripts/network_inference.py>
- tracker landmark consumption: <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/src/pixel3dmm/tracking/tracker.py>
- landmark/loss configuration: <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/configs/tracking.yaml>

모든 판단은 README 예시가 아니라 이 실제 코드 경로를 기준으로 한다.

## Official Pixel3DMM Order

공식 README는 preprocessing이 cropping, facial landmark detection, segmentation, MICA를 수행한다고 설명한다. 실제 코드는 다음 순서다.

```text
source image/video
  -> unpack into rgb/
  -> FaceBoxes face detection
  -> square face crop, resized to 512x512
  -> FaceBoxes re-detection inside saved crop
  -> temporary PIPNet ROI resize
  -> PIPNet WFLW 98 landmarks mapped back to saved 512 crop
  -> optional MICA/ArcFace identity prior
  -> RetinaFace re-detection on saved crop
  -> FaRL face segmentation
  -> Pixel3DMM normal prediction
  -> Pixel3DMM UV-map prediction
  -> FLAME tracking using crops, segmentation, normal/UV and PIPNet landmarks
```

Pixel3DMM network inference는 `cropped/`의 square image를 512×512로 읽고 `seg_og/` mask를 함께 사용한다. tracker는 `PIPnet_landmarks/*.npy`의 98점을 읽어 WFLW-to-68 mapping을 적용하고, index 96/97을 left/right iris point로 사용한다.

따라서 Pixel3DMM의 실제 fitting landmark는 crop 이후 PIPNet이 만든 98점이다.

## Three Different Landmark Roles

현재 혼동을 막기 위해 landmark를 세 종류로 분리한다.

### A. Crop Detection Landmarks

목적:

- 얼굴 후보와 bbox를 찾기;
- 주 피사체 선택 보조;
- crop coverage 검사.

v1~v3에서 사용한 Facer RetinaFace 5점은 여기에 해당한다. 이 점은 exact pupil detector가 아니라 sparse alignment point다. Pixel3DMM tracker의 최종 fitting point가 아니다.

최종 baseline에서는 bbox가 안정적이면 sparse 5점을 roll source로 사용하지 않는다.

### B. PIPNet 98 Fitting Landmarks

목적:

- crop 안에서 얼굴의 세부 landmark 추정;
- tracker의 eye, eyelid, iris/pupil, 선택적 mouth landmark loss;
- camera/head pose와 FLAME parameter fitting 보조.

이 landmark는 **첫 persistent crop 이후** 검출한다. 공식 tracker가 기대하는 topology와 index이므로 첫 baseline에서 임의로 MediaPipe 478점으로 교체하지 않는다.

### C. FLAME Projected 3D Landmarks

목적:

- 현재 FLAME mesh와 camera를 image plane에 투영;
- PIPNet 2D landmark와 비교해 fitting error 계산.

tracker가 최적화하면서 B와 C 사이의 오차를 줄인다. 사진의 roll은 camera/head rotation parameter가 설명할 수 있는 관측값이다.

## Why There Appears to Be a Second Crop

공식 `pipnet_utils.py`에는 두 번의 detection/ROI 처리가 있다.

1. 첫 번째는 원본에서 저장할 512×512 `cropped/` image를 만드는 persistent crop이다.
2. 두 번째는 이미 저장된 crop 안에서 PIPNet이 얼굴 영역을 다시 찾고 자신의 network input 크기로 임시 resize하는 내부 ROI다.

두 번째 ROI는 최종 crop 파일을 다시 덮어쓰는 것이 아니다. PIPNet output을 다시 512 crop 좌표로 환산해 `PIPnet_landmarks`에 저장한다. landmark network가 안정적으로 작동하기 위한 내부 입력 정규화다.

FaRL도 segmentation 전에 RetinaFace를 다시 실행한다. 이것은 PIPNet ROI와 또 다른 단계이며, parser에 face box를 제공하기 위해서다. 이전 FaRL 빈 검출은 이 단계에서 발생했다.

즉, 중복처럼 보이는 동작은 각각 목적이 다르다.

```text
persistent bbox crop        -> Pixel3DMM의 공통 image 좌표계 생성
temporary PIPNet ROI        -> 98-point landmark network 입력
FaRL face detection/warp    -> segmentation parser 입력
```

## Root Cause of the First Crop Failure

공식 `run_cropping.py`는 `static_crop=True`를 사용한다. `pipnet_utils.py`는 모든 frame의 FaceBoxes bbox 절대 픽셀 좌표를 평균내고 같은 bbox를 재사용한다.

이 방식은 같은 해상도·구도의 연속 video에는 유용하지만, 해상도와 얼굴 위치가 서로 다른 독립 사진 폴더에는 맞지 않는다. 실제 8장에서는 일부 crop에 눈만 남고 코·입·턱이 잘렸다. 이 잘못된 crop이 이후 PIPNet/FaRL 실패를 유발할 수 있다.

따라서 수정해야 할 핵심은 **roll이 아니라 static shared bbox**다.

## Final Default Decision: Per-Image BBox, No Roll

Hair App의 첫 Pixel3DMM-compatible baseline은 다음으로 결정한다.

```text
EXIF-oriented raw photo
  -> official FaceBoxes bbox per photo
  -> choose intended primary face
  -> square bbox using official-compatible 1.42 margin
  -> shift square inside source bounds when possible
  -> resize once to 512x512
  -> DO NOT normalize roll
  -> store source<->crop affine metadata
```

### Why FaceBoxes

현재 RetinaFace bbox도 8장 시각 검사에서는 usable했다. 그러나 첫 baseline의 목표는 detector bake-off가 아니라 Pixel3DMM 재현이다. 공식 FaceBoxes와 `get_cstm_crop`의 scale convention을 유지하고 static averaging만 per-image로 바꾸면 training/inference preprocessing 분포에서 벗어나는 변수를 최소화할 수 있다.

FaceBoxes가 실제 obstacle stress set에서 실패하면 같은 contract 아래 RetinaFace/SCRFD 후보를 A/B한다. detector 선택은 영구 고정이 아니다.

### Why No Roll

- 공식 preprocessing은 bbox를 square crop하지만 image-plane roll을 제거하지 않는다.
- Pixel3DMM tracker는 per-frame head/camera rotation을 직접 최적화한다.
- PIPNet 98 landmarks가 crop 이후 실제 fitting landmark로 사용된다.
- sparse RetinaFace 5점의 오차로 사진 전체를 잘못 회전시키는 위험이 사라진다.
- 회전 padding과 synthetic boundary가 줄어든다.
- Pixel3DMM normal/UV network가 학습·공식 inference에서 본 crop convention에 더 가깝다.

사람이 보기에 똑바로 선 crop이 반드시 3D 결과가 더 좋은 것은 아니다. 이 단계의 성공 기준은 crop 미관이 아니라 downstream normal/UV/tracking 품질이다.

### Source Boundary Handling

기본값은 official code처럼 crop square를 image 안쪽으로 shift해 검은 padding을 만들지 않는 것이다. crop side가 source보다 커서 shift만으로 해결할 수 없는 예외에만 reflect padding을 허용하고, 해당 영역은 `observed_source_mask=0`으로 기록한다.

## Planned Hair App Preprocessing Flow

```text
0. Raw input preservation
   - original bytes, EXIF, source ID

1. Per-image persistent crop
   - FaceBoxes detections
   - primary face selection
   - square 1.42-margin bbox
   - no roll
   - 512 crop + affine + validity metadata

2. Official PIPNet 98 landmarks on final crop
   - internal temporary ROI is allowed
   - output mapped to 512 crop coordinates
   - overlay and confidence saved

3. Landmark quality gate
   - count/output check
   - face topology/order plausibility
   - iris/eye/mouth/oval visibility checks
   - unreliable points are masked, not silently trusted

4. Segmentation on the same final crop
   - FaRL official path first
   - zero-face fallback using known centered crop/direct parser path
   - mask visual check and output-count gate
   - later add general obstacle/unknown mask

5. Pixel3DMM inference
   - cropped RGB + segmentation
   - normal and UV map count/size validation

6. FLAME tracking
   - PIPNet landmarks + iris
   - segmentation/silhouette
   - Pixel3DMM normal/UV
   - per-image camera/head pose including original roll

7. Reconstruction validation
   - reproject mesh/landmarks/masks to every crop
   - compare observed regions and record per-view error
```

## PIPNet Confidence Improvement

공식 code는 crop 안의 FaceBoxes detection score가 `0.99`보다 낮으면 해당 frame의 PIPNet landmark를 저장하지 않는다. V4 notebook은 missing output을 줄이기 위해 이 값을 `0.75`로 낮추되 output-count와 visual gate를 강제한다. 낮은 face-detection score가 곧 landmark confidence인 것은 아니다.

최종 구현에서는 단순 threshold 하향만으로 끝내지 않는다.

- FaceBoxes detection score를 저장한다.
- PIPNet의 per-landmark heatmap/class confidence를 가능하면 저장한다.
- 98점 overlay를 crop과 함께 저장한다.
- out-of-frame, 뒤집힌 topology, 비현실적인 iris/eye/mouth 배치를 검사한다.
- tracker에 넣지 않을 point는 좌표를 0으로 만들거나 명시적 mask로 전달한다.
- frame 전체를 거절하기보다 region/point 단위로 confidence를 낮춘다.

PIPNet confidence를 tracker loss에 연속 weight로 연결하는 것은 baseline 재현 이후의 별도 수정이다. 첫 실행에서는 official binary landmark mask와 시각 gate를 우선한다.

## Role of MediaPipe After This Decision

MediaPipe는 폐기하지 않는다. 다만 기본 Pixel3DMM fitting landmark를 즉시 대체하지 않는다.

첫 역할:

- live capture guidance;
- roll/yaw/pitch quality report;
- face coverage와 blur/stability 검사;
- PIPNet 결과와 독립적인 landmark sanity check;
- obstacle/visibility metadata 보조.

MediaPipe 478점과 PIPNet WFLW 98점은 topology와 semantic index가 다르다. MediaPipe 좌표를 tracker에 바로 넣으면 WFLW-to-68 mapping, iris index 96/97, eye/mouth loss가 깨진다. 대체하려면 explicit mapping, visibility mask, 동일 입력 A/B가 필요하다.

따라서 첫 baseline에서는 다음을 금지한다.

- MediaPipe landmark를 PIPNet `.npy` 형식으로 이름만 바꿔 저장하기;
- MediaPipe로 roll한 뒤 PIPNet/segmentation 좌표를 이전 crop 기준으로 사용하기;
- source, crop, landmark, segmentation 사이 transform을 섞기.

## Optional Roll Normalization: Only After Downstream Failure

no-roll baseline에서 큰 roll 사진의 normal/UV 또는 tracking 품질이 실제로 낮다는 증거가 생기면 그때 optional two-pass branch를 비교한다.

```text
raw image
  -> per-image no-roll bbox crop
  -> PIPNet 98 + optional MediaPipe dense landmarks
  -> confidence-aware robust roll estimate
  -> if confidence is high, create final rotated crop from raw once
  -> rerun PIPNet and segmentation on the final crop
  -> run Pixel3DMM inference/tracking
```

중요 조건:

- 임시 crop을 여러 번 JPEG로 재저장하지 않는다.
- 최종 rotated crop은 raw에서 한 번만 resample한다.
- PIPNet과 segmentation은 최종 crop에서 반드시 다시 계산한다.
- hidden eye를 실제 관측처럼 사용하지 않는다.
- roll 적용 여부를 metadata에 기록한다.
- 선택 기준은 crop이 똑바로 보이는지가 아니라 3D reconstruction error다.

이 branch는 default가 아니다.

## Segmentation and Obstacles

장애물 사진은 정상적인 사용자 입력이다. crop 단계에서 삭제하지 않는다.

Pixel3DMM의 FaRL segmentation은 face classes 중심이며 hand, phone, headphone 등의 모든 장애물을 완벽히 분류한다고 가정할 수 없다. 최종 구조는 다음 mask를 분리한다.

- face-part semantic mask;
- hair mask;
- known accessory/hand/object mask;
- unknown/low-confidence occlusion mask;
- observed-source validity mask.

Pixel3DMM baseline은 우선 official FaRL mask로 재현한다. 그 다음 obstacle stress set에서 잘못 skin으로 분류되는 픽셀을 수집해 general human/object segmentation 또는 Hair App 전용 occlusion module을 추가한다.

가려진 pixel은 geometry/UV loss weight를 낮추지만 사진 전체를 버리지는 않는다. 다른 view에서 같은 얼굴 region이 보이면 그 관측을 우선한다.

## Artifact and Coordinate Contract

```text
preprocessed/{set_id}/
  raw_manifest.json
  rgb/                       # oriented raw-derived frames
  cropped/                   # final 512 no-roll crops
  crop_meta/                 # one JSON per image
  crop_validity/             # real source vs fallback padding
  PIPnet_landmarks/          # official 98-point normalized coords
  PIPnet_landmark_meta/      # detector/confidence/QC
  PIPnet_annotated_images/   # visual gate
  seg_og/                    # segmentation labels
  seg_non_crop_annotations/  # visual gate
  p3dmm/normals/
  p3dmm/uv_map/
```

각 `crop_meta/{frame}.json`은 최소 다음을 가진다.

- source ID and oriented source size;
- detector/model/version;
- all candidate boxes and selected face;
- square bbox and margin;
- source-to-crop and crop-to-source transform;
- padding/validity information;
- `roll_applied=false` for the default baseline;
- warnings and parent artifact IDs.

공식 code의 단일 `crop_ymin_ymax_xmin_xmax.npy`는 independent multi-photo provenance에 부족하므로 호환용으로만 만들고 Hair App source of truth로 사용하지 않는다.

## Validation Gates

### Gate A: Persistent Crop

- 모든 입력에 올바른 주 피사체 선택;
- 눈·코·입·턱·필요한 이마/귀 coverage;
- crop 안 face occupancy가 official convention과 크게 다르지 않음;
- raw↔crop matrix round-trip 오차 허용범위 이내;
- 사진별 crop metadata 존재.

### Gate B: PIPNet Landmark

- crop 수와 98-point `.npy` 수가 같음;
- annotated overlay에서 눈·iris·코·입·윤곽이 해부학적으로 타당;
- profile/occlusion에서 hidden point와 low-confidence point 표시;
- 좌표가 같은 final crop 기준임.

### Gate C: Segmentation

- crop과 `seg_og` 수가 같음;
- face/ears/hair/background가 시각적으로 타당;
- 장애물이 skin/ear로 잘못 포함된 영역 기록;
- 빈 mask 또는 전체 mask 금지.

### Gate D: Pixel3DMM Network

- crop마다 normal과 UV output 존재;
- output size/format 정상;
- normal/UV overlay가 얼굴 위치와 일치;
- 예외를 삼키고 누락된 output이 없는지 count 확인.

### Gate E: Tracking

- 모든 accepted view가 camera/head pose를 얻음;
- landmark reprojection, silhouette, normal, UV error 기록;
- shared identity가 view별로 붕괴하지 않음;
- obstacle region이 geometry를 끌어당기는 실패 기록;
- neutral render/turntable로 최종 identity와 geometry 평가.

전처리 후보 선택은 Gate A의 시각적 uprightness가 아니라 Gate B~E까지의 결과로 결정한다.

## Implementation Status and Order

`experiments/milestone1_geometry_bakeoff/pixel3dmm_colab_v4.ipynb`에 다음이 구현됐다.

1. v1~v3 roll experiment는 historical로 보존하고 V4 기본 경로에서 제외했다.
2. official FaceBoxes와 1.42 margin을 유지한 per-image no-roll 512 crop을 구현했다.
3. 모든 face candidate ranking, 선택된 bbox, 양방향 affine, warning을 사진별 JSON과 manifest에 저장한다.
4. final crop을 덮어쓰지 않고 official PIPNet WFLW 98점을 실행한다.
5. crop/PIPNet overlay/FaRL mask의 개수와 파일 크기를 검사하고 3열 visual gate를 표시한다.
6. 사용자가 `PREPROCESSING_APPROVED=True`로 명시 승인하기 전 normal/UV와 tracking으로 진행하지 않는다.
7. 승인 뒤 official normal/UV inference, output-count gate, multi-image FLAME tracking, mesh preview, Drive manifest 저장까지 같은 notebook에 포함했다.
8. 실제 FLAME 배포 구조에 맞춰 generic model, FLAME2023, Vertex Masks를 찾는다. 세 FLAME ZIP에 없는 `landmark_embedding.npy`는 DECA pinned commit의 호환 파일을 내려받아 SHA-256과 required key를 검증한다.

아직 완료로 간주하지 않는 다음 순서는 다음과 같다.

1. 같은 private 8장으로 V4 crop, PIPNet 98점, FaRL mask visual gate를 실행한다.
2. FaRL zero-face가 재발하면 원인을 기록하고 검증된 fallback을 추가한다. 현재 V4는 누락을 조용히 통과시키지 않고 count gate에서 중단한다.
3. visual gate 통과 뒤 normal/UV inference와 FLAME tracking을 실제로 완료한다.
4. no-roll 결과의 reprojection/reconstruction error를 기록한다.
5. 큰-roll view만 optional two-pass normalization과 비교할지 결정한다.

### First V4 Live Crop Result (2026-06-23)

- private 8장 모두 per-image no-roll crop 파일 생성 성공;
- `00000`, `00007`: multiple-face warning;
- `00007`: FaceBoxes confidence `0.716`, low-confidence warning;
- 따라서 Gate A의 output completeness는 통과했지만 primary-face selection과 coverage visual approval은 아직 보류;
- 다음 실행은 `7.1 원본/crop 시각 gate`이며 그 전에는 PIPNet/FaRL로 진행하지 않는다.
- 실제 Gate A visual 결과는 7/8 정상, `00007` 실패였다. FaceBoxes가 실제 profile 얼굴 후보를 검출했지만 custom area-heavy ranking이 더 큰 가슴/목 false positive를 선택했다.
- 이는 crop/no-roll geometry가 아니라 primary-face selection 실패다. 현재 `0.70 area + 0.20 confidence + 0.10 centrality` 가설은 폐기 후보이며, candidate confidence와 second-detector/PIPNet face-validity를 확인한 뒤 수정한다.
- candidate metadata는 실제 얼굴 confidence `0.9352` 대 false-positive confidence `0.7161`로 detector 자체의 판정은 올바랐음을 보였다. 따라서 area-heavy selection은 폐기하고 official FaceBoxes confidence-first를 V4 baseline으로 사용한다. area/center는 선택값이 아니라 diagnostics로 보존한다.
- confidence-first live 재실행은 8/8 생성에 성공했고 `00007`이 confidence `0.935`인 실제 얼굴 후보를 선택했다. Gate A는 마지막 crop 시각 재확인 뒤 확정한다.
- 마지막 시각 재검사에서 `00007`의 실제 profile 얼굴 선택, 얼굴 coverage, no-roll 보존을 확인했다. 전체 8장 Gate A PASS. 다음은 Gate B(PIPNet 98)와 Gate C(FaRL)다.
- 첫 Gate B/C 실행에서 PIPNet 98 landmark는 8/8 export 성공했다. FaRL은 617MB JIT weight 다운로드가 361MB에서 연결 종료돼 inference 전에 중단됐다. 이는 Gate C 품질 실패가 아니라 dependency fetch 실패이며, retry/resume 다운로드와 JIT load 검증 뒤 Gate C를 재개한다.
- weight 복구 후 Gate B/C count는 input/crop/meta/landmark/annotated/seg 모두 8/8 PASS. 첫 두 visual overlay에서 landmark와 segmentation 좌표 정렬 및 주요 얼굴 부위가 타당했다. 최종 visual PASS는 `00006/00007` profile/occlusion 확인 뒤 확정한다.
- 첫 Gate D normal inference는 PyTorch 2.6+ `weights_only=True` default가 official Lightning checkpoint의 OmegaConf object를 차단해 시작 전 실패했다. official notebook 경로로 받은 trusted Pixel3DMM checkpoint에만 `load_from_checkpoint(..., weights_only=False)`를 명시하고 재실행한다.

## Decision and Change Conditions

현재 default decision은 **per-image bbox + no roll + official PIPNet landmarks**다.

다음 증거가 생길 때만 바꾼다.

- no-roll 큰 각도 사진에서 Pixel3DMM normal/UV가 반복적으로 실패함;
- tracker가 roll 때문에 camera initialization에 반복적으로 실패함;
- PIPNet 98점이 obstacle/profile에서 지속적으로 부정확함;
- FaceBoxes bbox가 현실적인 입력에서 RetinaFace/SCRFD보다 명확히 낮은 성공률을 보임;
- optional roll branch가 동일 입력에서 Gate D/E error와 최종 3D 품질을 일관되게 개선함.

v1~v3의 RetinaFace 5-point roll은 연구 기록으로 남기지만 기본 후보에서는 제외한다. 이는 아이디어가 잘못돼서가 아니라, 실제 Pixel3DMM pipeline에서 더 정확한 fitting landmark가 뒤 단계에 따로 있고 camera/head roll 자체도 tracker가 추정하기 때문이다.
