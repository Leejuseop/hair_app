# Hair App Project History

Last synchronized: 2026-06-24
Status: living project chronology for future review and portfolio writing

## Why This File Exists

이 문서는 현재 설계 명세가 아니라 Hair App이 어떤 문제에서 시작했고, 어떤 모델을 찾고 실행했으며, 결과가 왜 만족스럽지 않았고, 그 판단이 어떻게 다음 구조로 이어졌는지를 보존하는 기록이다.

프로젝트가 끝난 뒤 다시 읽었을 때 다음 질문에 답할 수 있어야 한다.

- 처음에는 무엇을 만들려고 했는가?
- 실제로 어떤 코드와 모델을 실행했는가?
- 무엇이 잘됐고 무엇이 실패했는가?
- 단순한 모델 교체가 아니라 제품 구조를 바꾼 이유는 무엇인가?
- 2D 연구와 실패한 crop 실험은 이후에 어떻게 재사용됐는가?
- 다음 사람이 같은 실수를 반복하지 않으려면 무엇을 알아야 하는가?

현재 구현과 계획의 source of truth는 `README.md`, `newchat.md`, `10_3d_hair_app_master_plan.md`다. 이 문서는 과거의 판단을 당시 맥락과 함께 설명하며, 현재 계획과 충돌하면 현재 구현과 재현 가능한 결과를 우선한다.

## 1. 아이디어의 시발점

출발점은 단순했다. 사용자가 마음에 드는 헤어스타일 사진을 찾았을 때, 그 머리가 자신의 얼굴에 실제로 어울릴지 미리 보고 싶다는 문제였다.

처음 생각한 제품은 대략 다음 흐름이었다.

```text
사용자 얼굴 사진
  + 원하는 헤어스타일 사진
  -> 사용자의 얼굴은 유지하고 머리만 바꾼 결과 이미지
```

하지만 곧 일반적인 헤어 합성 서비스에서 자주 발생하는 문제가 보였다.

- 헤어스타일뿐 아니라 얼굴까지 다시 그려져 사용자가 다른 사람처럼 보임;
- 눈, 코, 입, 피부색, 배경과 옷이 함께 변함;
- 정면 한 장은 그럴듯해도 측면과 후면이 일관되지 않음;
- 실제 헤어라인, 이마, 광대, 턱선, 귀, 두상의 깊이를 제대로 반영하기 어려움;
- 한 장의 스타일 참고 사진에 없는 뒤쪽 머리를 사실처럼 단정하게 됨.

이때부터 Hair App의 문제는 단순한 이미지 생성이 아니라 `identity를 보존하면서 헤어스타일만 제어하는 문제`로 구체화됐다.

## 2. 생성보다 먼저 만든 스캔 기반

완성된 AI 엔진을 바로 연결하기 전에 사용자 정보를 안정적으로 모으는 기반부터 구현했다.

구현된 초기 구조:

1. React + Vite 기반 mobile web;
2. 브라우저 카메라와 `getUserMedia`;
3. MediaPipe Face Landmarker를 이용한 얼굴 위치와 품질 검사;
4. `front`, `left`, `right`, `hairline` 네 단계 가이드 촬영;
5. 단계별 accepted sample 자동 수집;
6. FastAPI `POST /api/scan` 업로드와 file-based storage;
7. raw landmark, 대표 이미지, 품질 지표, anchor를 담는 `base_profile.json` version `0.1`;
8. 얼굴 landmark와 hairline guide preview.

중요한 점은 당시의 `base_profile`이 3D avatar가 아니라는 것이다. 이후 어떤 geometry 또는 texture 모델을 선택하더라도 재사용할 수 있는 structured scan foundation이었다.

이 단계에서 얻은 교훈:

- 모델보다 입력 품질과 원본 보존이 먼저다.
- 얼굴 사진은 biometric-sensitive data이므로 runtime storage와 Git을 분리해야 한다.
- 대표 사진 하나만 남기지 말고 raw frame, landmark, quality, camera/view 의미를 보존해야 한다.
- 이후 모델이 바뀌어도 capture contract가 안정적이면 전체 앱을 다시 만들 필요가 없다.

## 3. 첫 번째 방향: hair-specific 2D 모델 탐색

초기에는 이름 그대로 머리카락 편집을 위해 만들어진 모델이 가장 좋은 답일 것이라고 생각했다. StableHairV2, Stable-Hair, HairFusion, HairFastGAN, HairPort 계열을 조사했다.

### StableHairV2를 선택한 이유

- hairstyle transfer를 직접 목표로 한 공개 연구 모델;
- identity image와 hairstyle reference를 분리해 받는 구조;
- official inference와 pretrained checkpoint가 있어 재현 가능;
- 일반 image editor보다 헤어 영역을 더 전문적으로 다룰 것이라는 기대.

### 실제로 한 작업

- Colab에서 official repository와 checkpoint를 설치;
- dependency와 fp16 dtype 문제를 수정;
- official test pair inference 재현;
- 일반 인물 사진과 원하는 hairstyle reference를 넣은 Hair App 형태의 private test 수행.

### 결과가 마음에 들지 않았던 이유

공식 경로 자체는 실행됐지만 일반적인 사용자 portrait에서는 다음 문제가 발생했다.

- 얼굴과 배경까지 심하게 재생성됨;
- identity가 유지되지 않음;
- 얼굴과 머리 주변에 severe artifact 발생;
- official identity input이 `bald.jpg`로 구성돼 있어 민머리 또는 기존 머리가 제거된 입력을 강하게 가정;
- 사용자가 평범한 셀카를 바로 넣는 제품 흐름과 맞지 않음.

