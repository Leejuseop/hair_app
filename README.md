# Hair App

Hair App은 여러 사용자 사진과 가이드 스캔으로 재사용 가능한 개인 3D 머리를 만들고, 원하는 헤어스타일을 독립된 3D 머리카락으로 복원해 사용자의 얼굴·두상·헤어라인에 맞춰 보여주는 프로젝트다.

목표 출력은 한 장짜리 2D 합성이 아니라 회전 가능한 3D 결과다.

```text
여러 사용자 사진 + hairline/head scan
  -> 편집 가능한 민머리 head mesh
  -> 실제 사진 기반 face UV texture

hairstyle reference image(s)
  -> independent 3D strand hair

head + hair
  -> scalp retargeting + collision correction
  -> mobile GLB + optional high-quality renders
```

모든 모델 선택은 현재 가설이다. 같은 Hair App 입력에서 측정한 결과가 더 좋은 후보가 나오면 Pixel3DMM, MICA, FreeUV, DiffLocks 등을 교체한다.

## Current Status

### 제품 코드에 구현된 부분

- React 18 + Vite mobile-first frontend.
- browser `getUserMedia` camera.
- MediaPipe Face Landmarker.
- `front`, `left`, `right`, `hairline` 4단계 자동 capture.
- 단계별 accepted sample 20개와 quality guidance.
- FastAPI `POST /api/scan`과 file-based scan storage.
- `base_profile.json` version `0.1`.
- representative image, landmark, hairline-guide preview.

### 오프라인 연구에서 완료된 부분

2026-06-24 기준 Pixel3DMM V4 no-MICA baseline을 A100에서 같은 사용자 사진 8장으로 end-to-end 완료했다.

- independent FaceBoxes no-roll crop: 8/8;
- PIPNet WFLW-98 landmarks: 8/8;
- FaRL segmentation: 8/8;
- Pixel3DMM normal maps: 8/8;
- Pixel3DMM UV correspondence maps: 8/8;
- multi-photo FLAME tracking complete;
- `canonical.ply`: 5,023 vertices, 9,976 faces;
- fitted identity landmark error: `5.8803 px`;
- mean FLAME landmark error under the same fitted cameras/poses/expressions: `7.1109 px`;
- quick diagnostic improvement: `1.2306 px`, approximately `17.3%`, fitted wins 8/8 views.

이 결과는 첫 개인화 geometry baseline이다. 제품 FastAPI에 연결되지 않았고, 실제 피부 UV texture·3D hair·retargeting·GLB도 아직 구현하지 않았다. hidden scalp/rear head는 여전히 prior 추정이다.

### 아직 미구현인 부분

- existing-selfie multi-upload와 star UI;
- production 3D reconstruction job/API;
- 실제 사진 픽셀 기반 UV baker와 missing-region completion;
- hairstyle-reference persistence;
- strand-hair reconstruction;
- hairline-aware retargeting과 collision correction;
- asynchronous GPU job queue;
- final GLB builder와 mobile 3D viewer;
- production auth, encryption, retention, deletion, billing, deployment.

## Current Research Stack

- capture guidance and low-cost quality checks: MediaPipe.
- first head geometry baseline: Pixel3DMM + FLAME.
- next immediate experiment: same-input MICA versus no-MICA A/B.
- optional geometry/camera assistance: VGGT.
- face appearance: custom multi-photo observed-pixel UV baker.
- missing UV research baseline: FreeUV versus simpler completion.
- first strand-hair baseline: DiffLocks, compared with Im2Haircut and current alternatives.
- head/hair integration: custom scalp mapping, root fitting, and collision correction.
- delivery: Blender/server validation renders and GLB/Three.js.

FastAvatar는 현재 core가 아니다. Gaussian avatar와 `editable UV mesh + independent replaceable hair` 요구가 맞지 않기 때문이다. FLUX.2와 일반 image editor 연구는 2D quality benchmark, auxiliary views, optional render refinement, fallback으로 남긴다.

## Pixel3DMM V4

Executable notebook:

- [`experiments/milestone1_geometry_bakeoff/pixel3dmm_colab_v4.ipynb`](experiments/milestone1_geometry_bakeoff/pixel3dmm_colab_v4.ipynb)

Complete contract, source audit, errors/fixes, live metrics, limitations, and next experiment:

- [`docs/pixel3dmm_v4.md`](docs/pixel3dmm_v4.md)

The notebook is executable code and intentionally stays under `experiments/`. The Markdown is the long-lived explanation and stays under `docs/`. They share the V4 name because they describe the same experiment, but they are not redundant files.

## Documentation

Detailed Markdown has been consolidated into three documents.

- [`docs/10_3d_hair_app_master_plan.md`](docs/10_3d_hair_app_master_plan.md): product goal, current app/API/storage contracts, future personal-head asset, UV, hair, service, evaluation, fine-tuning, privacy, and license plan.
- [`docs/pixel3dmm_v4.md`](docs/pixel3dmm_v4.md): all Pixel3DMM V4 preprocessing, execution, errors, fixes, results, current loss interpretation, and next A/B experiments.
- [`docs/history.md`](docs/history.md): project chronology from the first 2D attempts through the 3D pivot and current geometry baseline.
- [`newchat.md`](newchat.md): compact handoff for the next AI conversation.
- [`AGENTS.md`](AGENTS.md): repository working rules for coding agents.

Root `README.md`, `AGENTS.md`, and `newchat.md` remain at the repository root because GitHub and agents discover them there. Detailed project knowledge is centralized under `docs/`.

## Implemented API

- `POST /api/scan`
- `GET /api/scan/{scan_id}`
- `GET /api/base-profile/{scan_id}`

Current placeholders, not finished generation APIs:

- `POST /api/style-reference`
- `POST /api/generate`
- `GET /api/result/{result_id}`

## Project Structure

```text
hair_app/
  README.md
  AGENTS.md
  newchat.md
  docs/
    10_3d_hair_app_master_plan.md
    pixel3dmm_v4.md
    history.md
  experiments/
    milestone1_geometry_bakeoff/
      pixel3dmm_colab_v4.ipynb
      scoring_sheet.csv
  frontend/
  backend/
  ai_engine/
```

Private photos, scans, landmarks, masks, textures, embeddings, meshes, tracking videos, and Drive run folders must never be committed.

## Local Development

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Backend:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt
cd backend
uvicorn main:app --reload
```

- Frontend: `http://127.0.0.1:5173/`
- Backend docs: `http://127.0.0.1:8000/docs`

## License and Privacy Warning

Pixel3DMM, FLAME, KaoLRM, DiffLocks, Im2Haircut, FreeUV, and related assets have research-only, non-commercial, dependency, dataset, or unclear-license constraints. A successful research run is not automatically commercial-safe. Code, model weights, datasets, assets, and dependencies must be audited separately before launch.

Face photos, landmarks, embeddings, meshes, and textures are biometric-sensitive. Production requires explicit consent, encryption, short retention, user-visible deletion, and a separate training opt-in.
