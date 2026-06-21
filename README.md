# Hair App

Hair App은 사용자의 여러 얼굴 사진과 가이드 스캔으로 개인 3D 머리 모델을 만들고, 원하는 헤어스타일 사진을 독립된 3D 머리카락으로 복원해 사용자의 두상에 맞춰 보여주는 모바일 웹 프로젝트다.

현재 저장소는 최종 3D 생성기를 구현한 상태가 아니다. 지금 구현된 범위는 브라우저 카메라, MediaPipe 기반 4단계 스캔, 자동 양질 프레임 수집, FastAPI 저장, `base_profile.json` 생성과 미리보기다. 3D 재구성·UV 텍스처·3D 헤어·기하학적 결합은 다음 연구 및 구현 단계다.

가장 상세한 현재 계획은 [`docs/10_3d_hair_app_master_plan.md`](docs/10_3d_hair_app_master_plan.md)를 기준으로 한다.

## Working Product Goal

목표 사용자 흐름:

1. 사용자가 여러 셀카를 올리고 좋은 사진 1~2장에 별표를 표시한다.
2. 사용자가 머리를 뒤로 넘겨 헤어라인과 가능한 두피를 가이드에 맞춰 스캔한다.
3. 여러 사진과 스캔으로 편집 가능한 민머리 3D 머리 메시를 복원한다.
4. 사진에서 실제 피부·입술·눈썹 픽셀을 공통 UV 텍스처로 합쳐 3D 메시 위에 입힌다.
5. 사용자가 원하는 헤어스타일 사진을 한 장 이상 업로드한다.
6. 헤어스타일을 독립된 3D 가닥으로 복원한다.
7. 머리카락을 사용자의 두상과 실제 헤어라인에 맞추고 충돌을 제거한다.
8. 모바일에서 회전·확대할 수 있는 GLB 결과와 선택적 고품질 렌더를 제공한다.

요약:

```text
여러 사용자 사진 + 헤어라인 스캔
  -> 민머리 3D 메시
  -> 다중 사진 얼굴 UV 텍스처
  -> 피부가 입혀진 사용자 3D 머리

헤어스타일 참고 사진
  -> 독립된 3D strand hair

사용자 머리 + strand hair
  -> 리타게팅 + 충돌 보정
  -> GLB/Three.js 3D 결과
```

## Current Working Model Stack

아래 조합은 첫 실험 스택이지 영구 확정안이 아니다.

- 촬영 가이드: MediaPipe Face Landmarker.
- 머리 형상: Pixel3DMM을 첫 연구 기준 및 가능한 teacher로 사용.
- 다중 시점 보조: 필요하면 VGGT로 카메라·깊이·포인트 초기화.
- 얼굴 외관: Hair App 전용 다중 사진 UV 베이킹 파이프라인.
- 미관측 UV 보완: FreeUV 또는 더 단순한 completion 방법을 비교.
- 3D 헤어: DiffLocks를 첫 strand baseline으로 사용.
- 결합: Hair App이 직접 구현하는 두피 리타게팅·헤어라인 정렬·충돌 보정.
- 출력: 서버 품질 렌더와 모바일용 GLB/Three.js.

반드시 비교할 후보:

- 머리 형상: Pixel3DMM, KaoLRM, VGGT 보조 유무, 향후 공개되는 다중 사진 머리 모델.
- 얼굴 텍스처: 직접 UV만 사용, FreeUV 보완, Hair App 자체 completion 모델.
- 헤어: DiffLocks, Im2Haircut, UniHair, 장기적으로 PERM 기반 자체 모델.
- 품질 기준: FLUX.2 또는 HairPort 계열의 2D 결과를 보조 benchmark로 유지.

FastAvatar는 현재 핵심에서 제외한다. GPU가 부족해서가 아니라 Gaussian Avatar가 `편집 가능한 UV 메시 + 독립된 교체형 머리카락`이라는 제품 표현과 잘 맞지 않기 때문이다. 시각 품질 benchmark나 미래 대안으로는 남겨둔다.

