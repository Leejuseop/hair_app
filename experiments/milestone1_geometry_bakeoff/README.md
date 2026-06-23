# Milestone 1: Hairless Geometry Bake-Off (Pixel3DMM vs KaoLRM)

Created: 2026-06-21
Status: V4 preprocessing Gate A/B/C passed 8/8 and saved; normal/UV Gate D compatibility fix pending live rerun
Source of truth for the plan: `docs/10_3d_hair_app_master_plan.md` (Milestone 1), `newchat.md` (Immediate Next Step)

## Progress / Resume (2026-06-23)

`pixel3dmm_colab.ipynb`로 A100에서 실제 실행하며 잡은 fix가 기록돼 있다. 새 실행은 과거 오류, 실제 FLAME 배포 구조, per-image no-roll 전처리 계약을 통합한 **`pixel3dmm_colab_v4.ipynb`를 우선 사용한다.** `pixel3dmm_colab_safe.ipynb`는 V4 이전의 디버그 기준으로 보존한다.

Safe rerun notebook에서 추가로 보강한 내용(2026-06-23):

- A100/H100 compute capability 자동 감지 및 CUDA extension arch 설정.
- 공식 environment 기준 Torch 2.7/cu118 pin.
- `ignore_mica=True`인데도 upstream tracker가 MICA `identity.npy`를 강제로 읽는 부분을 zero prior로 우회.
- tracking이 실제로 요구하는 **FLAME2020 + FLAME2023** 두 asset을 Drive zip에서 수동 설치하고 HTML/깨진 zip/필수 파일을 검증.
- 공식 README의 중복 인자 `iters=100 iters=1500`을 `iters=100 global_iters=1500`으로 교정.
- 입력 사진 수보다 default batch 16이 커서 crash하는 문제를 막기 위한 dynamic batch.
- network inference가 내부 exception을 삼키는 문제를 보완하는 normals/UV output count 검증.
- preprocess/network/tracking raw log와 실제 fix 목록을 Drive run manifest에 저장.
- 독립 사진의 bbox를 평균내는 upstream video용 `static_crop` 문제를 확인했다. V4는 official FaceBoxes detection을 사진마다 별도로 적용하고 margin 1.42의 no-roll 512 crop을 만든다. v1~v3의 RetinaFace sparse-landmark roll은 source audit 뒤 superseded돼 V4 기본 경로에 들어가지 않는다.
- crop 개수만 검사하지 않고 원본/crop pair를 network inference 전에 직접 확인하는 visual gate 및 crop metadata/PIPNet landmark/segmentation count gate 추가.

기존 실행에서 멈춘 지점과 다음에 이어갈 지점:

- ✅ **검증 완료(노트북에 반영됨):**
  - 환경 빌드: CUDA 11.8 toolkit(`cuda-nvcc` + dev libs) 설치 후 `pytorch3d`/`nvdiffrast`를 `--no-build-isolation`으로 빌드, `TORCH_CUDA_ARCH_LIST=8.0+PTX`(A100).
  - 전처리 설치: 공식 스크립트의 **SSH clone이 Colab에서 실패** → `facer`/`PIPNet`을 **HTTPS**로 설치, FaceBoxes 빌드에 **Cython** 필요, `uv.ckpt`/`normals.ckpt`를 올바른 위치(`/content/pixel3dmm/pretrained_weights`)로.
  - 경로: 전처리 출력 폴더명 = 입력 폴더 basename이므로 `VID_NAME`을 `os.path.basename(INPUT_PATH)`로 자동 도출(=`inputs`).
  - facer segmentation: `farl.py`의 인덱스를 `.long()`으로 캐스팅(torch 호환). → cropping + segmentation 통과 확인.
