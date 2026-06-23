# Hair App New-Chat Handoff

Last synchronized: 2026-06-23
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
- 이번 Pixel3DMM V4 문서/코드 publish 직전 base commit: `a30458d experiment: add hardened Pixel3DMM Colab rerun`
- 사용자가 2026-06-23 V4 전체 변경을 `main`에 commit/push하도록 요청했다. 실제 최종 commit은 `git log -1 --oneline`과 `git status`로 재확인할 것.

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

첫 3D bake-off(Milestone 1)를 진행 중이다. Colab 노트북과 진행상황은
`experiments/milestone1_geometry_bakeoff/` (특히 최신 `pixel3dmm_colab_v4.ipynb`, README의 Progress/Resume, `docs/13_pixel3dmm_v4_live_run_2026-06-23.md`).

진행 상태 (2026-06-23, A100 및 crop-only Colab에서 실행):

- ✅ 환경 빌드(pytorch3d/nvdiffrast, CUDA 11.8 toolkit, A100 arch) 통과.
- ✅ 전처리 설치 수정: 공식 스크립트의 SSH clone이 Colab에서 실패 → facer/PIPNet HTTPS 설치,
  FaceBoxes에 Cython 필요, uv/normals ckpt를 올바른 위치로. facer `farl.py` `.long()` 패치.