이 실험에서 가장 중요한 교훈은 `hair-specific`이라는 이름이 곧 Hair App에 맞는다는 뜻은 아니라는 점이었다. 논문의 데모 입력과 실제 사용자의 셀카 조건은 다르며, 공식 예제가 성공해도 제품 입력에서는 실패할 수 있다.

StableHairV2의 긴 설치 recipe는 활성 문서에서 삭제했다. 필요하면 Git history에서 복원할 수 있지만 현재 제품 구조의 실행 경로는 아니다.

## 4. 두 번째 방향: 범용 2D image editor

hair-specific 모델의 품질과 identity 문제가 확인된 뒤, 더 강한 범용 image editor에 Hair App의 mask, landmark, hairline 정보를 결합하는 방향을 조사했다.

검토한 후보:

- Qwen Image Edit;
- HiDream;
- FLUX 계열;
- LongCat Image;
- Step1X Edit;
- HairPort와 유사한 2D final-transfer pipeline.

당시 계획은 다음과 같았다.

```text
사용자 portrait + hairstyle reference
  -> multi-reference image editor
  -> 얼굴 identity와 landmark 검사
  -> protected-region compositing
  -> retry/ranking
  -> 최종 2D portrait
```

여기서는 단순 prompt보다 다음을 함께 쓰려 했다.

- face/hair mask;
- hairline anchor;
- protected face region;
- identity embedding score;
- landmark displacement;
- 배경과 옷 보존 검사;
- 여러 seed 결과 ranking;
- baseline이 확인된 뒤 LoRA 또는 editing SFT.

이 접근은 한 장의 보기 좋은 결과를 만드는 데는 가능성이 있었지만, 여러 각도에서 같은 머리와 같은 얼굴을 유지하는 문제는 여전히 해결하지 못했다.

## 5. FLUX.2를 첫 2D 파인튜닝 대상으로 고른 시기

2026-06-20에는 `FLUX.2 [klein] base-9B`를 첫 2D tuning target으로 선택했다.

선택 이유:

- 사용자가 공개 Space에서 편집 가능성을 직접 확인;
- portrait와 hairstyle reference를 함께 쓰는 multi-reference 구조가 목적과 가까움;
- distilled checkpoint보다 undistilled base가 fine-tuning에 적합하다고 판단;
- H100을 사용할 수 있어 작은 모델보다 품질 ceiling을 우선;
- LoRA, cached image latent, cached text embedding 등 현실적인 학습 경로가 존재;
- 4B보다 9B를 우선 검토할 수 있는 compute 여유.

예상 학습 구조:

- transformer core에 LoRA;
- VAE와 text encoder는 freeze;
- portrait + hairstyle reference를 image condition으로 사용;
- target은 identity가 유지된 hairstyle edit;
- identity, landmark, hairline, protected region, artifact를 평가.

사용자는 FLUX.2의 모델 구조를 직접 공부했다. 그러나 실제 LoRA training, checkpoint, 정량 benchmark까지 가기 전에 제품 목표가 3D로 바뀌었다.

이 공부가 헛수고가 아닌 이유:

- 3D 결과의 2D quality benchmark로 사용할 수 있음;
- 한 장짜리 hairstyle reference에서 plausible side/rear hypothesis를 만들 수 있음;
- 정확한 3D render가 다소 거칠 때 presentation refinement에 활용 가능;
- 3D가 완성되기 전 임시 2D preview 후보가 될 수 있음;
- multi-reference conditioning과 identity evaluation 지식은 다른 모델에도 재사용 가능.

다만 generated side/rear view는 실제 관측이 아니며, independently edited view들은 하나의 일관된 3D geometry가 아니다. FLUX.2가 head mesh, UV texture, strand hair, collision correction을 대신하지는 않는다.

## 6. 결정적 전환: 원하는 것은 한 장의 사진이 아니라 회전 가능한 3D

제품을 다시 생각하면서 요구사항이 더 명확해졌다.

사용자가 원한 흐름:

1. 본인 사진을 여러 장 업로드;
2. 본인이 가장 잘 나왔다고 생각하는 1~2장을 star로 표시;
3. 여러 사진에서 얼굴 비율, 코 높이, 눈 깊이, 광대, 턱선, hairline을 분석;
4. 현재 머리카락은 제거한 개인 hairless head를 생성;
5. 원하는 hairstyle 사진을 추가;
6. hairstyle만 독립된 3D 머리카락으로 이해;
7. 개인 head에 hair를 결합;
8. 결과를 여러 각도 또는 손가락으로 회전해 확인.

이 요구사항에서는 2D image editor를 계속 교체해도 핵심 문제가 남는다. 2D 모델은 특정 camera의 픽셀을 잘 그릴 수 있지만, 사용자가 돌려볼 수 있는 공통 geometry와 독립된 hair asset을 자연스럽게 제공하지 않는다.

그래서 source of truth를 다음처럼 바꿨다.

```text
editable hairless head mesh
  + actual-photo-derived face UV texture
  + independent 3D strand hair
  + scalp retargeting and collision correction
```

이것이 2D에서 진짜 3D로 이동한 핵심 이유다.

## 7. 처음 생각한 세 엔진 구조와 이후의 구체화

처음에는 다음 세 엔진으로 단순하게 나눴다.

1. 사용자 사진으로 3D head를 만드는 엔진;
2. hairstyle 사진을 3D hair로 이해하는 엔진;
3. head와 hair를 합성하는 엔진.

이 구분은 큰 방향에서는 맞았다. 연구하면서 각 엔진 사이에 필요한 중간 단계가 더 명확해졌다.