- ✅ **V4에 구현되고 private-photo preprocessing에서 live 검증됨:**
  - official FaceBoxes per-image bbox + margin 1.42 + no-roll 512 crop, 후보 ranking, 사진별 affine/manifest.
  - final crop의 official PIPNet 98 overlay/count와 FaRL segmentation count/visual gate.
  - crop/PIPNet/FaRL을 사람이 승인하기 전 normal/UV로 넘어가지 않는 `PREPROCESSING_APPROVED` gate.
  - 실제 FLAME 배포 구조에서 generic model, FLAME2023, Vertex Masks를 찾고 pinned DECA landmark embedding을 SHA-256 검증하는 설치 셀.
  - 승인 뒤 `network_inference` → output-count gate → `track.py` → 3D mesh preview → Drive run manifest의 전체 Pixel3DMM 경로.
- ⚠️ **다음에 검증할 지점(미완료):**
  - live runtime의 `network_inference.py`에 trusted official checkpoint용 `weights_only=False` patch 적용.
  - normal/UV를 재실행하고 `expected/normals/uv: 8 8 8` count gate 확인.
  - count gate 통과 뒤에만 tracking을 실행해 첫 geometry result 저장.
  - 성공 시 `scoring_sheet.csv` 기록 후 KaoLRM과 동일 입력 비교.

V4 첫 재실행에서는 Drive에 `FLAME2020.zip`, `FLAME2023.zip`, `FLAME_masks.zip`만 있어 `flame_static_embedding.pkl`을 찾지 못했다. 세 ZIP에 Pixel3DMM용 `landmark_embedding.npy`가 없는 것은 정상 배포 구조다. V4 설치 셀은 이제 별도 RingNet 파일을 가정하지 않고, DECA pinned commit `a11554ae2a2b0f3998cf1fa94dd4db03babb34a2`의 FLAME `landmark_embedding.npy`를 내려받아 SHA-256과 static/dynamic key를 검증한다. 이 파일은 Pixel3DMM tracker가 읽는 네 key와 호환된다.

이어진 V4 crop 실행에서는 embedded helper가 FaceBoxesV2를 package import했지만 upstream `faceboxes_detector.py`가 legacy absolute import `from detector import Detector`를 사용해 `ModuleNotFoundError`가 발생했다. 공식 `run_cropping.py`와 동일하게 FaceBoxesV2 디렉터리를 `sys.path` 앞에 추가한 뒤 `faceboxes_detector`를 import하도록 수정했다. `conda run`에는 `--no-capture-output`을 추가해 이후 내부 traceback을 바로 볼 수 있게 했다.

해당 import patch 뒤 private 8장 모두 V4 per-image no-roll crop 생성에 성공했다. `00000`과 `00007`에는 다중 얼굴 후보 warning이 있었고, 강한 profile/occlusion 입력인 `00007`의 FaceBoxes confidence는 `0.716`으로 low-confidence warning이 기록됐다. 이는 output-count gate 통과일 뿐 품질 승인이 아니다. 다음 gate는 notebook의 원본/후보 bbox/crop 시각화에서 실제 사용자 얼굴이 선택됐는지와 이마·눈·코·입·턱 coverage를 확인하는 것이다.

Gate A 시각화에서는 7장이 정상 crop이었지만 `00007`이 가슴/목 영역으로 잘못 crop됐다. 중요한 점은 FaceBoxes가 실제 profile 얼굴 후보 자체는 검출했다는 것이다. 실패 원인은 V4 custom ranking이 confidence보다 상대 면적을 0.70으로 크게 둬 더 큰 false-positive box를 선택한 것이다. 따라서 detector 전체 실패가 아니라 primary-face selection policy 실패로 기록한다. roll 보정은 설계대로 적용하지 않았다. candidate별 confidence/box를 확인한 뒤 official confidence 우선으로 selection을 수정하고 Gate A를 재실행했다.

`00007` metadata에서 실제 얼굴 후보의 FaceBoxes confidence는 `0.9352`, 상대 면적은 `0.5602`였고, 가슴/목 false positive는 confidence `0.7161`, 상대 면적 `1.0`이었다. FaceBoxes 자체는 올바른 후보를 더 신뢰했으므로 첫 baseline은 official `pipnet_utils.py`처럼 confidence-first 선택으로 되돌린다. area와 centrality는 provenance와 향후 실제 다중 인물/identity tie-break 연구용으로만 저장한다.

