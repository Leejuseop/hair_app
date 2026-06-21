# Personal Base Model Design

Last synchronized: 2026-06-21
Status: current `base_profile.json` plus future versioned 3D personal asset design

## Terminology

이 문서에서 혼동을 피하기 위해:

- **Current base profile:** 현재 구현된 `base_profile.json` version `0.1`.
- **3D personal head:** 미래에 생성할 editable hairless mesh와 cameras/parameters.
- **Face appearance:** user photos에서 만든 UV/material maps.
- **Personal base asset:** 3D head + face appearance + hairline/confidence/manifest. Hairstyle은 포함하지 않는다.

현재 base profile은 3D model이 아니다.

## Current Implementation

`ai_engine/base_profile.py`:

```python
build_base_profile(scan_record)
```

Backend가 scan bundle 저장 후 호출하며 결과는 다음에 저장한다.

```text
backend/storage/scans/{scan_id}/base_profile.json
```

### Current Inputs

- `scan_id`
- client scan session ID
- upload timestamp
- scan step data
- stored frame URLs
- compact MediaPipe landmarks
- selected key points
- quality metrics
- pose proxies

### Current Output

- `scan_id`
- `version`
- `status`
- `assets`
- `raw_landmark_samples`
- `derived_metrics`
- `synthesis_anchors`
- `preview`

### Current Assets

- `best_front_image`
- `best_left_image`
- `best_right_image`
- `best_hairline_image`

각 asset은 sample ID, path, URL, quality score를 가진다.

### Raw Landmark Samples

원본에 가까운 per-sample landmarks, key points, pose, quality를 보존한다. Summary metric이 raw evidence를 대체하면 안 된다.

### Derived Metrics and Anchors

현재 metric은 face width/height/ratio, jaw proxy, forehead/hairline visibility, side profile, symmetry 등이다. Anchor는 centerline, approximate hairline, jaw, temples를 포함한다.

이 값은 현재 2D preview와 future preprocessing에 유용하지만 고정밀 3D geometry truth로 취급하지 않는다.

## Future Personal Base Asset

3D pipeline이 구현되면 `base_profile.json`을 무리하게 거대한 binary container로 만들지 않는다. JSON은 manifest와 metadata를 가리키고 mesh, texture, confidence map은 별도 versioned files로 둔다.

예상 구조:

```text
backend/storage/users/{user_id}/personal_heads/{head_id}/
  manifest.json
  accepted_inputs.json
  cameras.json
  flame_params.npz
  head_mesh.glb
  head_mesh.obj                 # research export, optional
  hairline.json
  geometry_confidence.npy
  base_color.png
  observed_base_color.png
  uv_coverage.png
  uv_confidence.npy
  normal.png                    # optional later
  roughness.png                 # optional later
  material.json
  reconstruction_report.json
  previews/
```

실제 path와 schema는 구현 전까지 확정이 아니다.

## Planned Manifest

`manifest.json`은 최소한 다음을 추적해야 한다.

- artifact and schema version;
- source scan ID와 source photo IDs;
- user star selections;
- accepted/rejected images and reasons;
- code commit and pipeline version;
- model/weight versions and licenses;
- Pixel3DMM/KaoLRM/VGGT config;
- head topology and UV topology version;
- output file hashes;
- parent artifact IDs;
- geometry/texture confidence summary;
- observed/generated region ratio;
- runtime, GPU, warnings, failures;
- created/updated/deletion timestamps.

## Head Geometry Contract

첫 contract 가설:

- editable triangle mesh;
- stable FLAME-compatible or explicitly mapped topology;
- consistent world units and coordinate axes;
- UV coordinates;
- named regions: face, scalp, ears, neck, eyes boundaries;
- camera transforms for every accepted input;
- hairline curve in mesh/scalp coordinates;
- per-vertex or per-surface confidence;
- neutral expression version separated from source expressions.

Pixel3DMM 결과가 이 contract를 완전히 만족하지 않으면 conversion layer를 만든다. 특정 모델의 internal tensor를 앱 전체에서 직접 참조하지 않는다.

## Face Texture Contract

- unmodified or minimally normalized observed texture layer;
- render-ready base color;
- observed coverage mask;
- confidence map;
- generated/completed region mask;
- color-space and resolution metadata;
- source-photo contribution metadata;
- optional normal, roughness, specular maps.

AI completion이 observed pixels를 몰래 덮어쓰지 않도록 layer와 mask를 분리한다.

## Hairline Contract

Hairline은 단순 2D landmark proxy보다 풍부해야 한다.

- 3D curve on scalp;
- per-point confidence;
- source image visibility;
- temple anchors;
- left/right asymmetry;
- observed versus inferred segments;
- optional user correction history.

Hair fitting은 이 curve를 hard constraint가 아니라 style-aware constraint로 사용한다. 앞머리가 hairline을 덮는 style도 있기 때문이다.

## Confidence and Uncertainty

Personal base asset은 결과만 저장하지 말고 uncertainty를 저장해야 한다.

- photographed and strongly constrained face region;
- pulled-back scan에서 visible한 scalp/hairline;
- multi-view but weakly constrained region;
- model-prior-only crown/rear scalp;
- direct observed UV;
- blended UV;
- generatively completed UV.

이 정보는 recapture, model training, user warning, fitting weight에 재사용한다.

## Reuse Principle

Personal base asset은 hairstyle과 독립적이어야 한다.

- user가 다른 style을 시도할 때 head/UV를 재생성하지 않는다.
- geometry 또는 texture model이 개선되면 새로운 `head_id` version을 만든다.
- old hairstyle fits가 어느 head version을 사용했는지 추적한다.
- full reconstruction이 실패해도 raw scan과 current base profile을 보존한다.

## Evolution Plan

Possible versions:

- `0.1`: current structured 2D base profile.
- `0.2`: multi-selfie metadata, star flags, enhanced quality/segmentation.
- `0.3`: first research head mesh and cameras.
- `0.4`: direct observed UV and coverage/confidence.
- `1.0`: validated reusable personal head contract used by the app.

Version numbering is illustrative and can change. Schema changes must be documented and old artifacts must not be silently interpreted as new ones.