```text
사용자 사진과 scan
  -> 전처리와 camera/landmark
  -> hairless head geometry
  -> multi-photo UV texture

hairstyle reference
  -> mask/orientation/depth
  -> canonical strand hair

head + hair
  -> scalp correspondence
  -> hairline-aware deformation
  -> collision correction
  -> GLB/mobile LOD
```

즉, 단순히 세 개의 거대한 AI 모델을 이어 붙이는 것이 아니라 geometry, texture, hair, fitting의 contract를 분리하는 구조로 발전했다.

## 8. Pixel3DMM과 FastAvatar를 이해하며 바뀐 판단

### Pixel3DMM에 대한 초기 오해와 정리

README 예시의 마지막 민머리 mesh를 보고 처음에는 `사진을 넣으면 얼굴 정보가 없는 대머리 뼈대만 출력하는가`라는 혼동이 있었다.

정확한 해석:

- Pixel3DMM은 얼굴이 없는 빈 두상 template을 출력하는 엔진이 아니다.
- 입력 사진의 얼굴형, 코, 광대, 턱, 표정과 camera pose에 맞도록 FLAME 계열 3D face/head geometry를 fit한다.
- 결과는 hair가 제거된 mesh처럼 보이지만 얼굴 geometry가 포함돼 있다.
- 사진에서 보이지 않는 crown/rear scalp는 실제 scan이 아니라 prior 기반 추정이다.
- 여러 사진은 각 사진의 evidence를 만들고 shared identity를 최적화하는 방식으로 Hair App baseline에 사용할 수 있다.

Pixel3DMM은 최종 상용 엔진으로 확정한 것이 아니라 첫 geometry baseline과 possible teacher로 선택했다.

### FastAvatar를 함께 쓰려 했던 이유

한때는 Pixel3DMM을 geometry teacher로 사용하고 FastAvatar 계열을 Hair App 전용 multi-image model로 개조해 실제 얼굴 appearance를 얻는 구조를 고려했다.

하지만 Hair App이 원하는 것은 stable topology와 UV를 가진 editable mesh, 그리고 교체 가능한 독립 hair였다. Gaussian avatar는 얼굴 appearance와 기존 hair가 얽힐 수 있고, Pixel3DMM mesh로 다시 appearance를 옮기는 추가 문제가 생긴다.

결론:

- FastAvatar는 compute가 부족해서 제외한 것이 아니다.
- representation이 제품의 editing/fitting/export 요구와 맞지 않아 core에서 제외했다.
- photorealistic visual benchmark 또는 미래 대안으로는 남길 수 있다.
- 얼굴색과 입술색을 얻기 위해 또 하나의 full avatar를 만들기보다 실제 사진을 UV로 직접 투영하는 편이 구조적으로 단순하다.

### UV baker를 직접 만들기로 한 이유

여러 사진에 실제로 보이는 피부, 입술, 눈썹 픽셀은 AI가 새로 상상할 필요가 없다. reconstructed mesh와 camera가 있으면 visible pixel을 공통 UV atlas로 옮길 수 있다.

Hair App이 직접 구현할 부분은 새 renderer 전체가 아니라 다음 policy다.

- view별 visibility와 occlusion;
- 얼굴 영역별 적합한 camera 선택;
- sharpness, exposure, white balance;
- star photo bonus;
- segmentation과 obstacle mask;
- seam blending과 de-lighting;
- observed/generated coverage와 confidence.

관측되지 않은 UV만 completion model의 대상이며, generated texture가 raw observed texture를 덮어쓰지 않게 한다.

## 9. Pixel3DMM 원본 crop을 바꾸게 된 이유

이 부분은 실제 디버깅을 통해 모델의 전처리 계약을 다시 이해한 대표 사례다.

### 원래 Pixel3DMM 전처리의 가정

공식 pipeline은 주로 동일한 사람이 이어서 등장하는 video frame을 처리한다. `static_crop=True` 경로는 여러 frame의 face detection bbox를 평균내 하나의 안정된 공통 crop을 사용할 수 있다.

영상에서는 유효한 가정이다.

- frame 해상도가 동일;
- 사람이 비슷한 위치와 크기에 있음;
- camera framing이 크게 바뀌지 않음;
- bbox 절대 좌표를 평균내도 같은 얼굴 주변을 가리킴.

### Hair App 입력에서 깨진 이유

Hair App은 서로 다른 날과 camera framing에서 찍은 독립 사진을 사용한다.

- 해상도와 종횡비가 다름;
- 얼굴이 사진마다 다른 위치에 있음;
- 촬영 거리와 얼굴 크기가 다름;
- 정면, 3/4, profile이 섞임;
- 모자, 손, 제품, 전화기, 헤드폰, 머리카락 같은 obstacle이 존재.

이 독립 사진들의 bbox를 원본 pixel 좌표 그대로 평균내면 의미 없는 공통 box가 된다. 실제 8장 test에서 일부 crop은 얼굴 전체가 아니라 눈 위주만 남기고 코·입·턱을 잘랐다. 이 잘못된 crop은 뒤 FaRL segmentation에서 얼굴 재검출 실패와 빈 tensor 오류를 유발했다.

문제는 FaRL 자체보다 앞단의 video용 shared crop 가정을 독립 사진에 사용한 것이었다.

## 10. crop v1, v2, v3 실험과 배운 점

### V1: per-image bbox와 두 눈 roll

첫 개선은 사진마다 RetinaFace로 bbox와 5-point를 다시 검출하고, 두 눈을 수평으로 돌린 뒤 512×512로 만드는 것이었다.

좋아진 점:

- 사진마다 얼굴 위치와 scale이 정상화됨;
- 기존처럼 눈만 남는 crop이 사라짐;
- 정면과 3/4 view의 coverage가 좋아짐;
- 기울어진 정면 사진의 roll이 자연스럽게 보정됨.

