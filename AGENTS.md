# AGENTS.md

Hair App에서 작업하는 AI coding agent를 위한 저장소 규칙이다.

## Start Here

실질적인 작업을 시작하기 전에 다음 순서로 확인한다.

1. `git status --short --branch`
2. `newchat.md`
3. 변경하려는 영역의 `docs/*.md`
4. 전체 3D 방향이 관련되면 `docs/10_3d_hair_app_master_plan.md`

현재 구현, 재현 가능한 실험 결과, 문서가 충돌하면 현재 구현과 결과를 우선하고 같은 작업에서 문서를 동기화한다. 사용자 변경과 관계없는 working-tree 수정은 버리거나 덮어쓰지 않는다.

## Documentation Sync Rule

이 프로젝트는 장기간 진화할 예정이므로 문서 동기화는 선택 사항이 아니다.

- 코드 동작을 바꾸면 관련 README/docs를 같은 작업에서 갱신한다.
- API, request/response, 저장 형식, 데이터 흐름, 설치법, 사용자 행동이 바뀌면 관련 문서를 갱신한다.
- 제품 방향이나 모델 전략이 바뀌면 기존 문서를 수정하거나 `docs/`에 새 문서를 만든다.
- 현재 구현과 미래 계획을 반드시 분리해 쓴다.
- 아직 없는 route, 모델, worker, asset을 구현 완료처럼 표현하지 않는다.
- 계획에는 가정, 검증 방법, 대체 후보, 변경 가능성을 기록한다.
- 모델 선택은 영구 확정처럼 쓰지 말고 선택 날짜, 근거, 실패 조건을 남긴다.
- 문서 수정이 불필요한 작업이라면 최종 응답에 그 사실을 명시한다.

## New-Chat Handoff Rule

`newchat.md`는 새 AI 대화에서 빠르게 이어가기 위한 compact handoff다.

- 구현 상태, 제품 방향, 모델 실험, blocker, 즉시 다음 단계가 바뀌면 갱신한다.
- 상세 내용은 관련 docs로 연결하고, 긴 재현 로그를 중복 복사하지 않는다.
- 중요한 변경이 commit/push되었는지 기록한다.
- 새 대화는 `newchat.md`만 믿지 말고 반드시 실제 `git status`와 코드를 확인한다.

## Current Product Direction

Hair App의 현재 목표는 단일 2D 편집 이미지가 아니라 다음 표현을 갖는 진짜 3D 파이프라인이다.

```text
여러 사용자 사진 + 가이드 헤어라인/두상 스캔
  -> 편집 가능한 민머리 head mesh
  -> 실제 사진 기반 face UV texture

헤어스타일 참고 사진
  -> 독립된 3D strand hair

head + hair
  -> scalp retargeting + hairline alignment + collision correction
  -> rotatable GLB and optional rendered stills
```

첫 연구 가설:

- MediaPipe: capture guidance와 저비용 품질 검사.
- Pixel3DMM: 첫 multi-photo head baseline과 possible teacher.
- VGGT: 선택적 camera/depth/point initialization.
- Hair App UV baker: 실제 관측 픽셀을 공통 UV로 투영·가중 합성.
- FreeUV: 관측되지 않은 UV 영역의 연구용 completion baseline.
- DiffLocks: 첫 strand-hair baseline.
- custom geometry module: scalp mapping, root fitting, deformation, collision correction.
- GLB/Three.js: interactive delivery.

이 조합은 고정되지 않았다. Pixel3DMM은 KaoLRM 등과, FreeUV는 단순 completion 및 자체 모델과, DiffLocks는 Im2Haircut·UniHair·PERM 계열과 동일 입력으로 비교한다.

FastAvatar는 현재 core가 아니다. 이유는 compute가 아니라 Gaussian representation과 편집 가능한 UV mesh/독립 hair 요구의 mismatch다. 시각 benchmark나 미래 대안으로 유지한다.

FLUX.2와 일반 image editor 연구는 폐기하지 않는다. 2D quality benchmark, auxiliary hairstyle views, render refinement, 빠른 fallback에 활용할 수 있지만 interactive 3D geometry의 source of truth는 아니다.

## Current Implementation Boundary

현재 실제 구현:

- React + Vite mobile web.
- MediaPipe Face Landmarker.
- `front`, `left_45`, `right_45`, `left_profile`, `right_profile`, `hairline` 6단계 geometry-oriented 자동 capture.
- 단계별 accepted sample 8~12개.
- FastAPI `POST /api/scan`과 scan storage.
- `selected_3dmm/` reconstruction input bundle.
- `base_profile.json` version `0.2`.
- 대표 이미지·랜드마크·헤어라인 guide preview.

현재 미구현:

- 기존 셀카 multi-upload와 star UI. 현재는 사용자가 고른 셀카를 repository 밖 private 폴더에 두고, 앱 스캔의 `selected_3dmm/` 프레임과 오프라인에서 합친다.
- 실제 style-reference persistence.
- 3D head reconstruction.
- UV baking/completion.
- strand hair reconstruction.
- retargeting/collision.
- asynchronous GPU jobs.
- GLB viewer/result.

현재 오프라인 연구 구현:

- `experiments/milestone1_geometry_bakeoff/pixel3dmm_colab_v4.ipynb`로 A100 Pixel3DMM no-MICA baseline을 8장 입력에서 end-to-end 완료했다.
- crop/PIPNet/FaRL/normal/UV가 각각 8/8이고, FLAME `canonical.ply`와 tracking render를 생성했다.
- MICA prior와 MICA init-only는 fixed-context adoption gate를 통과하지 못했다.
- fully refitted mean-shape control이 landmark 기준 no-MICA fitted shape와 동률 또는 소폭 우세였으므로, 현재 `canonical.ply`를 강하게 검증된 개인 두상으로 설명하지 않는다.
- 이 연구 결과는 제품 FastAPI 경로에 연결되지 않았다. 정확한 결과와 다음 실험은 `docs/pixel3dmm_v4.md`를 따른다.

## Experiment Rules

- README의 예시 품질만으로 모델을 채택하지 않는다.
- 동일한 Hair App input set으로 후보를 비교한다.
- official inference를 먼저 재현한다.
- 출력이 다음 단계의 계약에 실제로 들어갈 수 있는지 확인한다.
- fixed validation set, config, seed, model version, runtime, GPU, output을 기록한다.
- baseline 원인을 이해하기 전에 fine-tuning하지 않는다.
- 사용자에게 H100 access가 있으므로 초기 선택에서 VRAM을 과도하게 우선하지 않는다.
- compute는 missing view, 잘못된 representation, data quality, license를 해결하지 않는다는 점을 유지한다.
- private photos, scans, textures, embeddings, meshes를 git에 넣지 않는다.
- private frozen model-trio outputs, texture atlases, coverage maps, renders, and private manifests generated from biometric data must stay in Drive/private storage and must not be committed.

## Representation and Artifact Rules

- head는 가능한 한 stable topology와 UV가 있는 editable mesh로 유지한다.
- face appearance는 mesh와 분리된 UV/material asset으로 저장한다.
- hair는 master strand representation과 mobile LOD/hair-card representation을 분리한다.
- head reconstruction 결과는 hairstyle과 독립적으로 재사용 가능해야 한다.
- raw inputs와 observed texture를 보존하고 AI completion 결과로 덮어쓰지 않는다.
- generated region과 observed region을 coverage/confidence map으로 구분한다.
- model, weight, license, code commit, config, input IDs, output parents를 manifest에 기록한다.
- 현재 private geometry handoff는 raw FLAME template, fitted mean-shape control, personal no-MICA 세 mesh의 texture 비교다. `experiments/milestone1_geometry_bakeoff/freeze_model_trio_for_texture.py`로 private Drive bundle을 만들고, 다음 구현은 그 manifest를 입력으로 받는 observed-photo texture baker부터 시작한다.

## Implementation Rules

- 사용자가 더 큰 build를 요구하지 않으면 검증 가능한 작은 milestone을 우선한다.
- 기존 project pattern을 우선한다.
- 모델이 baseline에서 이기기 전에 production generation route를 연결하지 않는다.
- placeholder route는 명확히 placeholder로 유지한다.
- raw scan/landmark/photo metadata를 가능한 한 보존한다.
- `backend/storage/`는 local runtime data이며 git에 넣지 않는다.
- 비동기 GPU job을 구현할 때 web request process에 장시간 추론을 직접 묶지 않는다.
- plan-only 작업과 implementation 작업을 구분한다.

## Frontend Rules

- React + Vite mobile-first 구조를 유지한다.
- 현재 scan flow를 변경하면 사용자 지시, 재촬영 안내, 상태 text, docs를 함께 수정한다.
- 향후 selfie upload에서는 regional usefulness와 자동 quality score를 별표와 함께 사용한다.
- 3D viewer는 mobile frame rate, GLB size, touch rotation, zoom, reset, fixed camera presets를 검증한다.
- 사용자에게 한 장짜리 hairstyle의 hidden back region이 추정임을 숨기지 않는다.

## Backend Rules

- 현재 backend는 FastAPI다.
- 현재 실제 API는 README와 `docs/10_3d_hair_app_master_plan.md`의 현재 모바일/API 계약을 기준으로 한다.
- file-based storage는 사용자가 DB 도입을 결정하기 전까지 유지한다.
- storage layout이 바뀌면 README와 `docs/10_3d_hair_app_master_plan.md`의 scan/storage/personal-asset 계약을 갱신한다.
- `base_profile.json` 변경 시 version을 올리고 migration/compatibility를 문서화한다.
- 미래 3D worker API는 구현 전까지 계획으로만 표시한다.
- 사용자 biometric asset 삭제와 training opt-in은 production design의 필수 요구사항으로 취급한다.

## Model and License Rules

- code license, model-weight license, dataset license, asset license, dependency license를 별도로 확인한다.
- research에서 실행됐다는 이유로 commercial-safe라고 쓰지 않는다.
- Pixel3DMM, FLAME, KaoLRM, DiffLocks, Im2Haircut, FreeUV 등 현재 후보에는 상용 제한 또는 불명확성이 있다.
- distillation이나 wrapper 재작성으로 upstream 제한이 자동 소멸한다고 가정하지 않는다.
- 상용화 전 라이선스 취득 또는 clean replacement 계획을 요구한다.

## Git Rules

- 사용자가 요청하지 않으면 commit 또는 push하지 않는다.
- commit 전에 `git status --short --branch`를 확인한다.
- 요청과 관련된 파일만 stage한다.
- push 후 commit hash와 branch를 보고한다.
- destructive reset/checkout로 사용자 변경을 버리지 않는다.