confidence-first로 crop을 다시 생성한 live 결과는 8/8 성공했고 `00007`이 confidence `0.935`인 실제 얼굴 후보를 선택했다. 이전 low-confidence와 tight-margin warning은 사라졌고 multiple-face diagnostic만 유지됐다. Gate A 최종 통과 여부는 원본/crop 시각화 재확인 뒤 결정한다.

재실행한 원본/crop 시각화에서 `00007`의 실제 profile 얼굴, 얼굴 coverage, no-roll 보존이 정상임을 확인했다. 나머지 7장과 함께 Gate A를 PASS로 기록한다. 다음 gate는 같은 final crop에서 official PIPNet WFLW 98 overlay와 FaRL segmentation의 8/8 completeness 및 시각 품질이다.

Gate B/C 첫 실행에서 PIPNet은 8장 모두 landmark export에 성공했다. FaRL은 segmentation inference 전에 617MB JIT weight를 GitHub release에서 받다가 약 361MB에서 `ConnectionResetError`가 발생했다. 모델이나 crop 실패가 아니라 대용량 다운로드 중단이다. V4는 해당 파일을 설치 단계에서 curl retry/resume로 미리 받고 `torch.jit.load(..., map_location='cpu')`로 integrity를 검증하도록 수정했다.

weight 복구 뒤 FaRL segmentation을 재실행해 `input/crop/meta/landmark/annotated/seg = 8/8/8/8/8/8` count gate를 통과했다. 첫 두 overlay는 PIPNet 98점과 FaRL mask가 final crop 좌표에 맞게 정렬됐고 주요 얼굴 부위가 타당했다. 최종 Gate B/C 판정은 profile/occlusion stress view인 `00006`, `00007` 시각 확인 뒤 내린다.

V4 `7.3`은 runtime-local preprocessing 결과를 Drive run 폴더에 보존한다. final crops, crop metadata, PIPNet 98 `.npy`와 annotated images, FaRL label/color masks, 전체 3열 overview PNG와 summary JSON을 저장한다. 이 폴더는 private biometric artifact이며 git 대상이 아니다.

V4 `7.4` complete bundle은 재현성을 위해 raw input 복사본, official `rgb`/crop, FaceBoxes candidate와 양방향 crop transform, PIPNet 98 원본 NPY와 JSON/CSV/512-pixel export, FaRL raw/color masks와 class histogram, logs, pinned commit/config manifest, 모든 파일 SHA-256을 같은 Drive run에 추가한다. 8장 입력이면 long-form landmark CSV는 784행이어야 한다.

첫 normal inference는 PyTorch 2.6+가 `torch.load`의 기본을 `weights_only=True`로 바꾼 영향으로 official Lightning checkpoint의 `omegaconf.DictConfig` unpickle을 거부했다. V4는 notebook이 official Pixel3DMM Google Drive ID에서 받은 trusted research checkpoint에 한정해 `load_from_checkpoint(..., weights_only=False)`를 명시한다. 전역 allowlist나 임의 checkpoint 허용으로 넓히지 않는다.

이 폴더는 Hair App의 **첫 3D 실험**인 민머리 head geometry bake-off를 Colab H100에서 재현하기 위한 starter다. 코드를 더 만들기 전에 *"Pixel3DMM 또는 KaoLRM이 사용자의 다중 사진에서 쓸만한 hairless head mesh를 만드는가"*라는 핵심 가설을 검증하는 것이 목적이다.

이 starter의 명령들은 2026-06-21 기준 공식 저장소 README에서 가져왔지만, **Colab/PyTorch/CUDA dependency는 자주 바뀌므로 실제 실행에서 깨질 수 있다.** 깨지면 `docs/07_hair_engine_experiment_plan.md`가 StableHairV2로 했던 것처럼, 실제로 통과한 exact version과 fix를 run manifest에 기록한다.