문제:

- 강한 profile에서 가려진 눈 landmark가 코 주변에 잘못 찍힘;
- 잘못된 두 점을 정확하게 수평화하면서 오히려 잘못된 회전 발생;
- landmark가 불합리해도 warning이 없었음;
- 회전 시 source 경계 밖에 검은 fill이 생길 수 있었음.

판정은 `bbox/scale PASS`, `profile roll/warning gate FAIL`이었다.

### V2: landmark plausibility와 안전장치

V2는 두 눈만 보지 않고 눈·코·입 관계를 검사했다.

- profile 또는 가짜 눈으로 판단되면 사진은 유지하고 roll만 생략;
- 다중 얼굴 후보를 면적, confidence, 중심 위치로 비교;
- reflect padding과 observed-source validity mask;
- 양방향 source↔crop transform 저장;
- crop margin과 vertical offset 조정.

합성 unit test는 통과했지만 실제 결과에서 체감상 큰 개선은 제한적이었다. 핵심 문제는 roll 공식보다 입력 sparse landmark 자체의 정밀도였다.

### V3: 눈·코·입꼬리 5점 전체 도형

사용자 아이디어로 두 눈만 쓰지 않고 다음 다섯 점 전체가 정방향 얼굴 도형에 가까워지도록 roll을 계산했다.

```text
left eye       right eye
        nose
left mouth     right mouth
```

코를 anchor로 두고 네 상대 vector를 canonical template에 least-squares similarity fit했다. 한 눈이 틀려도 나머지 점이 rotation에 참여하도록 한 것이다.

수학 test에서는 알려진 roll을 복원했고 한쪽 눈 오류에도 eye-only보다 안정적이었다. 그러나 실사진에서는 RetinaFace의 5점이 정확한 동공 중심, 코끝, 입꼬리 끝이 아니라 alignment용 근사점이었다. 정교한 공식을 사용해도 입력 점의 한계를 넘지 못했다.

## 11. source audit 후 내린 crop 최종 결정

v1~v3을 계속 개선하기 전에 Pixel3DMM 공식 코드를 다시 읽었다. 여기서 중요한 사실을 확인했다.

- crop detector의 sparse 5점은 최종 FLAME fitting landmark가 아님;
- persistent crop 이후 PIPNet이 WFLW 98 landmark를 별도로 생성;
- tracker는 이 중 68-point mapping과 iris 96/97을 사용;
- normal, UV, silhouette, segmentation evidence와 함께 camera/head pose를 최적화;
- 공식 persistent crop은 roll normalization을 하지 않음.

따라서 crop 단계에서 부정확한 sparse point로 roll을 미리 제거할 필요가 없었다. 오히려 tracker가 추정해야 할 pose evidence를 잘못 바꿀 위험이 있었다.

최종 V4 전처리 구조:

```text
독립 원본 사진
  -> 사진별 official FaceBoxes detection
  -> confidence-first 주 얼굴 선택
  -> bbox margin 1.42
  -> 512x512 per-image crop
  -> roll은 원본 그대로 보존
  -> crop candidate와 source↔crop transform 기록
  -> final crop에서 official PIPNet WFLW 98
  -> official FaRL segmentation
  -> count gate + 사람이 보는 visual gate
  -> normal/UV inference
  -> shared-identity FLAME tracking
```

이 구조가 바꾼 것은 Pixel3DMM의 geometry model이 아니라 Hair App 독립 사진을 model input contract에 맞추는 persistent crop 부분이다. PIPNet 내부의 temporary ROI crop과 FaRL의 448 inference alignment는 각 모델 내부 좌표 처리를 위해 유지한다.

### confidence-first로 다시 고친 이유

V4 첫 candidate ranking은 큰 얼굴을 우선하려고 relative area에 높은 가중치를 줬다. profile stress image에서 FaceBoxes는 실제 얼굴 후보를 confidence `0.9352`로, 가슴/목 false positive를 `0.7161`로 검출했다. 그러나 false positive box가 더 커서 area-heavy custom score가 잘못된 후보를 골랐다.

FaceBoxes 자체는 실제 얼굴을 더 신뢰하고 있었으므로 official 방식처럼 confidence-first로 되돌렸다. 수정 뒤 8장 모두 실제 얼굴 crop이 선택됐고 Gate A를 통과했다.

이 사례의 교훈은 모델 출력 뒤에 붙인 custom heuristic이 pretrained detector의 올바른 판단을 망칠 수 있다는 것이다. 단순한 면적 규칙은 provenance로 남기되 baseline selection은 detector confidence를 우선한다.

## 12. Pixel3DMM V4를 실제로 돌리며 해결한 오류

2026-06-23 A100 Colab에서 V4를 실행하며 다음 문제를 순서대로 해결했다.

### 환경과 dependency

- PyTorch 2.7.0 + CUDA 11.8 환경 확인;
- A100 compute capability에 맞는 `TORCH_CUDA_ARCH_LIST=8.0+PTX`;
- `pytorch3d`, `nvdiffrast` build;
- official SSH clone을 Colab-compatible HTTPS clone으로 변경;
- FaceBoxes build 전에 Cython 설치;
- uv/normals checkpoint를 official code가 읽는 경로로 배치;
- Facer 최신 Torch index dtype에 `.long()` patch.

### FLAME asset 구조

처음에는 `FLAME2020.zip` 안에 `landmark_embedding.npy`와 masks가 모두 있다고 가정했지만 실제 배포 ZIP에는 없었다.

