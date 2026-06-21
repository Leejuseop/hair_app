# Hair App New-Chat Handoff

Last synchronized: 2026-06-21
Current architecture source of truth: `docs/10_3d_hair_app_master_plan.md`

이 파일은 새 대화용 compact handoff다. 상세 내용은 연결된 문서를 읽고, 실제 코드는 항상 `git status`와 repository를 기준으로 확인한다.

## First Actions

1. `git status --short --branch` 실행.
2. 사용자 또는 다른 agent의 local change를 버리지 않기.
3. `AGENTS.md` 읽기.
4. 3D 방향이 관련되면 `docs/10_3d_hair_app_master_plan.md` 읽기.
5. commit/push는 사용자가 명시적으로 요청할 때만 하기.

## Repository

- GitHub: <https://github.com/Leejuseop/hair_app>
- Default branch: `main`
- 현재 문서 동기화 직전 원격 최신 commit: `6ef4286 docs: record FLUX.2 klein base-9B tuning decision and sync docs`
- 이 handoff 갱신 작업의 실제 commit 여부는 `git log -1 --oneline`과 `git status`로 재확인할 것.

## Product Goal

Hair App은 여러 사용자 사진과 가이드 스캔으로 편집 가능한 개인 3D 머리를 만들고, 원하는 헤어스타일 사진에서 독립된 3D 머리카락을 복원해 사용자 두상에 맞춰 보여주는 모바일 웹 프로젝트다.

```text
사용자 사진 여러 장 + 머리를 넘긴 헤어라인/두상 스캔
  -> 민머리 3D head mesh
  -> 다중 사진 face UV texture
  -> textured personal head

헤어스타일 참고 사진
  -> 3D strand hair

personal head + strand hair
  -> retargeting + collision correction
  -> rotatable GLB + optional high-quality renders
```

모든 모델 선택은 작업 가설이다. 동일한 Hair App 입력으로 비교한 결과에 따라 바꾼다.

## Current Implementation

### Frontend

- React 18 + Vite.
- `getUserMedia` 카메라.
- MediaPipe Face Landmarker `VIDEO` mode, one face.
- scan order: `front`, `left`, `right`, `hairline`.
- 단계별 20개 accepted sample 자동 수집.
- detection, face size, centering, brightness, sharpness, yaw, roll, stability 검사.
- 완료 후 `POST /api/scan` upload.
- base profile image/landmark/hairline preview.
- hairstyle file input은 있으나 persistence와 실제 generation은 placeholder.

### Backend

- FastAPI `backend/main.py`.
- 실제 route:
  - `POST /api/scan`
  - `GET /api/scan/{scan_id}`
  - `GET /api/base-profile/{scan_id}`
- placeholder route:
  - `POST /api/style-reference`
  - `POST /api/generate`
  - `GET /api/result/{result_id}`
- local file storage: `backend/storage/scans/{scan_id}/`.
- database 없음.

### AI Engine

- `ai_engine/base_profile.py`: 실제 `base_profile.json` version `0.1` 생성.
- raw landmark sample, best asset, derived metrics, anchors, preview 보존.
- `face_landmark.py`, `hair_synthesis.py`, `postprocess.py`: placeholder.
- 현재 base profile은 3D avatar가 아니라 2D scan foundation.

## Current Working 3D Stack

첫 연구 스택:

1. MediaPipe capture guidance.
2. Pixel3DMM multi-photo hairless head baseline.
3. 필요하면 VGGT camera/depth/point initialization.
4. Hair App 자체 multi-photo UV baker.
5. FreeUV는 unobserved UV completion benchmark로만 우선 사용.
6. DiffLocks strand-hair baseline.
7. Hair App scalp retargeting, hairline alignment, collision correction.
8. Blender/server render validation.
9. GLB/Three.js mobile output.

필수 비교:

- Pixel3DMM vs KaoLRM 및 새 multi-image head 후보.
- 직접 UV + 단순 completion vs FreeUV.
- DiffLocks vs Im2Haircut vs UniHair; 장기적으로 PERM 기반 자체 hair model.
- 3D result vs FLUX.2/HairPort-like 2D quality reference.

FastAvatar는 core에서 제외됐다. 이유는 GPU가 아니라 Gaussian representation과 editable UV mesh/independent hair 구조의 mismatch다. visual benchmark로는 유지한다.

## Important Technical Interpretation