## Important Interpretation

Pixel3DMM의 결과는 사진 속 머리카락을 투시해 실제 두개골 전체를 스캔한 것이 아니다. 보이는 얼굴과 두피는 사진으로 제약하고, 머리카락에 계속 가린 정수리·뒤통수는 FLAME 계열 prior와 보조 깊이 정보로 추정한다. 머리를 뒤로 넘긴 스캔은 실제 헤어라인·이마·관자놀이·귀 주변 품질을 높이지만 모든 두피를 직접 관측하지는 못한다.

얼굴 표면을 입히는 핵심은 새로운 거대 AI가 아니라 다중 사진 UV 베이킹이다. Pixel3DMM이 제공한 메시와 카메라를 이용해 각 사진에서 보이는 피부 픽셀을 공통 UV 지도에 투영하고, 가시성·각도·선명도·조명·별표를 지역별로 가중 합성한다. AI는 주로 보이지 않은 영역, seam, de-lighting을 보완한다.

## Current Implementation

구현 완료:

- React 18 + Vite 모바일 웹 UI.
- `getUserMedia` 실시간 카메라.
- 프론트엔드 MediaPipe Face Landmarker.
- `front`, `left`, `right`, `hairline` 가이드 스캔.
- 감지·거리·중앙 정렬·밝기·선명도·yaw·roll·안정성 품질 검사.
- 단계별 양질 샘플 20개 자동 수집.
- `POST /api/scan` 스캔 번들 업로드.
- FastAPI 파일 기반 저장.
- 원본에 가까운 샘플 데이터와 `base_profile.json` 생성.
- 대표 정면 이미지, 랜드마크, 헤어라인 가이드, 요약 수치 미리보기.

아직 placeholder 또는 미구현:

- 기존 셀카 다중 업로드와 별표 UI.
- 실제 스타일 참고 이미지 저장.
- Pixel3DMM/VGGT/KaoLRM 추론.
- UV 베이킹과 UV completion.
- DiffLocks/Im2Haircut 헤어 복원.
- 두피 리타게팅과 충돌 처리.
- 비동기 GPU 작업 큐.
- 실제 GLB 결과와 3D 뷰어.
- 데이터베이스, 인증, 결제, 운영 배포, 바이오메트릭 데이터 삭제 흐름.

## Current Data Flow

현재 구현된 흐름:

1. 사용자가 `Start Scan`을 누른다.
2. 브라우저가 카메라와 MediaPipe를 시작한다.
3. `front`, `left`, `right`, `hairline`을 순서대로 수집한다.
4. 품질 조건을 통과한 프레임과 랜드마크를 자동 저장한다.
5. 완성된 번들을 `POST /api/scan`으로 전송한다.
6. 백엔드가 `backend/storage/scans/{scan_id}/` 아래에 사진과 JSON을 저장한다.
7. 백엔드가 `base_profile.json`을 만든다.
8. 프론트엔드가 현재 2D 기반 프로필 미리보기를 표시한다.

계획된 3D 흐름은 마스터 계획 문서의 milestone을 따른다. 계획 API를 실제 구현 API처럼 문서화하거나 노출하지 않는다.

## API Routes

실제 구현:

- `POST /api/scan`
- `GET /api/scan/{scan_id}`
- `GET /api/base-profile/{scan_id}`

Placeholder:

- `POST /api/style-reference`
- `POST /api/generate`
- `GET /api/result/{result_id}`

향후 3D 작업 API와 비동기 job 구조는 아직 확정되지 않았다.

## Compute and Fine-Tuning

사용자는 Colab H100을 사용할 수 있고 추가 GPU 비용도 지불할 수 있다. 따라서 초기 단계는 속도보다 최고 품질과 분석 가능성을 우선한다.

원칙:

1. 공식 inference를 재현한다.
2. 같은 Hair App 입력으로 후보를 비교한다.
3. 다음 단계에서 실제로 사용할 수 있는 출력 형식인지 확인한다.
4. 라이선스와 데이터 권리를 확인한다.
5. baseline 실패 원인이 명확해진 뒤 fine-tuning한다.
6. 경량화와 학생 모델은 latency가 실제 병목이 된 뒤 진행한다.

현재 예상 fine-tuning 순서는 hair model, UV completion/de-lighting, 빠른 다중 사진 head student, 선택적 2D refinement 순이다. 결과에 따라 언제든 바뀔 수 있다.

## License Warning

현재 연구 후보에는 비상업적 제한이 많다.

- Pixel3DMM 공개 저장소: CC BY-NC 4.0.
- FLAME: 기본 연구 라이선스이며 상용 사용은 별도 확인 필요.
- KaoLRM 공개 스택: 가중치와 의존성 때문에 사실상 비상업 연구용.
- DiffLocks 및 Im2Haircut 계열: 비상업 연구 제한.
- FreeUV: 명시적 상용 권한을 가정하면 안 됨.
- PERM 코드: MIT지만 데이터와 의존성은 별도 감사 필요.

연구용 pipeline이 잘 작동해도 그대로 상용 출시할 수 있다는 뜻은 아니다. 상용화 전에는 라이선스를 취득하거나 제한된 구성요소를 깨끗한 대안으로 교체해야 한다.

## Documentation Map

- [`docs/01_problem_definition.md`](docs/01_problem_definition.md): 현재 문제 정의와 성공 기준.
- [`docs/02_idea_evolution.md`](docs/02_idea_evolution.md): 2D 편집 중심에서 진짜 3D 구조로 바뀐 이유.
- [`docs/03_mobile_web_mvp.md`](docs/03_mobile_web_mvp.md): 현재 웹 구현과 계획 UI의 경계.
- [`docs/04_scan_pipeline.md`](docs/04_scan_pipeline.md): 현재 스캔 데이터와 3D용 확장 계획.
- [`docs/05_base_model_design.md`](docs/05_base_model_design.md): 현재 `base_profile.json`과 미래 3D asset 계약.
- [`docs/06_hair_synthesis_pipeline.md`](docs/06_hair_synthesis_pipeline.md): 3D 헤어 복원·결합 파이프라인.
- [`docs/07_hair_engine_experiment_plan.md`](docs/07_hair_engine_experiment_plan.md): StableHairV2 과거 실험과 재현 recipe.
- [`docs/08_general_image_editing_strategy.md`](docs/08_general_image_editing_strategy.md): 2D 편집 모델의 보조·fallback 역할.
- [`docs/09_flux2_klein_tuning.md`](docs/09_flux2_klein_tuning.md): FLUX.2 학습 기록과 현재 3D 계획에서의 재배치.
- [`docs/10_3d_hair_app_master_plan.md`](docs/10_3d_hair_app_master_plan.md): 현재 가장 상세한 3D 기준 문서.
- [`newchat.md`](newchat.md): 새 대화용 간결한 최신 handoff.

모든 계획은 실험 결과에 따라 수정할 수 있다. 문서가 코드 또는 측정 결과와 충돌하면 코드와 재현 가능한 결과를 우선하고 같은 작업에서 문서를 다시 동기화한다.

## Project Structure

```text
hair_app/
  README.md
  AGENTS.md
  newchat.md
  docs/
    01_problem_definition.md
    02_idea_evolution.md
    03_mobile_web_mvp.md
    04_scan_pipeline.md
    05_base_model_design.md
    06_hair_synthesis_pipeline.md
    07_hair_engine_experiment_plan.md
    08_general_image_editing_strategy.md
    09_flux2_klein_tuning.md
    10_3d_hair_app_master_plan.md
  frontend/
  backend/
  ai_engine/
```

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