- `generic_model.pkl`과 FLAME2023 model 확인;
- Vertex Masks 별도 ZIP 설치;
- pinned DECA-compatible `landmark_embedding.npy` 다운로드;
- SHA-256과 required key 검증;
- runtime이 끊어지면 `/content`가 사라지므로 전체 설치를 다시 해야 한다는 점 기록.

### FaceBoxes import

embedded helper가 package import를 시도했지만 upstream `faceboxes_detector.py`는 `from detector import Detector`라는 legacy absolute import를 사용했다. official script처럼 FaceBoxesV2 directory를 `sys.path` 앞에 넣어 해결했다.

### crop primary-face selection

area-heavy score가 profile 사진에서 가슴/목 false positive를 선택했다. candidate metadata를 확인해 detector confidence-first로 바꾸고 8/8 crop을 재생성했다.

### PIPNet과 FaRL

- PIPNet 98 landmark는 8/8 export 성공;
- FaRL 617MB JIT weight 다운로드가 약 361MB에서 reset;
- curl retry/resume와 `torch.jit.load` integrity check 추가;
- segmentation 재실행 후 crop/meta/landmark/annotated/seg가 모두 8/8 통과.

### private artifact 보존

runtime이 사라져도 재현할 수 있도록 Drive bundle에 다음을 저장했다.

- raw input copy와 final crop;
- FaceBoxes candidate와 선택 bbox;
- source↔crop transform;
- PIPNet NPY, JSON, CSV, overlay;
- FaRL raw/color mask와 class histogram;
- visual overview;
- logs, config, commit, manifest;
- 모든 저장 파일 SHA-256.

private photo와 biometric artifact는 Git에 넣지 않는다.

### checkpoint 오류를 넘어서 첫 mesh까지

첫 normal inference에서 PyTorch 2.6+가 `torch.load`의 기본값을 `weights_only=True`로 바꾼 영향으로 official Lightning checkpoint 내부 `omegaconf.DictConfig` load가 거부됐다.

V4는 official Google Drive ID에서 받은 trusted Pixel3DMM checkpoint에 한정해 `load_from_checkpoint(..., weights_only=False)`를 명시하도록 수정했다. 이후 normal과 UV inference가 각각 8/8 완료됐고, 다음 설정으로 multi-photo FLAME tracking을 끝냈다.

```text
iters=100, global_iters=1500, batch_size=8
use_flame2023=True, ignore_mica=True, is_discontinuous=True
normal_super=2000, sil_super=1000
```

`canonical.ply`는 5,023 vertices와 9,976 faces를 가졌다. tracking result video에서 원본, source overlay, per-view fitted render를 8장 모두 확인했다. neutral identity shape는 입력마다 공유하고 camera, pose, jaw, expression은 사진마다 따로 최적화됐다.

첫 Plotly preview가 옆으로 누워 있고 flat gray라 형상을 알아보기 어려웠다. 이는 mesh 실패가 아니라 기본 camera/shading 문제였다. 또 `!pip`와 `%pip`가 notebook kernel과 다른 interpreter에 설치되어 `trimesh` import가 실패했으며, `sys.executable -m pip` 방식으로 고쳤다. 실행 노트북도 이 수정으로 최신화했다.

### 첫 개인화 검증

평균 FLAME와 fitted identity를 centroid 정렬한 뒤 vertex displacement를 측정했다.

- mean `3.73 mm`;
- RMS `5.50 mm`;
- p95 `11.37 mm`;
- max `25.02 mm`.

변형량만으로 정답을 증명할 수는 없지만 mean head를 그대로 반환하지 않았다는 점은 확인했다. 같은 fitted camera·pose·expression을 고정한 quick landmark shape-swap test에서는 mean FLAME error `7.1109 px`, fitted error `5.8803 px`, improvement `1.2306 px`로 약 `17.3%` 좋아졌고 fitted가 8/8 view에서 이겼다.

이 검증은 camera와 expression을 각 조건에서 다시 맞춘 완전한 control은 아니다. 이후 같은 8장 입력으로 MICA prior와 MICA init-only를 A/B했지만 fixed-context 채택 기준을 통과하지 못했다. 또한 identity shape를 zero로 고정하고 camera/pose/expression을 다시 맞춘 mean-FLAME control이 `5.7423 px`로 no-MICA fitted-shape의 `5.8803 px`와 동률 또는 소폭 우세였기 때문에, 현재 canonical identity shape가 강하게 개인화됐다는 claim은 약해졌다. 정확한 수치, 제한, loss 구조, 다음 실험은 `docs/pixel3dmm_v4.md`에 통합했다.

## 13. 현재 구조와 남은 일

현재 working architecture:

1. MediaPipe: capture guidance와 저비용 quality check;
2. Pixel3DMM: 첫 multi-photo hairless geometry baseline과 possible teacher;
3. Hair App UV baker: 실제 관측 픽셀을 common UV에 투영·가중 결합;
4. completion model: 관측되지 않은 UV만 보완;
5. DiffLocks/Im2Haircut/PERM 계열: independent strand hair 후보;
6. custom geometry module: scalp mapping, hairline fitting, deformation, collision correction;
7. GLB/Three.js: mobile interactive delivery;
8. optional 2D model: quality benchmark, auxiliary views, still-render refinement, fallback.

현재 완료되지 않은 핵심 단계:

- completed MICA versus no-MICA and MICA init-only A/B, followed by fully refitted mean-shape control;
- completed cross-context no-MICA fitted shape versus mean-shape validation on the private 19-view run, which did not validate no-MICA identity shape over the refitted mean-shape control;
- pending frozen-model-trio observed-photo texture comparison;
- 512 tracking resolution 및 float normal/UV precision A/B;
- 더 많은 identity와 capture condition에서 Pixel3DMM geometry 검증;
- 실제 multi-photo UV baker;
- strand hair baseline 비교;
- head/hair retargeting과 collision;
- mobile GLB viewer;
- asynchronous GPU job architecture;
- commercial-safe model/license replacement.

