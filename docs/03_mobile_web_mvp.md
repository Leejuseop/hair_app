# Mobile Web MVP

Last synchronized: 2026-06-21
Status: current implementation plus clearly separated future 3D UX

## Current Implemented MVP

현재 mobile-first React + Vite app은 guided scan과 base-profile foundation을 검증한다. 실제 3D head, UV texture, strand hair, fitted GLB는 아직 생성하지 않는다.

### Current User Flow

1. 사용자가 `Start Scan`을 누른다.
2. 브라우저가 camera permission을 요청하고 front camera를 시작한다.
3. MediaPipe Face Landmarker를 load한다.
4. `front`, `left`, `right`, `hairline`을 순서대로 진행한다.
5. 각 단계가 quality check를 통과한 sample 20개를 자동 수집한다.
6. 모든 단계 완료 후 하나의 scan bundle을 backend에 upload한다.
7. backend가 scan을 저장하고 `base_profile.json`을 반환한다.
8. frontend가 대표 image, landmarks, hairline guide, summary metrics를 보여준다.
9. hairstyle file을 선택할 수 있지만 실제 persistence와 generation은 placeholder다.

### Current Frontend Scope

`frontend/src/App.jsx`, `frontend/src/scanAnalyzer.js`:

- `navigator.mediaDevices.getUserMedia`.
- `@mediapipe/tasks-vision` Face Landmarker.
- real-time detection and frame analysis.
- progress and quality feedback.
- manual shutter 없이 accepted frame capture.
- scan bundle upload.
- base profile preview.

### Current Quality Checks

- face detection;
- face size/distance;
- center alignment;
- brightness;
- sharpness;
- yaw and expected direction;
- roll/upright;
- movement stability;
- hairline step의 forehead visibility proxy.

### Current Backend Scope

`backend/main.py`:

- completed scan bundle 수신;
- `backend/storage/scans/{scan_id}/` 저장;
- `metadata.json` 기록;
- `ai_engine.base_profile.build_base_profile` 호출;
- `base_profile.json` 기록;
- `/storage` static serving.

## Planned 3D Product Flow

아래는 계획이며 구현 완료가 아니다.

1. 기존 selfie 여러 장을 upload.
2. user가 가장 자신답고 선명한 사진 1~2장에 star 표시.
3. app이 자동 quality/pose/coverage를 평가하고 부족한 view 안내.
4. guided camera scan에서 hair를 뒤로 넘겨 hairline과 가능한 scalp를 capture.
5. async GPU job으로 head geometry reconstruction.
6. multi-photo UV baking과 missing-region completion.
7. hairless textured 3D preview 확인 및 필요 시 recapture.
8. hairstyle reference 한 장 이상 upload.
9. 3D strand hair reconstruction.
10. scalp retargeting, hairline alignment, collision correction.
11. mobile GLB와 server-rendered previews 제공.
12. touch rotate, zoom, reset, front/side/rear presets 제공.

## Planned UI States

- photo upload and star selection;
- automatic input-quality report;
- missing-view and recapture guidance;
- head reconstruction queued/running/failed/succeeded;
- texture coverage and uncertainty warning;
- hair reconstruction queued/running/failed/succeeded;
- single hairstyle image hidden-back uncertainty notice;
- fitting and GLB build progress;
- interactive viewer;
- delete biometric assets.

Progress text should describe the real stage instead of a generic fake percentage.

## UX Principles

- 사용자가 왜 추가 사진이 필요한지 설명한다.
- star는 automatic score와 함께 사용하고 side evidence를 무시하지 않는다.
- inferred scalp와 observed scalp를 같은 확신으로 표현하지 않는다.
- 한 장의 hairstyle reference에서 보이지 않는 rear style은 model hypothesis임을 알린다.
- failed capture와 failed model inference를 구분한다.
- private face data의 retention과 deletion을 명확히 한다.
- mobile viewer 품질 때문에 full strands를 hair cards로 바꿀 수 있음을 내부 asset level에서 관리한다.

## API Boundary

현재 실제 route:

- `POST /api/scan`
- `GET /api/scan/{scan_id}`
- `GET /api/base-profile/{scan_id}`

현재 placeholder:

- `POST /api/style-reference`
- `POST /api/generate`
- `GET /api/result/{result_id}`

향후 3D reconstruction/job routes는 `10_3d_hair_app_master_plan.md`에 아이디어로만 기록되어 있다. 구현 전에는 실제 API로 간주하지 않는다.

## Integration Order

1. Colab/offline에서 geometry와 UV proof를 먼저 완성.
2. output artifact contract 확정.
3. hairstyle strands와 fitting을 offline으로 연결.
4. end-to-end quality가 확인된 뒤 asynchronous backend job 도입.
5. 마지막에 mobile viewer와 product storage를 연결.

이 순서는 결과에 따라 바뀔 수 있다. 모델 검증 전에 UI와 route를 대규모로 미리 만들지 않는다.