- ✅ 전처리(cropping + segmentation)까지 통과 확인. `VID_NAME`은 입력 폴더 basename으로 자동 도출.
- ✅ 과거 오류와 공식 코드의 추가 함정을 반영한 `pixel3dmm_colab_safe.ipynb` 준비: A100/H100 arch 자동 감지, Torch pin, MICA zero-prior 우회, FLAME2020+2023 수동 검증 설치, dynamic batch, `global_iters` 교정, output/log 검증.
- ✅ `pixel3dmm_colab_v4.ipynb` 구현: official FaceBoxes를 사진마다 적용하는 margin 1.42 **no-roll 512 crop**, 후보 ranking/양방향 affine manifest, official PIPNet 98 overlay/count, FaRL count/visual gate를 통합했다. shared static bbox와 v1~v3 roll은 V4 기본 경로에서 제거했다.
- ✅ V4는 crop-only가 아니라 환경 설치 → 실제 FLAME asset 통합 설치 → 전처리 → normal/UV → `track.py` → mesh preview → Drive manifest까지 포함한 전체 Pixel3DMM notebook이다. 단, 사람이 crop/PIPNet/FaRL을 확인하고 `PREPROCESSING_APPROVED=True`로 바꾸기 전에는 뒤 단계가 의도적으로 중단된다.
- ✅ live preprocessing Gate A/B/C: private 8장 crop, PIPNet 98, FaRL이 모두 8/8 생성됐고 Drive complete bundle까지 저장됐다고 사용자가 보고했다.
- ⚠️ **즉시 다음 실행:** 현재 Colab이 살아 있으면 `network_inference.py`에 trusted official checkpoint용 `weights_only=False` 한 줄 patch를 적용하고 section 8 normal/UV 셀을 재실행한다. 그 다음 count cell에서 `expected/normals/uv: 8 8 8`을 확인하기 전 tracking을 실행하지 않는다. runtime이 사라졌으면 최신 V4를 처음부터 사용한다. 상세 exact code는 `docs/13_pixel3dmm_v4_live_run_2026-06-23.md` §11.
- V4 첫 live 재실행에서 `FLAME2020.zip`, `FLAME2023.zip`, `FLAME_masks.zip`에는 `flame_static_embedding.pkl`이 없어 설치 셀이 중단됐다. 이는 세 ZIP의 정상 구성이다. V4는 이제 DECA pinned commit의 FLAME-compatible `landmark_embedding.npy`를 자동 다운로드하고 SHA-256 `8095348e...d667954`와 static/dynamic key를 검증하도록 수정했다. 현재 runtime에서는 실패 셀의 `else` block을 같은 코드로 바꿔 전체 셀을 재실행하면 된다.
- 다음 live V4 crop 실행은 `FaceBoxesV2/faceboxes_detector.py`의 legacy absolute import `from detector import Detector` 때문에 `ModuleNotFoundError`로 중단됐다. 공식 `run_cropping.py`처럼 FaceBoxesV2 폴더를 `sys.path`에 먼저 넣도록 embedded helper를 수정했고, 이후 conda 내부 traceback이 숨지 않도록 `--no-capture-output`도 추가했다. 현재 runtime에서는 생성된 `/content/per_image_no_roll_crop_v4.py`의 import 부분을 같은 방식으로 patch한 뒤 crop command를 재실행한다.
- FaceBoxes import patch 뒤 같은 private 8장에 V4 per-image no-roll crop이 8/8 생성됐다. `00000`, `00007`은 multiple-face warning, `00007`은 FaceBoxes confidence `0.716`과 low-confidence warning이 있으므로 아직 crop 품질을 승인하지 않는다. 다음 즉시 단계는 V4의 `7.1 원본/crop 시각 gate` 셀을 실행해 주 피사체 선택과 얼굴 coverage를 확인하는 것이다. PIPNet/FaRL은 이 시각 gate 뒤에 실행한다.
- V4 Gate A 시각 검사 결과 7장은 정상이고 `00007`만 실패했다. FaceBoxes는 실제 profile 얼굴을 빨간 후보로 검출했지만 custom selection의 `0.70*relative_area + 0.20*confidence + 0.10*centrality`가 더 큰 가슴/목 오검출을 초록 주 후보로 선택했다. no-roll 자체는 의도대로 유지됐다. 다음 단계는 `00007` candidate ranking을 출력해 confidence/box를 확인한 뒤, 단순 면적 우선이 아닌 official confidence 또는 second-detector/PIPNet validation 기반 선택으로 고친 후 Gate A를 다시 실행하는 것이다. 현재 crop은 승인하지 않으며 PIPNet/FaRL로 진행하지 않는다.
- `00007` candidate metadata 확인: 실제 얼굴 후보는 confidence `0.9352`, area score `0.5602`; 가슴/목 false positive는 confidence `0.7161`, area score `1.0`이었다. detector는 진짜 얼굴에 훨씬 높은 confidence를 줬고 custom area-heavy score만 선택을 뒤집었다. V4 selection을 official `pipnet_utils.py`와 같은 confidence-first로 수정했다. area/center는 기록만 유지한다. 현재 runtime에서 helper score 한 줄을 patch해 crop을 8장 다시 생성하고 Gate A를 재실행해야 한다.
- confidence-first live 재실행은 8/8 crop 생성에 성공했고 `00007` 선택 confidence가 `0.935`로 교정됐다. `00007`의 `low_faceboxes_confidence`와 `source_too_tight_margin_reduced` warning도 사라지고 multiple-face diagnostic만 남았다. 다음 즉시 단계는 `7.1 원본/crop 시각 gate`를 다시 실행해 마지막 crop이 실제 얼굴인지 확인하는 것이다. 통과하면 PIPNet/FaRL 단계로 진행한다.
- 재실행한 Gate A 시각 검사에서 `00007`은 실제 profile 얼굴을 올바르게 crop했고 필요한 얼굴 coverage와 no-roll 보존을 확인했다. 전체 8장 Gate A PASS. 다음 즉시 단계는 V4 `7.2`의 official PIPNet 98 + FaRL 실행 셀과 그 다음 output-count/3열 visual gate를 실행하는 것이다. `PREPROCESSING_APPROVED`는 결과를 보기 전 True로 바꾸지 않는다.
- V4 `7.2` live log에서 PIPNet은 8장 모두 FaceBoxes confidence `0.987~0.999`로 landmark export에 성공했다. FaRL은 code/inference가 아니라 617MB JIT weight 다운로드가 361MB에서 `ConnectionResetError`로 끊겨 시작 전 종료됐다. 현재 runtime은 curl retry/resume로 weight를 완성한 뒤 `torch.jit.load` 검증과 segmentation만 재실행한다. V4 수정본은 설치 단계에서 이 weight를 미리 retry/resume 다운로드하고 JIT load를 검증하도록 변경했다.
- FaRL weight 복구 후 segmentation 재실행 성공. count gate는 `input/crop/meta/landmark/annotated/seg = 8/8/8/8/8/8` PASS. 첫 두 시각 결과에서 PIPNet 98점과 FaRL class mask가 final crop에 정렬돼 있고 얼굴 주요 부위가 타당하게 보였다. Gate B/C 최종 승인은 stress profile인 `00006/00007`까지 시각 확인한 뒤 결정하며, 그 전에는 `PREPROCESSING_APPROVED=True`로 바꾸지 않는다.
- runtime-local preprocessing artifact가 끊김으로 사라지지 않도록 V4에 `7.3` Drive save cell을 추가했다. `cropped`, `crop_meta`, PIPNet landmark/overlay, `pipnet`, FaRL raw/color mask와 8행 3열 `preprocessing_overview.png`, summary JSON을 `MyDrive/hair_app/runs/pixel3dmm_v4_preprocessing_{VID_NAME}_{UTC}`에 저장한다. private biometric artifact이므로 git에는 넣지 않는다.
- 사용자 요청으로 V4 `7.4` complete bundle을 추가했다. raw input 복사본, official input/crop, FaceBoxes 후보·선택 bbox·source↔crop transform, PIPNet 98 원본 NPY, frame별 JSON, 전체 JSON, 784-row CSV와 512 pixel 좌표, annotated images, FaRL raw/color masks와 label histogram, logs, README, Pixel3DMM commit/config manifest, 모든 저장 파일 SHA-256을 동일 private Drive run 폴더에 보존한다.
- 첫 normal inference는 PyTorch 2.6+의 `torch.load(weights_only=True)` 기본값 때문에 official Lightning checkpoint 안의 `omegaconf.DictConfig`를 거부해 시작 전 실패했다. checkpoint는 notebook이 official Pixel3DMM Google Drive ID로 받은 trusted research asset이므로 `network_inference.py`의 `load_from_checkpoint` 한 곳에만 `weights_only=False`를 명시하는 compatibility patch를 V4 설치 단계에 추가했다. 현재 runtime에서도 같은 한 줄을 patch한 뒤 normal/UV 셀을 재실행한다.
- 그 뒤: 3D 미리보기 → KaoLRM 동일 입력 비교 → temporary baseline 선택 → direct UV prototype.

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
- `docs/11_canonical_crop_engine.md`: crop v1~v3 roll 실험과 sparse-landmark 한계의 historical record.
- `docs/12_pixel3dmm_preprocessing_contract.md`: official source audit와 최종 per-image no-roll/PIPNet 98 통합 계약.
- `docs/13_pixel3dmm_v4_live_run_2026-06-23.md`: V4 전체 live 실행, 모든 오류/수정, Drive artifact, 정확한 재개 명령.
- `experiments/milestone1_geometry_bakeoff/`: Milestone 1 bake-off Colab notebooks(Pixel3DMM/KaoLRM), scoring sheet, progress/resume notes.