## 14. 무엇이 실패했고 무엇을 남겼는가

| 시도 | 결과 | 버리지 않고 남긴 것 |
| --- | --- | --- |
| StableHairV2 | 일반 portrait에서 identity와 artifact 문제 | hair-specific model도 제품 입력 검증이 필요하다는 원칙 |
| 범용 2D editor | 한 장의 품질 가능성은 있지만 rotatable consistency 부족 | identity scoring, mask, protected-region, retry/ranking |
| FLUX.2 tuning plan | 실제 학습 전에 3D로 전환 | multi-reference 연구, 2D benchmark, auxiliary view, render refinement |
| FastAvatar core 구상 | Gaussian과 editable UV mesh 요구가 충돌 | photorealistic benchmark와 future alternative |
| Pixel3DMM upstream static crop | 독립 사진 bbox 평균 때문에 얼굴이 잘림 | video와 independent-photo input contract 차이 |
| crop v1 | bbox/scale 개선, profile roll 실패 | per-image crop과 visual gate |
| crop v2 | 안전장치 강화, 체감 개선 제한 | warning, validity, reversible transform 개념 |
| crop v3 | 수학은 동작, sparse landmark 정밀도 한계 | 공식 downstream landmark를 먼저 확인해야 한다는 교훈 |
| V4 area-heavy face ranking | 큰 false positive 선택 | candidate provenance와 confidence-first baseline |
| PyTorch `weights_only=True` | official Lightning checkpoint load 실패 | trusted pinned checkpoint에 한정한 compatibility patch |
| `!pip`/`%pip` trimesh 설치 | active kernel에서 import 실패 | `sys.executable -m pip`로 interpreter 일치 |
| Pixel3DMM V4 no-MICA | 8장 end-to-end 성공, quick same-camera landmark error 약 17.3% 개선; MICA prior/init-only 탈락; fully refitted mean-shape control은 landmark 기준 동률/소폭 우세 | 첫 end-to-end geometry artifact이나 personal identity-shape claim은 추가 검증 필요 |

## 15. 프로젝트를 진행하며 세운 원칙

1. README의 예시가 좋아 보여도 같은 Hair App 입력으로 돌리기 전에는 채택하지 않는다.
2. baseline 실패 원인을 이해하기 전에 fine-tuning하지 않는다.
3. H100은 계산량 문제를 줄이지만 missing view, wrong representation, bad data, license를 해결하지 않는다.
4. head geometry, face appearance, hair geometry를 분리한다.
5. raw observed data를 AI-generated result로 덮어쓰지 않는다.
6. 관측 영역과 추정 영역, confidence를 명시한다.
7. model code, weights, dataset, dependency license를 각각 확인한다.
8. 현재 구현과 미래 계획을 문서에서 구분한다.
9. 실패한 실험은 실행 경로에서는 치우되, 판단 근거와 교훈은 history에 남긴다.
10. 최종 모델 선택은 고정 선언이 아니라 날짜, 근거, failure condition이 있는 임시 결정으로 남긴다.

## 16. 포트폴리오에서 설명할 수 있는 이야기

Hair App은 처음부터 완성된 3D 설계로 시작하지 않았다. 실제 사용자가 원하는 헤어스타일 합성을 만들기 위해 hair-specific 2D 모델을 재현했고, 일반 portrait에서 identity가 무너지는 실패를 확인했다. 더 강한 범용 editor와 FLUX.2 fine-tuning을 조사했지만, 사용자가 원하는 경험을 다시 정의하면서 한 장의 예쁜 이미지보다 회전 가능하고 헤어를 교체할 수 있는 3D asset이 핵심이라는 결론에 도달했다.

그 뒤 단순히 3D 모델 이름을 고른 것이 아니라 representation을 `editable head mesh + observed UV + independent strand hair`로 분리했다. Pixel3DMM을 실제 A100 환경에서 재현하면서 video용 crop 가정이 독립 셀카에 맞지 않는 문제를 찾았고, 여러 번의 crop 실험과 official source audit를 통해 per-image no-roll 구조로 수정했다. 실패한 heuristic은 candidate metadata로 원인을 확인해 confidence-first로 되돌렸고, 모든 전처리 artifact와 manifest를 재현 가능한 형태로 보존했다.

최종적으로 crop, WFLW-98, FaRL, normal, UV, tracking을 8/8 입력에서 끝내고 첫 end-to-end FLAME geometry artifact를 얻었다. 평균 FLAME와의 vertex 차이만 보는 데서 멈추지 않고 같은 camera/pose/expression의 landmark diagnostic을 만들어 fitted shape가 8/8 view에서 더 낫다는 수치도 확인했다. 이후 MICA prior와 MICA init-only A/B를 추가했고, 둘 다 fixed-context 채택 기준을 통과하지 못했다. 더 강한 fully refitted mean-shape control은 no-MICA fitted shape와 landmark 기준 동률 또는 소폭 우세였으므로, 현재 mesh를 강하게 검증된 개인 두상이라고 말하지 않기로 정리했다.

그 다음 제품 쪽 스캔 플로우도 연구 결론에 맞춰 바꿨다. 기존 preview 중심 스캔을 `front`, `left_45`, `right_45`, `left_profile`, `right_profile`, `hairline` 6단계 geometry capture로 바꾸고, backend가 raw samples와 별도로 `selected_3dmm/` reconstruction input bundle을 만들도록 했다. 사용자는 실제 본인 셀카를 고르고 있으며, 다음 실험은 repo 밖 private selfie folder와 새 app-scan `selected_3dmm/` frames를 합쳐 Pixel3DMM no-MICA와 mean-shape control을 다시 돌리는 것이다.

