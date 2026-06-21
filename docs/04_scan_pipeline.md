# Scan Pipeline

Last synchronized: 2026-06-21
Status: current capture implementation and proposed 3D extension

## Current Implemented Pipeline

현재 frontend scan은 MediaPipe Face Landmarker로 live camera frame을 분석하고, quality check를 통과한 frame과 landmark를 자동 수집해 backend로 보낸다.

### Current Steps

1. `front`
2. `left`
3. `right`
4. `hairline`

각 step은 accepted sample `20`개를 목표로 한다.

```text
progress = samples_collected / 20 * 100
```

사용자는 manual shutter를 누르지 않는다.

### Front

현재 목적:

- primary 2D face proportions;
- centerline and jaw/cheek anchors;
- representative preview;
- front-facing quality baseline.

### Left and Right

현재 목적:

- side-profile cues;
- yaw consistency;
- left/right asymmetry proxy;
- profile frame candidates.

### Hairline

현재 목적:

- forehead/hairline visibility;
- approximate guide points;
- temple and brow anchors;
- later mask/control preparation.

현재 hairline step이 실제 scalp segmentation 또는 full head scan을 수행하는 것은 아니다.

## Current Sample Data

Accepted sample은 다음을 포함한다.

- `id`
- `capturedAt`
- `scanStep`
- `imageDataUrl` during upload
- compact MediaPipe landmarks
- selected key points
- bounding box
- quality metrics
- pose proxy
- facial transformation matrix when available

Backend는 `imageDataUrl`을 실제 image file로 저장하고 JSON에서는 다음으로 바꾼다.

- `image_path`
- `image_url`

## Current Bundle and Storage

```text
{
  scanSessionId,
  completedAt,
  steps: {
    front: { status, progress, samples },
    left: { status, progress, samples },
    right: { status, progress, samples },
    hairline: { status, progress, samples }
  }
}
```

```text
backend/storage/scans/{scan_id}/
  metadata.json
  base_profile.json
  front/
    front_001.jpg
    front_001.json
  left/
  right/
  hairline/
```

`backend/storage/`는 local runtime data이며 git에 넣지 않는다.

## Proposed 3D Capture Extension

3D pipeline은 현재 4-step data를 재사용하되, 다음 입력을 추가로 요구할 가능성이 높다.

### Existing Selfies

- 사용자 selfie 5장 이상 권장.
- front, left/right three-quarter, left/right profile를 우선.
- rear/high-angle head view는 scalp와 ear 주변 개선을 위해 optional로 실험.
- beauty filter, portrait warp, severe wide-angle distortion을 감지·경고.
- 원본 file을 보존하고 model용 crop을 derived asset으로 저장.

### Star Selection

- user가 identity와 quality가 좋다고 생각하는 1~2장 선택.
- star는 metadata로 저장.
- central face texture에서 moderate bonus.
- regional visibility가 star보다 우선.
- geometry에서 star bonus는 더 약하게 시작하고 test로 조정.

### Pulled-Back-Hair Scan

사용자에게 다음을 안내한다.

- hair를 가능한 한 뒤로 넘기기;
- natural front hairline과 temples 노출;
- forehead, ears 주변이 가리지 않게 하기;
- neutral expression 유지;
- head를 천천히 회전;
- even lighting 유지.

이 scan이 개선할 수 있는 것:

- front hairline curve;
- temple shape;
- forehead-to-scalp transition;
- visible side scalp and ear context.

이 scan으로도 직접 알 수 없는 것:

- 계속 hair에 가린 crown/rear scalp;
- 정확한 skull 내부 geometry;
- thick hair 아래의 모든 surface.

가려진 부분은 model prior와 depth evidence로 추정하고 confidence를 낮게 표시해야 한다.

## Planned Quality Report

각 image/frame에 다음 score를 저장하는 방향을 검토한다.

- detection confidence;
- landmark confidence;
- pose and coverage class;
- sharpness and blur;
- exposure and clipping;
- white-balance confidence;
- occlusion classes;
- expression neutrality;
- hairline visibility;
- skin-region visibility;
- duplicate similarity;
- automatic quality score;
- user star flag;
- accepted/rejected reason.

정확한 schema와 threshold는 Pixel3DMM/VGGT/UV bake-off 결과를 본 뒤 versioning한다.

## Planned Geometry and UV Use

- geometry는 여러 view를 shared identity로 사용.
- camera estimation은 Pixel3DMM 내부 fitting과 optional VGGT를 비교.
- UV baker는 per-triangle visibility와 source camera를 사용.
- star, quality, angle, segmentation을 texel별 weight로 변환.
- raw image와 derived mask/crop/camera를 함께 추적.
- reconstruction report는 어떤 photo가 어느 region에 기여했는지 기록.

## Privacy

얼굴 사진, landmarks, 3D mesh, texture는 biometric-sensitive data다.

- git 또는 public experiment artifact에 넣지 않는다.
- product inference와 training opt-in을 분리한다.
- 삭제 요청이 raw와 모든 derived artifact에 전파되어야 한다.
- production 전에 encryption, access log, retention policy를 설계한다.

## Change Policy

Capture step 수, sample 20개, star 개수, required views는 고정값이 아니다. 첫 geometry/UV 실험에서 정보 기여도를 측정한 뒤 줄이거나 늘릴 수 있다. 사용자 부담과 품질의 trade-off를 실제 recapture rate와 결과 품질로 판단한다.