- Pixel3DMM 결과는 실제 두개골 전체를 투시한 스캔이 아니다.
- 보이는 얼굴과 노출 두피는 사진으로 제약되지만, 머리카락에 계속 가린 정수리·뒤통수는 prior와 보조 depth로 추정한다.
- 머리를 뒤로 넘긴 scan은 hairline, forehead, temples, ears 주변 품질을 높인다.
- face appearance는 새 거대 AI보다 direct multi-photo UV baking이 core다.
- star photo는 중앙 얼굴 appearance에 bonus를 주지만, side region에서는 실제 side view가 우선한다.
- AI completion은 관측되지 않은 UV와 seam/de-lighting을 보완한다.
- hair/head 결합은 주로 geometry, optimization, collision 문제이며 반드시 별도 생성 AI일 필요는 없다.

## Compute

- 사용자는 Colab H100 access가 있고 추가 compute 비용 지불 가능.
- 초기에는 quality-first로 무거운 baseline을 비교한다.
- premature quantization/student training은 하지 않는다.
- H100은 missing viewpoint, ambiguity, wrong representation, bad data, license 문제를 해결하지 않는다.
- Colab runtime은 ephemeral이므로 checkpoint, private input/output, environment 기록을 persistent storage에 보존한다.

## Fine-Tuning Order

현재 예상 순서이며 결과에 따라 변경 가능:

1. training 없는 end-to-end geometry + UV proof.
2. DiffLocks/Im2Haircut baseline 비교 후 hair adaptation.
3. 실제 UV hole/seam 실패를 수집한 뒤 UV completion/de-lighting.
4. Pixel3DMM 또는 다른 trusted teacher가 확정된 뒤 fast multi-image head student.
5. 선택적 FLUX.2 등 2D render refinement.

## Historical Model Work

- StableHairV2: official Colab inference 성공, normal portrait에서는 severe artifacts와 identity failure. 현재 core 아님. 재현 recipe는 `docs/07_hair_engine_experiment_plan.md`.
- FLUX.1 Kontext dev: 비공식 Space test 품질 불만족.
- FLUX.2 klein base-9B: 2026-06-20에 2D tuning target으로 선택했으나, 이후 product direction이 true 3D로 이동. 학습은 실행되지 않았고 현재는 auxiliary 2D/reference 후보. 기록은 `docs/09_flux2_klein_tuning.md`.
- Qwen Image Edit, HiDream, LongCat 등: 2D fallback/quality references. 현재 core 3D engine 아님.

## Immediate Next Step

코드 구현보다 먼저 첫 3D bake-off를 작게 재현한다.

1. private user-like multi-photo set 준비: 정면, 좌우 3/4, 좌우 profile, hairline-visible frames.
2. Pixel3DMM official inference를 Colab H100에서 재현.
3. 같은 입력의 best frame으로 KaoLRM 비교.
4. 두 결과를 같은 camera와 neutral material로 render해 geometry/identity/hairline을 평가.
5. winner를 영구 확정하지 말고 첫 UV prototype에 사용할 temporary baseline으로 선택.
6. Pixel3DMM camera/mesh를 이용한 direct UV projection prototype으로 넘어가기.

## Documentation Map

- `README.md`: 최신 overview와 구현 경계.
- `docs/01_problem_definition.md`: 문제와 성공 기준.
- `docs/02_idea_evolution.md`: 방향 전환 기록.
- `docs/03_mobile_web_mvp.md`: 현재 UI/backend와 미래 3D UI.
- `docs/04_scan_pipeline.md`: 현재 capture와 3D 확장.
- `docs/05_base_model_design.md`: current JSON과 future 3D assets.
- `docs/06_hair_synthesis_pipeline.md`: strand hair reconstruction/fitting.
- `docs/07_hair_engine_experiment_plan.md`: StableHairV2 historical recipe.
- `docs/08_general_image_editing_strategy.md`: 2D auxiliary/fallback strategy.
- `docs/09_flux2_klein_tuning.md`: superseded 2D tuning decision and reusable FLUX knowledge.
- `docs/10_3d_hair_app_master_plan.md`: current detailed source of truth.

## Working Rules

- 사용자와는 한국어로 직접적으로 소통한다.
- current implementation과 future plan을 섞지 않는다.
- private biometric data를 git에 넣지 않는다.
- raw scan/photo data와 observed texture를 보존한다.
- 모델의 code, weights, data, dependencies license를 각각 확인한다.
- 연구 성공을 상용 가능으로 오해하지 않는다.
- 문서 또는 계획은 실험 결과에 따라 수정 가능하며 그 변경 이유를 기록한다.