이 과정의 가치는 특정 모델 하나를 사용했다는 데 있지 않다. 문제 정의, 실제 입력 검증, 실패 원인 분석, representation 변경, 문서와 코드의 동기화, privacy와 license 경계까지 포함해 연구 prototype을 제품 구조로 발전시킨 경험에 있다.

## 17. 2026-06-24 private 19-view geometry and texture handoff

The private data experiment combined selected selfies with the app scan's selected 3DMM frames and reran the Pixel3DMM V4 no-MICA path plus the fully refitted mean-shape control on 19 clean views.

What succeeded:

- no-MICA Pixel3DMM generated a usable `canonical.ply`;
- the full no-MICA tracking folder was preserved in private Drive storage;
- the mean-shape control was rerun and its identity shape was effectively zero;
- raw FLAME, fitted mean-shape control, and personal no-MICA were visualized side by side, and the three meshes are visibly different.

What did not pass:

```json
{
  "views": 19,
  "no_mica_context_gain_px": 0.19544085823244828,
  "mean_shape_context_gain_px": -0.6038492081183984,
  "no_mica_wins_both_contexts": false
}
```

The landmark-only gate still does not prove that the personal no-MICA identity shape is better than the refitted mean-shape control. The practical decision was not to discard the personal mesh, because the bare geometry looks different and the final product will be judged with real face appearance applied. The next phase is therefore a controlled texture comparison:

1. freeze raw FLAME template, fitted mean-shape control, and personal no-MICA as a private model trio;
2. keep those PLY files and their private manifest outside Git;
3. implement the custom observed-photo face texture baker;
4. apply the same photo evidence to all three meshes;
5. decide visually and with coverage/reprojection diagnostics which candidate should become the temporary development head.

The generic helper for freezing the private trio is tracked at `experiments/milestone1_geometry_bakeoff/freeze_model_trio_for_texture.py`. Its generated outputs are biometric runtime artifacts and must never be committed.

After the model-trio freeze, the private Drive data was consolidated into a clean person-oriented layout:

```text
MyDrive/hair_app/
  input/<person>/
  output/<person>/
  shared/models/
  data_layout_manifest.json
```

The current user data now includes selfies, scan frames, the clean 19-image Pixel3DMM input set, preprocessing outputs, tracking outputs, validation artifacts, and the three-mesh texture handoff. The legacy girl experiment is preserved under the same style of `input/<person>/` and `output/<person>/` folders. Old staging, trash-review, and crop-test folders are no longer the source of truth and can be removed after manual verification of the cleaned layout.

## 18. 2026-06-26 Texture Baker v1 review and strategy reset

After the model-trio handoff, the first observed-photo texture baker was built
and pushed. It loads the private Drive layout, creates observed atlases from
crop RGB plus Pixel3DMM UV maps and segmentation labels, writes coverage,
confidence, and source-view maps, and renders all Juseop/Eunchae mesh
candidates with material fallback and diagnostic eye overlays.

What succeeded:

- the cleaned private Drive entrypoint works for both people;
- the same observed texture can be attached to all three frozen mesh candidates;
- black texture holes can be reduced with material fallback;
- low-confidence texture samples can be hidden in diagnostic renders;
- a one-file comparison sheet can show Juseop and Eunchae candidates across yaw views.

Representative private output:

```text
output/_comparison/face_texture_model_comparison_8view_wideface_eyes_conf5_v4.png
```

What failed:

- the result is visually far below product quality;
- UV splatting still leaks hair/headwear/occlusion and low-confidence artifacts;
- orthographic review cameras are not enough to compare against real selfies;
- fallback materials make the render easier to inspect but do not solve texture realism;
- eye overlays are only diagnostic, not final eye assets;
- the three base meshes cannot yet be judged fairly because texture quality is the bottleneck.

The strategic decision changed from "tune the v1 baker" to "build Texture Baker
v2." The product target was also clarified: not a perfect 360-degree personal
scan, but a front-to-45-degree personal bald head substrate that supports
realistic hair fitting. Rear head, hidden scalp, and low-confidence regions may
use generic fallback or completion.

Texture Baker v2 direction:

1. keep the user input UX unchanged: unconstrained selfies plus app scan;
2. use app scan frames for stable geometry/camera coordinates;
3. use selfies mainly as high-detail texture evidence;
4. score frames and selfies for quality, pose, expression, segmentation,
   landmarks, and occlusion;
5. use fitted cameras, z-buffer visibility, view-angle weighting, color
   normalization, confidence maps, and source-photo provenance;
6. evaluate with a front-focused sheet at `0`, `±15`, `±30`, and `±45` degrees;
7. add per-user render-to-selfie optimization after observed baking is stable.

That optimization is initially explicit per-user logic, not neural network
training. Later, if enough examples exist, a network can learn to predict good
texture/shape updates faster and use the explicit optimization only as a final
refinement.

## 19. 2026-06-26 Texture Baker v2 hybrid front45 run

Texture Baker v2 was implemented after the v1 visual quality reset. It keeps
the input policy unchanged: ordinary selfies plus app scan frames, with no
stricter user capture requirements.

What changed:

- added `experiments/texture_baker/evidence_quality_report.py` for blur, face
  size, pose, exposure, eye/mouth state, landmark, segmentation, occlusion, and
  skin-reference scoring;
- added `experiments/texture_baker/texture_baker_v2.py` for a hybrid observed
  atlas with fitted-camera projection diagnostics, z-buffer visibility,
  confidence/source maps, color normalization, material fallback compatibility,
  and Pixel3DMM UV correspondence detail for the central face;