## Goal and Gate

- **Goal:** 동일한 private 다중 사진 세트로 Pixel3DMM와 KaoLRM 공식 inference를 재현하고, 같은 camera/neutral material로 렌더해 점수화한다.
- **Gate (docs/10 Milestone 1):** 측정 결과로 **임시(temporary) geometry baseline 하나**를 고른다. 영구 확정이 아니다. 둘 다 부적합하면 → UV 단계로 넘어가지 말고 capture 요구사항(각도/장수)을 먼저 바꾼다.
- **검증할 Open Question:** Pixel3DMM topology가 required scalp/ears를 충분히 표현하는가? identity가 neutral render에서도 보존되는가?

## Privacy (필수)

얼굴 사진·landmark·mesh·texture는 biometric-sensitive data다. (`AGENTS.md`, `docs/10` §14)

- **private 입력/출력은 절대 git에 넣지 않는다.** 이 폴더의 `inputs/`, `outputs/`는 `.gitignore`로 제외돼 있다.
- private 데이터는 Google Drive 또는 로컬 persistent storage에만 둔다. Colab runtime은 ephemeral이다.
- 실험 로그에서 private path/ID는 redaction한다.
- git에 commit하는 것은 **이 README, 노트북 scaffold, 비식별 점수표**뿐이다.

## Private Input Checklist

bake-off 전에 본인 사진으로 한 세트를 준비한다 (`docs/10` Stage 1, `docs/04` 참고). git 금지.

> 사진은 Google Drive `MyDrive/hair_app/inputs/` 폴더에 넣는다. **Pixel3DMM은 폴더 안의 모든 이미지를 읽으므로 파일명은 자유다.** 결과 mesh와 manifest는 노트북이 `MyDrive/hair_app/results/`, `MyDrive/hair_app/manifests/` 에 저장한다.

- [ ] 정면(front) — neutral expression, even light
- [ ] 좌 3/4 (left three-quarter)
- [ ] 우 3/4 (right three-quarter)
- [ ] 좌 profile
- [ ] 우 profile
- [ ] 헤어라인 노출 프레임 (머리 뒤로 넘김) — 정면 + 좌우
- [ ] 총 5장 이상 권장
- [ ] beauty filter / portrait warp / 광각 왜곡 없음
- [ ] 안경·큰 가림 제거(최소 일부 프레임)
- [ ] (선택) 정체성을 가장 잘 나타내는 1~2장에 star 표시 기록

> 현재 frontend scan flow(`front/left/right/hairline`)로도 유사 프레임을 모을 수 있다. 다만 Pixel3DMM은 video 또는 image 폴더를 직접 받으므로, bake-off 단계에서는 수동으로 준비한 고품질 still 세트로 시작하는 것이 빠르다.

## Run Order

1. **입력 준비** — 위 체크리스트. Drive에 `hair_app_private/m1_inputs/{set_id}/`.
2. **Pixel3DMM** — 새 실행은 `pixel3dmm_colab_v4.ipynb` 사용. `pixel3dmm_colab.ipynb`와 `pixel3dmm_colab_safe.ipynb`는 과거 live-debug 및 V4 이전 기준으로 유지.
   - preprocessing → network inference(normals, uv_map) → tracking(multi-image).
3. **KaoLRM** — `kaolrm_colab.ipynb` 실행 (별도 conda env, 별도 Colab runtime 권장).
   - background 제거 → `infer_mono.sh`(frontal) / `infer_multiview.sh`(profile).
4. **공통 렌더** — 두 결과 mesh를 같은 camera·neutral gray material로 렌더 (정면/좌우 3/4/profile/후면 turntable).
5. **점수화** — `scoring_sheet.csv`에 입력하고 임시 baseline 선택.
6. **manifest 기록** — 각 run의 commit/config/seed/GPU/runtime/license/fix를 Drive에 저장.

## Scoring Rubric (1–5)

`scoring_sheet.csv`에 run별로 기록한다.