## Working Rules

- 사용자와는 한국어로 직접적으로 소통한다.
- current implementation과 future plan을 섞지 않는다.
- private biometric data를 git에 넣지 않는다.
- raw scan/photo data와 observed texture를 보존한다.
- 모델의 code, weights, data, dependencies license를 각각 확인한다.
- 연구 성공을 상용 가능으로 오해하지 않는다.
- 문서 또는 계획은 실험 결과에 따라 수정 가능하며 그 변경 이유를 기록한다.

## 2026-06-23 FLAME asset 설치 실험 메모

- `pixel3dmm_colab_safe.ipynb`의 기존 FLAME 설치 셀은 현재 배포되는 `FLAME2020.zip` 안에 `landmark_embedding.npy`와 `FLAME_masks.pkl`이 함께 있다고 가정하지만, 실제 사용자 다운로드 ZIP에는 두 파일이 없었다.
- live run에서는 FLAME PyTorch가 안내하는 RingNet의 `flame_static_embedding.pkl`과 `flame_dynamic_embedding.npy`를 결합해 Pixel3DMM 형식의 `landmark_embedding.npy`를 만들었다.
- `FLAME_masks.pkl`은 FLAME 사이트의 별도 **FLAME Vertex Masks** 다운로드에서 찾아 설치했다. `generic_model.pkl`과 `flame2023_no_jaw.pkl`도 검증했으며 최종적으로 `ALL FLAME ASSETS: PASS`를 확인했다.
- 최종 Colab notebook을 정리할 때 기존 5번 FLAME 설치 셀을 이 실제 배포 구조에 맞는 통합 셀로 교체해야 한다. 현재 live runtime에서는 실패 셀을 재실행하지 않고 보완 셀을 추가해 계속 진행 중이다.
- 같은 live run의 preprocessing에서 FaRL/RetinaFace가 일부 multi-angle crop에서 얼굴을 0개로 반환해 `RuntimeError: stack expects a non-empty TensorList`가 3회 발생했다. upstream script가 예외를 출력하고 계속 진행하므로 shell 성공만 믿으면 안 된다. centered 512 crop을 FaRL `forward_warped`에 직접 넣는 fallback을 적용한 뒤 segmentation 개수와 시각 품질을 검증해야 하며, 검증되면 최종 notebook에 반영한다.
- crop pair를 시각 검사한 결과 `00003.jpg` 등에서 눈 위주만 남고 코·입·턱이 잘리는 심각한 오작동을 확인했다. 원인은 `run_cropping.py`가 독립적으로 촬영된 multi-image 입력에도 `static_crop=True`를 쓰고, `pipnet_utils.py`가 서로 다른 원본 좌표계의 face bbox를 평균내 모든 사진에 같은 bbox를 적용하기 때문이다. 앞서 발생한 FaRL 빈 검출의 상위 원인일 수 있다. segmentation fallback으로 덮지 말고, 먼저 각 사진의 자체 detection bbox를 1.42배 확장하는 per-image crop으로 다시 전처리해야 한다.
- 위 문제를 수정하는 `experiments/milestone1_geometry_bakeoff/canonical_face_crop.py`와 unit test를 추가하고 safe notebook 7번 셀을 교체했다. 새 engine은 사진별 bbox와 eye roll을 한 affine resampling에 적용해 512×512로 만들고 yaw/pitch를 보존하며 source↔crop matrix를 JSON으로 저장한다. 합성 test는 통과했지만 실제 private 8장 Colab visual gate는 아직 실행 전이다. 다음 즉시 단계는 새 crop 셀만 실행해 원본/crop 8쌍을 확인하는 것이다.
- 실제 private 사진 검증을 전체 3D 환경과 분리하기 위해 self-contained `canonical_crop_test_colab.ipynb`를 추가했다. 새 Colab에서 이 notebook만 실행해 Drive의 8장에 대한 bbox·눈선·roll·512 crop을 확인하는 것이 현재 사용자 작업이다.
- crop-only live 검증에서 강한 profile 사진 `00007.jpg`의 RetinaFace 첫 두 alignment point 중 하나가 가려진 눈이 아니라 코 주변에 놓이는 것을 확인했다. 따라서 자동 계산된 `roll=-10.4°`는 신뢰할 수 없다. frontal/three-quarter에서만 two-eye roll을 적용하고, profile 또는 eye-point plausibility가 낮은 view는 roll 보정을 생략하거나 MediaPipe pose/다른 안정적 축을 사용해야 한다. 현재 automatic gate는 "제공된 두 점을 수평화했는지"만 확인하므로 anatomical landmark validity gate를 추가해야 한다.
- 8장 전체 crop pair를 시각 검토한 결과 per-image bbox/scale은 기존 static crop보다 크게 개선되어 모든 사진에서 눈·코·입·턱이 유지됐다. frontal/three-quarter의 roll 보정은 정상이며 특히 `00003`의 약 `24.6°` 기울기를 올바르게 세웠다. `00006`과 `00007` profile은 두 눈 landmark가 해부학적으로 불안정하고, `00007`은 잘못된 `-10.4°` 회전이 실제 결과에 영향을 줬다. 따라서 v1 판정은 "bbox/scale PASS, profile roll/warning gate FAIL"이다. 모자·손가락·제품·휴대전화·헤드폰·머리카락 가림은 실제 사용자 입력의 정상적인 stress case로 유지하고, crop에서 거절하지 않으며 뒤 segmentation/regional confidence에서 처리한다.
- 이 문제를 보완한 별도 `canonical_face_crop_v2.py`, test, `canonical_crop_v2_test_colab.ipynb`를 추가했다. v2는 5-point plausibility gate로 profile/가짜 눈 roll을 생략하고, 모든 face candidate를 면적·confidence·중앙 위치로 rank하며, margin 1.50/세로 offset -0.04를 A/B하고, 검은 fill 대신 reflect와 실제 관측 validity mask를 저장한다. 로컬 합성 test는 v1 3개+v2 5개 총 8개 PASS. **실제 8장 v2 시각 검증 전이므로 아직 Pixel3DMM 기본 crop으로 연결하지 않았다.** 상세는 `docs/11_canonical_crop_engine.md`.
- 사용자는 v2가 체감상 큰 업그레이드가 아니라고 평가하고, 눈 2·코끝 1·입꼬리 2의 전체 5점 도형을 정방향으로 맞춰 roll을 계산하자고 제안했다. 이를 별도 `canonical_face_crop_v3.py`, test, `canonical_crop_v3_test_colab.ipynb`로 구현했다. v3는 코끝을 anchor로 다른 네 점의 vector를 upright template에 least-squares similarity fit해 단일 roll만 사진에 적용하며, warp 없이 yaw/pitch를 보존한다. 합성 v3 test 5개는 PASS했지만 실제 결과에서는 아래 sparse-landmark 한계가 확인돼 기본 후보에서 제외됐다.
- 실제 v3 결과에서 RetinaFace 5점이 exact pupil/nose-tip/mouth-corner가 아니라 근사 alignment point여서 roll 개선이 제한됨을 확인했다. 이어 official Pixel3DMM commit `fcd1fa973c7715b02a8948dfc679dff53cf85924`의 preprocessing/tracker를 재감사했다. v1~v3 5점은 최종 fitting landmark가 아니며, 공식 pipeline은 persistent bbox crop 뒤 PIPNet 98점을 생성하고 tracker가 68-point mapping과 iris 96/97, normal/UV/segmentation을 사용해 camera/head roll을 최적화한다. 공식 crop은 roll normalization을 하지 않는다.
- 현재 최종 결정은 **official FaceBoxes per-image bbox + margin 1.42 + no roll + official PIPNet 98 landmarks**다. 고쳐야 할 핵심은 independent images의 절대 bbox를 평균내는 static shared crop이다. PIPNet의 crop 내부 ROI는 landmark inference용 temporary crop이라 유지하고, FaRL 재검출은 segmentation 문제로 별도 검증한다. v1~v3은 historical로 보존하며 safe notebook default에 연결하지 않는다. 상세는 `docs/12_pixel3dmm_preprocessing_contract.md`.