- added `--texture-name` to `make_texture_comparison_sheet.py` so review sheets
  can point at a specific private texture run;
- changed preview defaults to `observed_v2_camera_visibility_front45_preview`.

Private outputs from the current local run:

```text
output/<person>/texture_baker/observed_v2_camera_visibility_front45_preview/
output/_comparison/face_texture_model_comparison_front45_v2.png
output/_comparison/face_texture_model_comparison_front45_v2.json
```

Observed result:

- coverage improved versus the first pure camera-projection attempt: roughly
  `33.5%` for Juseop and `30.3%` for Eunchae in the latest local run;
- front-to-45-degree review renders are easier to inspect because black holes
  are largely hidden by material/confidence fallback;
- central face identity is more readable than v1/v2-camera-only, but still far
  below product quality;
- Juseop still shows strong lighting/color seams and forehead artifacts;
- Eunchae still shows forehead/headband or hair contamination;
- diagnostic eye overlay is visible but not final-quality eye rendering.

Decision:

- keep all three base mesh candidates active;
- do not choose a mesh winner from this sheet yet;
- next work should focus on completion/occlusion cleanup: remove hair/headwear
  leakage from observed skin, fill low-confidence forehead/scalp/neck with
  plausible skin material, improve eyes, then revisit fitted-camera
  selfie-render comparison.

Follow-up cleanup/completion pass:

- added `experiments/texture_baker/texture_cleanup_completion.py`;
- it preserves `base_color_observed.png` and writes
  `base_color_cleanup_completed.png` plus cleanup/replacement masks beside the
  private v2 atlas;
- it removes low-confidence or color-outlier skin/scalp/neck texels from review
  use and replaces unobserved forehead, scalp, neck, boundary, and ear regions
  with simple skin materials;
- generated
  `output/_comparison/face_texture_model_comparison_front45_v2_cleanup.png`;
- the cleanup sheet reduces black holes and obvious headwear/hair leakage, but
  it also makes hidden scalp/neck flatter. Central face color seams, real eye
  assets, and fitted-camera selfie comparison remain unsolved.

## 20. 2026-06-26 Texture Baker v3 iterative bake

After the v2 cleanup and fitted-camera selfie comparison, the user rejected the
texture quality as still far below product standard. The key correction was to
stop treating the problem as "fill a few black holes" and instead build a more
controlled avatar-texture loop:

```text
fixed scan/base geometry
  + selected selfies and scan crops
  -> direct UV evidence
  -> whole-face bad/empty texel repair
  -> per-iteration review and metrics
  -> early clean final instead of over-smoothed last pass
```

Implemented:

- `experiments/texture_baker/texture_baker_v3.py`;
- two variants: `v3_no_lighting` and `v3_lighting_normalized`;
- frame filtering with a stricter default `--min-score 0.62`;
- weighted multi-frame seed texture instead of a single best-photo patchwork;
- optional fitted-camera projection pass, kept off by default because it still
  adds forehead/mouth noise;
- whole-face repair: neighbor fill, mirror fill, material fallback, seam
  smoothing, and skin coherence cleanup;
- per-iteration outputs for `0..5`: texture, confidence, observed mask, filled
  mask, metrics, fitted-camera comparison sheet, and front-to-45 review sheet;
- final texture selection from the earliest clean-enough iteration, usually
  `iter_01`, because later iterations reduce numeric error but visibly flatten
  identity details.

Private outputs from the run:

```text
output/<person>/texture_baker/v3_v3_no_lighting/
output/<person>/texture_baker/v3_v3_lighting_normalized/
output/_comparison/v3_주섭_variant_overview.png
output/_comparison/v3_은채_variant_overview.png
```

Selected final metrics from the local private run:

| Person | Variant | Selected final | Mean luma error | Seam score | Observed coverage |
| --- | --- | ---: | ---: | ---: | ---: |
| Juseop | no lighting | 1 | 27.48 | 0.640 | 34.2% |
| Juseop | lighting normalized | 1 | 27.12 | 0.631 | 34.3% |
| Eunchae | no lighting | 1 | 36.99 | 1.027 | 23.5% |
| Eunchae | lighting normalized | 1 | 37.16 | 1.114 | 23.6% |

What improved:

- black holes and the worst broken texel patches are mostly removed;
- front-to-45 sheets are easier to inspect than v1/v2;
- selected final iteration avoids the worst late-iteration flattening;
- lighting normalization is slightly better for Juseop by the current metrics.

What still failed:

- output is not product-quality;
- face identity is too soft and avatar-like;
- eyes, eyelids, mouth interior, lips, and brows are not handled by proper
  assets/materials;
- Eunchae still has lower useful coverage and visible forehead/hair/headwear
  contamination risk;
- repeated residual iterations can improve loss while making the image look
  worse to a human.

Current decision:

- keep all three base mesh candidates active;
- do not choose a mesh winner from v3;
- next texture work should improve eye/mouth materials, feature preservation,
  and stronger but safer fitted-camera texture refinement before any geometry
  correction.

## 21. 앞으로 기록을 추가하는 형식

새로운 중요한 실험이나 방향 전환이 생기면 다음 형식으로 이 문서에 추가한다.

```text
날짜:
당시 목표:
선택한 모델/구조:
선택 이유:
실제로 실행한 것:
성공한 것:
실패한 것:
원인:
수정 또는 방향 전환:
현재 남긴 자산/지식:
다음 검증:
관련 commit/document:
```

완성된 프로젝트를 돌아볼 때 결과만 보지 않고, 판단이 바뀐 이유와 그때 얻은 지식까지 설명할 수 있도록 계속 갱신한다.