| 항목 | 확인 내용 |
| --- | --- |
| identity | neutral render에서 본인으로 인식되는가 |
| geometry | 코/광대/턱선/얼굴 폭·깊이가 맞는가 |
| hairline | front hairline·temple 모양이 사진과 맞는가 |
| side_contour | 옆모습 contour와 비대칭이 맞는가 |
| scalp_ear_topology | scalp/ears topology가 이후 UV·hair fitting에 쓸만한가 |
| execution_reliability | 취약한 수동 fix 없이 안정적으로 돌았는가 |

각 모델의 hidden scalp/rear는 **측정값이 아니라 prior 추정**임을 잊지 말고, geometry 점수는 *관측된 영역* 기준으로 평가한다.

## Known Risks (Colab)

- **conda on Colab:** 두 repo 모두 conda 기반 → `condacolab` 필요, 커널 재시작 발생.
- **pytorch3d / nvdiffrast 빌드:** Pixel3DMM에서 가장 깨지기 쉬운 부분. **env에 CUDA 11.8 toolkit(`cuda-nvcc` + dev libs)이 설치돼 있어야 컴파일된다**(노트북 셀 3-3). CUDA arch는 GPU에 맞춘다: **A100=`8.0+PTX`**, H100=`9.0+PTX`, T4=`7.5+PTX`. 빌드는 10~25분 소요.
- **FLAME 등록:** `download_flame2023.sh` / KaoLRM `fetch_data.sh`는 https://flame.is.tue.mpg.de 계정·동의가 필요.
- **KaoLRM checkpoints:** Releases 페이지에서 `releases/mono/`, `releases/multiview/`로 수동 배치.
- **torch 버전 충돌:** Pixel3DMM(cu118, py3.9) vs KaoLRM(torch 2.9.1 cu126, py3.10) — 같은 runtime에서 섞지 말 것.

## License (commercial path 분리)

- **Pixel3DMM:** CC BY-NC 4.0 (비상업 연구). (`docs/10` §13)
- **KaoLRM:** 소스는 Apache 2.0이나 EG3D/FLAME/weights 때문에 effective use는 비상업 연구로 제한.
- 두 모델 모두 **연구 검증 성공이 곧 상용 가능을 의미하지 않는다.** 상용화 전 라이선스 취득 또는 clean replacement 필요.

## Result Log

bake-off 실행 후 아래에 요약을 적고, 상세는 `scoring_sheet.csv`와 Drive manifest를 가리킨다. 결정이 나면 `newchat.md`의 "Immediate Next Step"과 `docs/10` Milestone 1 Gate를 동기화한다.

| Run | Model | Input Set | Temporary Baseline? | Notes |
| --- | --- | --- | --- | --- |
| TBD | Pixel3DMM | TBD | TBD | first reproduction |
| TBD | KaoLRM | TBD | TBD | comparison |

### FLAME asset live finding (2026-06-23)

현재 FLAME 사이트에서 받은 `FLAME2020.zip`에는 Pixel3DMM이 추가로 요구하는 `landmark_embedding.npy`와 `FLAME_masks.pkl`이 포함되지 않았다. 초기 live workaround에서는 RingNet static/dynamic embedding을 결합했고, **FLAME Vertex Masks**를 별도 설치해 `ALL FLAME ASSETS: PASS`를 확인했다. 최종 V4는 사용자가 별도 RingNet 파일을 준비할 필요가 없도록 pinned DECA 호환 embedding을 SHA-256 검증해 설치하고, Vertex Masks는 Drive ZIP에서 찾는다.

같은 실행의 preprocessing에서는 FaRL detector가 일부 측면/헤어라인 crop에서 빈 face list를 반환해 `stack expects a non-empty TensorList`가 발생했다. upstream segmentation script는 이 오류를 frame 단위로 삼키고 계속 진행하므로 output-count 검사가 필수다. centered crop에 대한 direct `forward_warped` fallback과 결과 mask 시각 검사를 live run에서 검증한 뒤 최종 notebook에 포함할지 결정한다.

