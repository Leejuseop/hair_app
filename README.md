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
- `front`, `left_45`, `right_45`, `left_profile`, `right_profile`, `hairline` 6단계 geometry-oriented guided capture.
- 단계별 accepted sample 8~12개와 quality/pose guidance.
- FastAPI `POST /api/scan`과 file-based scan storage.
- `selected_3dmm/` reconstruction input bundle과 `selected_3dmm_manifest.json` 자동 생성.
- 선별된 3DMM 입력 프레임을 `C:\Users\User\Desktop\내사진\{scan_id}\selected_3dmm\`에도 자동 복사.
- `base_profile.json` version `0.2`.
- representative image, landmark, hairline-guide preview, 3DMM selected-frame count.

현재 앱 스캔은 제품 안에서 바로 3D reconstruction을 돌리지는 않는다. 대신 사용자의 실제 셀카 묶음과 앱이 만든 `selected_3dmm/` 스캔 프레임을 다음 오프라인 Pixel3DMM 입력으로 넘기기 위한 capture/provenance 단계다. 기존 셀카 업로드 UI는 아직 없으므로, 다음 실험에서는 셀카를 repository 밖 private 폴더에 보관하고 앱 스캔 결과와 수동으로 합친다.

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

이 결과는 첫 end-to-end geometry baseline이다. 다만 fully refitted mean-shape control은 평균 landmark error `5.7423 px`로 no-MICA fitted shape의 `5.8803 px`와 동률 또는 소폭 우세였다. 따라서 현재 수치만으로는 fitted identity shape의 개인화 이득이 증명됐다고 말하지 않는다. 제품 FastAPI에 연결되지 않았고, 실제 피부 UV texture·3D hair·retargeting·GLB도 아직 구현하지 않았다. hidden scalp/rear head는 여전히 prior 추정이다.

같은 8장 입력에서 MICA prior와 MICA init-only도 A/B했다. MICA run은 정상 완료됐지만 2x2 fixed-context landmark 비교에서 no-MICA context 기준 MICA shape가 8/8 view에서 악화됐고, init-only도 같은 결론이었다. 따라서 현재 기본 geometry baseline은 no-MICA Pixel3DMM V4로 유지한다.

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

## Current Private Run Status

On 2026-06-24, a stronger private input set was built from selected selfies plus the app scan frames. The offline Pixel3DMM V4 run completed with 19 accepted views, produced a no-MICA `canonical.ply`, and also produced a fully refitted mean-shape control.

The cross-context landmark gate did **not** validate the no-MICA identity shape as clearly better than the refitted mean shape:

```json
{
  "views": 19,
  "no_mica_context_gain_px": 0.19544085823244828,
  "mean_shape_context_gain_px": -0.6038492081183984,
  "no_mica_wins_both_contexts": false
}
```

The three geometry candidates now used for the next visual experiment are:

1. raw FLAME template, with no photo-derived values;
2. fitted mean-shape control, where identity shape is mean but camera/pose/expression context is fitted from the private photos;
3. personal no-MICA candidate, where identity shape is also fitted from the private photos.

Those meshes and their private manifest have been frozen into the private Drive model-trio handoff folder. The generic helper that created the handoff is tracked at `experiments/milestone1_geometry_bakeoff/freeze_model_trio_for_texture.py`, but the generated mesh files and private manifest are biometric runtime artifacts and must not be committed. The next implementation task is a custom observed-photo face texture baker that can apply the same private photo evidence to all three mesh candidates for visual comparison.

Current storage status:

- the private Drive data has been reorganized into the stable top-level folders `input/`, `output/`, and `shared/`;
- `input/<person>/` contains source selfies, app scan frames, and the clean Pixel3DMM input image set when applicable;
- `output/<person>/` contains preprocessing artifacts, tracking folders, validation renders/metrics, and model folders for that person;
- `shared/models/` contains reusable non-person-specific model assets;
- the current user's next texture-baker entrypoint is the private `output/<person>/models/model_trio_for_texture/model_trio_manifest.json`;
- the legacy girl-model experiment is preserved under the same `input/<person>/` and `output/<person>/` style layout;
- generated mesh files, private manifests, crops, segmentations, landmarks, and photos are biometric runtime artifacts and must not be committed.

Private Drive cleanup guidance:

- keep the new `input/`, `output/`, `shared/`, and `data_layout_manifest.json`;
- keep each person's source inputs, crop/landmark/segmentation outputs, tracking folders, and model manifests until texture baking has reproduced from the same evidence;
- staging folders with names such as `_OLD_STAGING_AFTER_CLEAN_LAYOUT_*`, `_TRASH_REVIEW_*`, and `_REMOVE_FROM_KEEP_REVIEW_*` are deletion candidates after the new `input/`, `output/`, and `shared/` folders have been visually checked;
- do not delete permission-gated shared model assets unless there is a known backup.

## Current Research Stack

- capture guidance and low-cost quality checks: MediaPipe.
- first head geometry baseline: Pixel3DMM + FLAME.
- current geometry choice: Pixel3DMM V4 no-MICA pipeline as the working reconstruction baseline; its optimized identity shape is not yet proven better than a refitted mean FLAME control.
- next practical experiment: implement the custom observed-photo face texture/UV baker and apply it to the raw FLAME, fitted mean-shape control, and personal no-MICA candidate.
- next geometry diagnostic after texture visual review: decide whether to improve capture evidence, tracker resolution, map precision, or identity-shape constraints.
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

## Current Manual Data Handoff

Until selfie upload is implemented, private input preparation is manual. The cleaned Drive layout is the current private data source of truth:

```text
MyDrive/hair_app/
  input/
    <person>/
      selfies/
      scan/
      pixel3dmm_input/
  output/
    <person>/
      preprocessing/
      models/
      tracking/
      validation/
  shared/
    models/
  data_layout_manifest.json
```

For a new private run:

1. keep chosen selfies outside the Git repository, for example `C:\Users\User\Documents\hair_app_private\my_selfies_01\`;
2. run the backend and frontend locally;
3. complete the six-step guided scan in the browser;
4. copy or record the resulting `scan_id`;
5. use `backend/storage/scans/{scan_id}/selected_3dmm/` or the exported `C:\Users\User\Desktop\내사진\{scan_id}\selected_3dmm\` plus the private selfie folder as the next Pixel3DMM input set.

The private selfie folder, `backend/storage/`, Colab Drive outputs, crops, segmentations, landmarks, meshes, textures, embeddings, and videos are biometric-sensitive runtime data and must not be committed.

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
      freeze_model_trio_for_texture.py
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
