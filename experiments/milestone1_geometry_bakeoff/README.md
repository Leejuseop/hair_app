# Milestone 1: Hairless Geometry Bake-Off (Pixel3DMM vs KaoLRM)

Created: 2026-06-21
Status: experiment starter; no result recorded yet
Source of truth for the plan: `docs/10_3d_hair_app_master_plan.md` (Milestone 1), `newchat.md` (Immediate Next Step)

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
2. **Pixel3DMM** — `pixel3dmm_colab.ipynb` 실행.
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
- **pytorch3d / nvdiffrast 빌드:** Pixel3DMM에서 가장 깨지기 쉬운 부분. CUDA arch(`TORCH_CUDA_ARCH_LIST`)를 Colab GPU에 맞춰야 할 수 있다.
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