후속 원본/crop 시각 검사에서 일부 crop이 눈 위주만 남기고 코·입·턱을 잘라낸 것을 확인했다. 독립 사진마다 해상도와 얼굴 위치가 다른데도 upstream `static_crop` 구현이 모든 detection bbox를 원본 픽셀 좌표에서 평균내 같은 bbox를 재사용한 것이 원인이다. 이 상태의 segmentation fallback 결과는 유효한 baseline이 아니다. 최종 notebook은 multi-image 폴더 입력에서 per-image bbox crop을 사용하고, crop pair 시각 검사 및 얼굴 중요 부위 coverage gate를 network inference 전에 추가해야 한다.

이를 반영해 `canonical_face_crop.py`를 추가하고 safe notebook의 7번 전처리를 교체했다. crop 기하 함수는 detector와 분리되어 있으며 현재 Colab adapter는 Pixel3DMM 환경에 이미 설치된 FaRL/RetinaFace를 사용한다. 합성 landmark test에서 roll 제거, 얼굴 scale 통일, source↔crop matrix 역변환을 검증했다. 실제 8장 입력에서의 detector/crop 시각 gate는 아직 live 재검증 전이므로 완료로 기록하지 않는다.

전체 Pixel3DMM과 분리해 실제 사진 crop만 먼저 확인할 수 있도록 `canonical_crop_test_colab.ipynb`도 추가했다. 이 notebook은 별도 Colab에서 detector 설치, Drive 입력 crop, metadata 저장, 원본/bbox/눈선/crop pair 표시, 수학 검증까지만 수행하며 PIPNet·FaRL parser·Pixel3DMM은 실행하지 않는다.

첫 private-photo 실행에서 강한 profile view의 RetinaFace eye pair가 해부학적으로 틀리게 추정되는 사례를 확인했다(가려진 눈 점이 코 주변에 위치, 계산 roll `-10.4°`). crop affine 계산 자체는 입력 점을 정확히 수평화하지만, 잘못된 점을 수평화하면 잘못된 회전이 된다. 다음 수정은 view/landmark plausibility gate를 추가해 frontal/three-quarter에만 two-eye roll을 적용하고 profile은 roll을 보존하거나 별도 pose source를 쓰는 것이다.

8장 전체 시각 판정은 **bbox/scale PASS, profile roll/warning gate FAIL**이다. 기존처럼 눈만 남는 crop은 사라졌고 모든 crop에 얼굴 핵심 부위가 유지됐으며, frontal/three-quarter roll 보정(예: 약 `24.6°`)도 정상 동작했다. 반면 두 profile view는 eye pair가 불안정했고 한 장은 잘못된 회전이 발생했는데도 `warnings=[]`였다. 이 gate를 고친 뒤 crop engine을 임시 baseline으로 확정한다. 모자·손가락·제품·휴대전화·헤드폰·hair occlusion은 실제 사용자 입력에서 흔하므로 crop 거절 사유로 두지 않는다. 현재 8장은 현실적인 obstacle stress set으로 유지하고, 이후 segmentation mask와 regional confidence로 가려진 픽셀의 geometry/UV weight를 낮춘다.

### Canonical crop v2 candidate (2026-06-23)

첫 시각 검사에서 확인한 문제를 보완하되 v1 비교 결과를 잃지 않도록 별도 `canonical_face_crop_v2.py`와 `canonical_crop_v2_test_colab.ipynb`를 추가했다. v2는 다음을 포함한다.

- RetinaFace의 두 눈뿐 아니라 코·두 입꼬리까지 저장하고 eye/nose/mouth geometry가 불합리하면 roll만 생략한다.
- profile candidate와 roll 생략 이유를 warning으로 남기며 사진은 계속 crop한다.
- 모든 얼굴 후보를 보존하고 상대 면적 0.65, confidence 0.20, 중앙 위치 0.15의 실험 점수로 주 피사체를 선택한다.
- 첫 A/B 기본 margin을 `1.50`, 세로 중심 offset을 `-0.04 * bbox_height`로 두어 context를 조금 늘린다.
- 회전 시 원본 밖은 reflect padding하고, 해당 합성 영역을 실제 관측으로 사용하지 않도록 별도 `crop_validity` mask를 저장한다.
- source↔crop affine 행렬, 5-point geometry 지표, 후보 ranking, observed fraction을 manifest에 기록한다.

로컬 합성 좌표 기준 v2 test 5개와 기존 v1 test 3개, 총 8개가 통과했다. 아직 같은 private 8장으로 v2 시각 A/B를 실행하지 않았으므로 `pixel3dmm_colab_safe.ipynb`의 기본 crop은 v1 상태로 유지한다. 다음 gate는 v2 crop-only Colab에서 `00003` roll 유지, `00006/00007` profile roll 생략, 검은 fill 제거/validity mask, 다중 얼굴 선택과 coverage를 확인하는 것이다. 자세한 설계와 변경 가능한 threshold는 `docs/11_canonical_crop_engine.md`에 기록한다.

### Canonical crop v3: five-point roll candidate (2026-06-23)

v2 결과가 체감상 큰 개선이 아니어서 사용자 제안의 5점 roll을 별도 v3로 구현했다. 두 눈의 선 하나 대신 코끝을 anchor로 두 눈·두 입꼬리까지의 4개 vector를 canonical upright 5점 도형에 least-squares similarity fit한다. fit에서 구한 단일 rotation만 사진에 적용하며 얼굴 점을 따로 warp하지 않아 yaw/pitch와 개인 얼굴형을 보존한다.

v3는 눈선·입선·eye→nose·nose→mouth·eye→mouth 축의 개별 roll, 5점 fit residual, 축 간 disagreement를 metadata에 기록한다. v2의 detector, 주 피사체 선택, margin/center, reflect padding, observed validity mask는 그대로 재사용했다. 합성 v3 test 5개는 통과했지만 실제 8장에서는 RetinaFace 5점이 exact pupil center/nose tip/mouth corner가 아니라 근사 alignment point여서 체감 roll 개선이 제한됐다.

### Final Pixel3DMM preprocessing decision after source audit (2026-06-23)

official `SimonGiebenhain/pixel3dmm@fcd1fa973c7715b02a8948dfc679dff53cf85924`를 다시 확인했다. 우리가 v1~v3에서 시각화한 RetinaFace 5점은 Pixel3DMM tracker가 사용하는 최종 landmark가 아니다. 공식 순서는 persistent bbox crop 뒤 PIPNet이 WFLW 98점을 생성하고, tracker가 이 중 68-point mapping과 iris index 96/97을 사용해 FLAME camera/head pose를 맞춘다. 공식 persistent crop은 roll을 제거하지 않는다.

따라서 현재 기본 설계는 **official FaceBoxes per-image bbox + margin 1.42 + no roll + official PIPNet 98 landmarks**다. 수정 대상은 independent images의 절대 bbox를 평균내는 `static_crop`이며 roll 자체가 아니다. PIPNet이 crop 안에서 다시 ROI를 만드는 것은 landmark network용 temporary crop이고 persistent 512 crop을 다시 만드는 단계가 아니다. FaRL의 재검출은 segmentation parser용 별도 단계다.

v1~v3은 historical experiment로 보존하고 V4 기본 전처리에 연결하지 않는다. V4의 per-image no-roll crop, PIPNet overlay/count, FaRL mask gate는 같은 private 8장에서 live 8/8 통과했다. 다음 작업은 trusted checkpoint compatibility patch 뒤 normal/UV Gate D와 tracking Gate E를 완료하는 것이다. MediaPipe는 우선 PIPNet cross-check와 quality report로만 사용한다. 자세한 좌표 계약은 `docs/12_pixel3dmm_preprocessing_contract.md`, 정확한 재개 명령은 `docs/13_pixel3dmm_v4_live_run_2026-06-23.md`가 source of truth다.
