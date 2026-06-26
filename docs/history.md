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

이 검증은 camera와 expression을 각 조건에서 다시 맞춘 완전한 control은 아니다. 이후 같은 8장 입력으로 MICA prior와 MICA init-only를 A/B했지만 fixed-context 채택 기준을 통과하지 못했다. 또한 identity shape를 zero로 고정하고 camera/pose/expression을 다시 맞춘 mean-FLAME control이 `5.7423 px`로 no-MICA fitted-shape의 `5.8803 px`와 동률 또는 소폭 우세였기 때문에, 현재 canonical identity shape가 강하게 개인화됐다는 claim은 약해졌다. 정확한 수치, 제한, loss 구조, 다음 실험은 이 파일의 Pixel3DMM archive 섹션에 통합했다.

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

## 22. 2026-06-27 FaceBuilder/KeenTools pivot and automation verification

After Texture Baker v3, the user judged the output quality as far below the
product bar. This became the point where the project stopped treating the
custom Pixel3DMM/FLAME texture baker as the main path for visual quality.

The important user constraint stayed the same:

```text
ordinary selfies + app scan frames
```

The app cannot require studio photographs, strict angle guides, manual pin
editing, or a human operator. A user should upload normal selfies and complete
the in-app scan. The system must handle scoring, filtering, alignment, and
fallback internally.

### Why the custom texture-baker path was demoted

Texture Baker v1/v2/v3 was useful, but it exposed a product-level mismatch:

- a segmented 2D face cannot simply be pasted onto a fixed 3D mesh;
- every photo must be aligned to the 3D head with accurate camera/pose;
- small projection errors create very visible seams around the nose, mouth,
  forehead, and eyes;
- photo lighting differences make skin patches disagree;
- occlusions such as hair, headwear, glasses, hands, phones, and shadows can
  poison the texture;
- filling holes can remove black regions but also flattens identity detail;
- repeated repair iterations can lower numeric loss while visually destroying
  nose, mouth, lips, skin texture, and face volume;
- the output quality was too low to choose among the three base mesh candidates.

The practical conclusion was: the v3 baker remains a research record and source
of reusable post-processing ideas, but it should not be the main engine for the
next product iteration.

### External engine review

The user asked about MetaHuman, Polycam, and KeenTools.

The working assessment:

- MetaHuman can be useful as a high-quality avatar/reference ecosystem, but it
  is not the immediate lightweight server path for an automatic bald-head hair
  app pipeline.
- Polycam is useful as a scanning-product reference, but it is not directly
  aligned with the current selfie-plus-app-scan input contract.
- KeenTools FaceBuilder is the most relevant because it fits head geometry and
  photo camera positions from multiple images inside Blender.

The key conceptual difference:

```text
FaceBuilder:
  photos + pins/landmarks
  -> jointly adjusts face/head shape and per-photo camera alignment
  -> builds texture after the model and photos match

Our Texture Baker v3:
  mostly fixed Pixel3DMM/FLAME mesh
  -> tries to paste/repair photo pixels on top
  -> does not strongly refit shape/cameras from all photos together
```

This explains why FaceBuilder can start from a visibly better head even before
Hair App-specific post-processing.

### Manual FaceBuilder result

The user manually used Blender + FaceBuilder with Juseop photos and exported
OBJ/MTL/texture files. The visual result was significantly better than the
custom Texture Baker v3 sheets.

This did not mean FaceBuilder output was immediately production-ready. It meant
it was a stronger substrate. Hair App still needs to:

- automate the process;
- reject or downweight bad photos;
- create review sheets;
- remove hair/headwear/shirt/background leakage;
- handle scalp, neck, rear head, eyes, mouth, lips, ears, and material cleanup;
- export mobile GLB;
- fit hairstyle geometry to the result.

### Blender and KeenTools code investigation

The user asked whether the project could avoid Blender and extract only the
needed FaceBuilder engine code.

Local findings:

```text
Blender executable:
C:\Program Files\Blender Foundation\Blender 5.1\blender.exe

KeenTools extension folder:
C:\Users\User\AppData\Roaming\Blender Foundation\Blender\5.1\extensions\user_default\keentools
```

The visible Python files in the add-on are mostly Blender integration, UI,
operator, loader, and control code. The core FaceBuilder solving logic is in the
compiled local `pykeentools` `.pyd` binary. It is code, but it is compiled native
binary code, not readable Python source. The project should treat it as a
licensed black-box dependency and should not reverse-engineer it or bypass
licensing.

Therefore the practical near-term server design is:

```text
backend job
  -> launch Blender in background mode
  -> drive KeenTools/FaceBuilder via script
  -> save private mesh/texture/blend/review outputs
  -> post-process and export app-ready assets
```

Blender is not the app viewer. Blender is the server-side 3D production engine.
The app should receive mobile assets such as GLB and display them with Three.js
or another mobile 3D viewer.

### Headless automation verification

Automation feasibility was tested locally on 2026-06-27.

Verified:

- Blender 5.1.2 runs in background mode.
- KeenTools 2026.2.0 loads in background mode.
- `pykeentools` imports successfully.
- A FaceBuilder object can be constructed from script.
- `detect_faces` is callable.
- `detect_face_pose` is reachable.
- preset pin solving is reachable.
- TextureBuilder APIs are visible and callable.

Existing-scene probe:

- The user's private `C:\Users\User\Desktop\blender.blend` scene contained one
  FaceBuilder head, 11 cameras, and 6 cameras with pins before probing.
- Re-aligning an already pinned camera succeeded.
- Of five unpinned cameras, four code-only auto-align attempts succeeded.
- One camera failed with zero detected faces, likely the eyeglasses selfie the
  user had already noticed.
- Texture baking ran in background mode and saved a private PNG.

Empty-scene automation v0:

- A new Blender background session was started from an empty scene.
- A FaceBuilder head was created from script.
- Two private Juseop photos were selected from the private photo folder.
- Both were added as FaceBuilder cameras.
- One photo auto-aligned and received preset pins.
- One photo failed face detection.
- Texture baking still succeeded from the aligned photo.
- A private `.blend`, private texture PNG, and `result.json` were saved under
  ignored `private_outputs/facebuilder_bridge/`.

Conclusion: full product automation is not done, but the important bridge is
real. Codex can run headless Blender, drive key FaceBuilder operations, inspect
results, and iterate scripts.

### Updated project decision

The current near-term direction is:

```text
ordinary selfies + app scan frames
  -> photo/frame scoring
  -> automated FaceBuilder solve in headless Blender
  -> private mesh + texture + blend
  -> Hair App bald-head post-processing
  -> front-to-45 review sheets
  -> hairline/scalp fitting
  -> collision correction
  -> mobile GLB
```

Pixel3DMM/FLAME and Texture Baker v1/v2/v3 remain as historical research,
fallbacks, and sources of reusable ideas. They are not the main quality path
unless FaceBuilder fails a specific gate or the user explicitly asks to return
to them.

### Immediate next work

1. Build FaceBuilder automation v1 for the Juseop/Eunchae private photo folders.
2. Add photo/frame scoring before FaceBuilder:
   - blur;
   - face detection confidence;
   - pose/yaw/pitch/roll;
   - lighting/exposure;
   - glasses, hair, headwear, hand, phone, shadow occlusion;
   - eyes closed;
   - mouth open;
   - landmark stability where available.
3. Add retry/reject logic for failed auto-align photos.
4. Save private manifests for selected/rejected/aligned/baked outputs.
5. Generate review sheets at 0, +-15, +-30, +-45 degrees.
6. Define and implement bald-head post-processing:
   - remove hair/headwear/shirt/background leakage;
   - fill scalp, neck, rear head, and low-confidence skin regions;
   - improve eyes, mouth, lips, ears, brows, and skin material;
   - preserve confidence/provenance maps.
7. Decide whether to use FaceBuilder mesh directly or transfer to a controlled
   Hair App mesh only after reviewing better FaceBuilder exports.

### Relationship to deleted standalone docs

After this pivot, standalone active docs for old engines are no longer useful if
they make the project look like Pixel3DMM or Texture Baker is still the main
path. Their detailed contents are archived below inside this `history.md` file,
and the standalone files are deleted from the active document set.

## 23. Archived former standalone document: `docs/pixel3dmm_v4.md`

This section preserves the detailed Pixel3DMM V4 document that used to live as a
separate active Markdown file. It was moved here on 2026-06-27 because
Pixel3DMM/FLAME is no longer the main engine path. The content remains valuable
as experiment history, failure analysis, and fallback reference.

---
# Pixel3DMM V4 Baseline: Contract, Live Results, and Next Experiments

Last synchronized: 2026-06-26

Status: **Geometry baseline and three-mesh handoff complete; Texture Baker v3 implemented as an iterative research baker but still below product quality; next work is eye/mouth materials, feature preservation, and safer fitted-camera texture refinement**

Executable notebook: `experiments/milestone1_geometry_bakeoff/pixel3dmm_colab_v4.ipynb`

Audited Pixel3DMM commit: `fcd1fa973c7715b02a8948dfc679dff53cf85924`

## 1. Why the Notebook and This Document Are Separate

The notebook and this document both use the name V4, but they do not duplicate the same role.

- `pixel3dmm_colab_v4.ipynb` is the executable, output-free Colab pipeline.
- This file is the human-readable contract, source audit, error history, measured result, interpretation, and next experiment plan.
- Private input photos, crops, landmarks, masks, predicted maps, meshes, videos, and Drive run folders stay outside Git.

Keeping executable code under `experiments/` and long-lived knowledge under `docs/` makes it possible to rerun the experiment without embedding private outputs in the repository. All former Pixel3DMM preprocessing, live-run, and experiment README material has been consolidated here.

## 2. Executive Result

The first complete Hair App Pixel3DMM baseline now works from eight independent photos through a reproducible FLAME geometry artifact. The mesh is useful, but the later mean-shape control means it should not yet be called a strongly validated personalized head.

```text
8 source photos
  -> 8 independent 512x512 no-roll face crops
  -> 8 PIPNet WFLW-98 landmark sets
  -> 8 FaRL face-part segmentations
  -> 8 predicted normal maps
  -> 8 predicted UV correspondence maps
  -> joint multi-photo FLAME tracking
  -> canonical.ply + per-view tracking renders
```

Confirmed live on an NVIDIA A100-SXM4-80GB:

- environment and CUDA extension checks passed;
- all required FLAME assets passed;
- crop passed 8/8;
- PIPNet WFLW-98 landmarks passed 8/8;
- FaRL segmentation passed 8/8;
- normal inference passed 8/8;
- UV inference passed 8/8;
- multi-photo tracking completed;
- `canonical.ply` contains 5,023 vertices and 9,976 faces;
- official tracking result video and all eight source/fitted overlays were visually inspected;
- the fitted identity shape beat the mean FLAME shape in the quick landmark diagnostic on all 8/8 views.

The correct conclusion is:

> V4 is a successful, reproducible first geometry baseline. It demonstrably personalizes the mean FLAME head, but it does not yet prove production-grade identity or measured hidden-scalp accuracy.

## 3. Exact Live Configuration

### 3.1 Runtime and pinned components

| Component | Version, commit, or source |
| --- | --- |
| Pixel3DMM | `fcd1fa973c7715b02a8948dfc679dff53cf85924` |
| Python environment | conda `p3dmm`, Python 3.9 |
| PyTorch | `2.7.0+cu118` |
| torchvision | `0.22.0+cu118` |
| torchaudio | `2.7.0+cu118` |
| PyTorch3D | `75ebeeaea0908c5527e7b1e305fbc7681382db47` |
| nvdiffrast | `253ac4fcea7de5f396371124af597e6cc957bfae` |
| Facer | `ddd35c76ff840174b8a5403ad1c1255e37b8782b` |
| PIPNet | `b9eab58816437403a34aa5bc3adeafe5081fd36b` |
| Landmark embedding fallback | pinned DECA commit `a11554ae2a2b0f3998cf1fa94dd4db03babb34a2` |
| DECA embedding SHA-256 | `8095348eeafce5a02f6bd8765146307f9567a3f03b316d788a2e47336d667954` |
| GPU used | NVIDIA A100-SXM4-80GB |

The user also has H100 access. Compute availability allows higher-resolution and fine-tuning experiments, but it does not recover unobserved scalp geometry, correct a wrong representation, resolve licenses, or replace data quality.

### 3.2 Final crop and preprocessing configuration

| Item | V4 value |
| --- | --- |
| Face detector | official FaceBoxesV2 |
| Candidate selection | highest FaceBoxes confidence |
| Processing unit | every source photo independently |
| Requested square margin | `1.42` |
| Persistent crop | `512x512` |
| Roll normalization | disabled |
| Landmark topology | PIPNet WFLW 98 |
| Segmentation | FaRL `celebm/448` |
| Source type | independent/discontinuous photos |

### 3.3 Tracking configuration used for the baseline

```text
iters=100
global_iters=1500
batch_size=8
include_neck=False
w_exp=0.1
use_mouth_lmk=False
w_shape=0.01
w_shape_general=0.001
normal_super=2000.0
sil_super=1000.0
use_flame2023=True
ignore_mica=True
is_discontinuous=True
```

The resulting run folder name contained `_noMICA_uv2000.0_n2000.0`. `ignore_mica=True` is important: the current result starts without a MICA identity prior and became the control for the MICA A/B tests. Those follow-ups did not pass the adoption gate, so this no-MICA run remains the active measured baseline.

## 4. What Each Intermediate Output Means

### 4.1 Crop

The crop does not reconstruct the face. It creates a stable per-photo coordinate frame with comparable face scale and enough forehead, jaw, and side context for the downstream networks.

### 4.2 PIPNet WFLW-98 landmarks

The 98 landmarks describe two-dimensional face feature locations on each final crop. They include face contour, brows, eyes, nose, mouth, and two iris-related points. They support camera, pose, expression, and selected landmark losses; they are not the complete 3D answer.

### 4.3 FaRL segmentation

The colored preview is a semantic face-part label map, not a UV map. It separates regions such as skin, hair, eyes, brows, nose, lips, and background. Pixel3DMM primarily uses it to obtain face silhouette and valid-region evidence.

### 4.4 Predicted normal map

A normal map predicts the direction that each visible surface point faces. It provides local 3D shape evidence: nose curvature, cheek orientation, brow depth, and other surface changes. The RGB-like colors encode directions, not skin color.

### 4.5 Predicted UV map

The Pixel3DMM UV prediction is a dense correspondence map. For each visible image pixel it predicts where that point belongs on the canonical FLAME face surface. It answers “which canonical face point is this pixel?” rather than “what skin color should this point have?”

This is different from the future Hair App face texture. The future UV baker will use camera, visibility, and these surface correspondences to project actual photographed pixels into a common texture atlas.

### 4.6 FLAME tracking

The tracker jointly adjusts:

- one shared identity shape across all photos;
- a separate camera for each photo;
- separate head and jaw pose for each photo;
- separate expression parameters for each photo.

It repeatedly renders the current FLAME estimate and compares it with observed or predicted evidence. The user does not provide a ground-truth 3D head; normal, UV, silhouette, and landmark agreement provide self-supervised fitting targets.

## 5. Official Source Audit and Why the Crop Was Changed

### 5.1 Official order

The audited upstream order is conceptually:

```text
input frames
  -> FaceBoxes crop
  -> PIPNet WFLW-98
  -> FaRL segmentation
  -> Pixel3DMM normal/UV network
  -> FLAME optimization
```

There are three different landmark roles that must not be confused:

1. **Crop detection:** FaceBoxes locates a face box before the persistent crop.
2. **Fitting landmarks:** PIPNet produces WFLW-98 on the final crop.
3. **Rendered landmarks:** FLAME projects its own 3D landmark embedding into each camera so the tracker can compare prediction and observation.

### 5.2 Why an apparent second crop exists

PIPNet/FaRL may perform a temporary internal re-detection and alignment because FaRL expects a `448x448` aligned face ROI. That temporary ROI is only a network input transform. Its segmentation result is mapped back to the persistent `512x512` crop coordinate system.

V4 therefore preserves two different concepts:

- one persistent, saved `512x512` crop used by the full pipeline;
- temporary internal ROIs that may be used by PIPNet/FaRL but never overwrite the persistent crop.

### 5.3 Root cause of the original broken crops

Upstream `static_crop=True` can average face boxes across frames of one continuous video, where every frame shares a coordinate system. Hair App supplied independent photos with different resolutions, locations, zooms, and orientations. Averaging absolute source-pixel boxes across those photos produced invalid crops: some images retained only eyes and forehead while nose, mouth, and chin were cut away.

The final fix is not a new face reconstruction model. It is an adapter that keeps the official FaceBoxes detector but processes each independent photo independently.

### 5.4 Why V4 does not rotate the persistent crop

Crop v1 through v3 tried to normalize roll before PIPNet:

| Version | Idea | What was learned |
| --- | --- | --- |
| v1 | RetinaFace box plus two-eye roll | box and scale improved, but sparse profile eye points were unreliable |
| v2 | five-point plausibility and profile skip | safer warnings, no decisive visual gain |
| v3 | nose-anchored five-point least-squares roll | geometry tests passed, but the sparse points were not exact pupil center, nose tip, and mouth corners |

The main problem was landmark semantics, not the angle formula. Pixel3DMM already estimates camera/head rotation after accurate PIPNet landmarks are available. Rotating the persistent input with weaker crop-time landmarks added interpolation and coordinate transforms without proven downstream benefit.

Current default:

> Normalize face location and scale once, preserve image-plane roll, then let PIPNet and the tracker estimate pose in the stage designed for it.

Roll normalization can return only as a controlled A/B test if downstream evidence shows that no-roll inputs fail.

## 6. Final V4 Preprocessing Contract

```text
private source photo
  -> apply EXIF orientation
  -> run FaceBoxes independently
  -> choose highest-confidence candidate
  -> save every candidate for diagnostics
  -> build a square box with requested margin 1.42
  -> move the square inside source bounds
  -> reduce margin only when the source is physically too tight
  -> resize once to 512x512
  -> do not rotate
  -> save source<->crop matrices and warnings
  -> run PIPNet WFLW-98
  -> run FaRL segmentation
  -> count and human visual gate
```

Candidate area and center scores remain metadata only. They must not outweigh detector confidence without a measured identity-aware selection strategy.

Obstacles such as hair, hands, a phone, headphones, hats, or a product are not automatic crop failures. Crop should locate the intended face; later segmentation and confidence logic should mark obstructed regions and reduce their geometry/texture weight. If two real people appear, confidence alone may select the wrong identity, so production capture will need identity continuity or explicit user confirmation.

### 6.1 Coordinate and metadata contract

- persistent crop size: `512x512`;
- crop origin: top-left;
- x increases right and y increases down;
- PIPNet normalized points are relative to the final crop;
- pixel position is `normalized_coordinate * 512`;
- every frame stores source size, chosen box, all candidates, warnings, and source-to-crop/crop-to-source `3x3` transforms;
- every derived artifact retains the source ID and pipeline version.

## 7. Live Error and Fix Record

This section records the failures that materially changed V4. It is intentionally detailed so a later runtime failure is not rediscovered from scratch.

### 7.1 Conda restart and ephemeral Colab state

`condacolab.install()` restarts Python. A full runtime loss also removes the conda environment, cloned repositories, `/content` assets, and generated outputs. Drive persists.

Rule: after a full runtime loss, run the complete notebook setup and complete FLAME installer again. Do not run a one-file recovery fragment against missing directories.

### 7.2 Google Drive mount

Observed:

```text
ValueError: mount failed
```

Recovery:

```python
from google.colab import drive
drive.mount('/content/drive', force_remount=True, timeout_ms=120000)
```

This was authentication/mount state, not a Pixel3DMM failure.

### 7.3 FLAME distribution mismatch

Drive contained `FLAME2020.zip`, `FLAME2023.zip`, and `FLAME_masks.zip`, but no ready `landmark_embedding.npy`. Earlier code incorrectly assumed it would always find RingNet files named `flame_static_embedding.pkl` and `flame_dynamic_embedding.npy`.

Observed:

```text
AssertionError: flame_static_embedding.pkl ... 찾지 못함
```

Final installer behavior:

1. extract valid FLAME archives;
2. install `generic_model.pkl`, `flame2023_no_jaw.pkl`, and `FLAME_masks.pkl`;
3. reuse an existing valid `landmark_embedding.npy` if present;
4. otherwise download the pinned DECA embedding;
5. verify its SHA-256 and the four required static/dynamic face-index and barycentric-coordinate keys;
6. assert every required asset exists before tracking.

### 7.4 Runtime loss during manual embedding recovery

Observed:

```text
FileNotFoundError: .../FLAME2020/landmark_embedding.npy
AssertionError: .../FLAME2020/generic_model.pkl
```

The runtime had changed and the destination directory plus other FLAME files were gone. Final rule: rerun the complete asset cell, not the failed embedding-only cell.

### 7.5 FaceBoxes legacy import

Observed:

```text
ModuleNotFoundError: No module named 'detector'
```

The legacy module uses `from detector import Detector`. V4 now adds the official `FaceBoxesV2` directory to `sys.path` before importing `faceboxes_detector`. Nested commands use `conda run --no-capture-output` so the real traceback remains visible.

### 7.6 Wrong face selected in the last profile image

The first custom score used `0.70 * area + 0.20 * confidence + 0.10 * centrality`. It selected a large chest/neck false positive instead of the face.

| Candidate | Meaning | Confidence | Relative area | Old score |
| --- | --- | ---: | ---: | ---: |
| 0 | actual profile face | `0.9352349` | `0.5601853` | `0.6665744` |
| 1 | chest/neck false positive | `0.7161046` | `1.0` | `0.8933956` |

FaceBoxes itself had ranked the face correctly. V4 reverted to official-like highest-confidence selection, retained other scores only as metadata, and passed 8/8 crops.

### 7.7 FaRL weight download interruption

Observed while downloading the approximately 617 MB JIT weight:

```text
ConnectionResetError: [Errno 104] Connection reset by peer
```

V4 now uses a resumable `curl` download with retries, writes to `.part`, moves only after completion, and validates the checkpoint with `torch.jit.load` before inference. The live retry produced segmentation 8/8.

### 7.8 PyTorch 2.6+ Lightning checkpoint behavior

Observed before normal inference:

```text
_pickle.UnpicklingError: Weights only load failed.
Unsupported global: GLOBAL omegaconf.dictconfig.DictConfig
```

PyTorch changed the default of `torch.load(weights_only=...)` to `True`. The official Lightning checkpoint includes trusted OmegaConf objects. V4 patches only the pinned official Pixel3DMM load:

```python
model = p3dmm_system.load_from_checkpoint(
    model_checkpoint,
    strict=False,
    weights_only=False,
)
```

This must never be generalized to unknown user-supplied checkpoints. After this fix, normal and UV inference succeeded 8/8.

### 7.9 Mesh preview package installed into the wrong interpreter

Observed after successful tracking:

```text
ModuleNotFoundError: No module named 'trimesh'
```

Both `!pip` and `%pip` could point at a different interpreter than the active notebook kernel after the conda/Colab setup. V4 now installs with the exact active interpreter:

```python
import sys, subprocess, importlib
subprocess.check_call([
    sys.executable, '-m', 'pip', 'install',
    '--no-cache-dir', '--upgrade', 'trimesh', 'plotly'
])
importlib.invalidate_caches()
```

The first Plotly view also used an unhelpful default camera and flat gray shading. That made a valid sideways face hard to inspect; it was a visualization issue, not evidence that tracking had failed. The official tracking video and fixed-view comparisons are the stronger visual gate.

### 7.10 Other compatibility hardening retained in V4

- use HTTPS rather than unavailable SSH dependency clones;
- install Cython before FaceBoxesV2 build;
- place normal and UV checkpoints in upstream-expected paths;
- cast Facer image indices to `.long()`;
- skip MICA preprocessing when `ignore_mica=True`;
- supply a zero MICA shape prior in the no-MICA control;
- use `batch_size=min(number_of_views, 16)`;
- correct duplicated upstream `iters` argument to `iters=100 global_iters=1500`;
- validate normal/UV output counts because upstream inference can catch a frame exception and continue;
- lower crop-internal PIPNet re-detection gate from `0.99` to `0.75`, while retaining count and visual gates;
- save raw logs, exact configuration, provenance, hashes, and environment information to Drive.

## 8. Generated Artifact Contract

The current private Drive source of truth has been cleaned into a person-oriented layout:

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

Older timestamped `runs/`, `inputs/`, `models/`, `comparisons/`, and crop-test folders were consolidated into this cleaned layout. Staging folders such as `_OLD_STAGING_AFTER_CLEAN_LAYOUT_*`, `_TRASH_REVIEW_*`, and `_REMOVE_FROM_KEEP_REVIEW_*` are review/delete candidates after the cleaned layout has been visually checked.

Expected private artifacts include:

```text
input/<person>/
  original source photos and app-selected scan frames
  cleaned Pixel3DMM input set
output/<person>/preprocessing/
  rgb/
  cropped/
  crop_meta/
  PIPnet_landmarks/
  PIPnet_annotated_images/
  landmarks_json/
  seg_og/
  seg_non_crop_annotations/
  p3dmm normals and UV maps
output/<person>/tracking/
  no-MICA and control tracking folders
output/<person>/models/
  model manifests and frozen candidate meshes
output/<person>/validation/
  overlays, metrics, and inspection sheets
shared/models/
  reusable non-person-specific assets
```

None of these biometric artifacts belongs in Git. Training use requires separate opt-in.

## 9. Geometry Validation Results

### 9.1 Mean FLAME versus fitted mesh displacement

After removing global translation by centroid alignment, vertex displacement from the mean FLAME shape to the fitted identity shape was:

| Metric | Result |
| --- | ---: |
| Mean displacement | `3.73 mm` |
| RMS displacement | `5.50 mm` |
| 95th percentile | `11.37 mm` |
| Maximum | `25.02 mm` |

Interpretation:

- the optimizer did not simply return the untouched mean FLAME head;
- visible changes in face depth and profile are substantial enough to treat the result as personalized;
- the largest values can occur at neck/scalp boundary regions and are not automatically identity improvements;
- displacement magnitude alone cannot prove that the changes are correct.

### 9.2 Same-camera shape-swap landmark diagnostic

The fitted identity and mean FLAME identity were rendered with the fitted run's same per-view camera, pose, and expression, then compared against PIPNet landmarks.

```json
{
  "views": 8,
  "mean_flame_average_error_px": 7.110900421740904,
  "fitted_average_error_px": 5.880312144215164,
  "average_improvement_px": 1.2305882775257402,
  "fitted_wins_views": 8,
  "mean_wins_views": 0
}
```

This is an average improvement of approximately `17.3%`, and the fitted shape won in every view. It confirms that the fitted identity explains the observed landmark locations better under the same cameras, poses, and expressions.

Limitation:

> This is a quick shape-swap diagnostic, not a fully fair independent baseline. A fairer comparison must rerun optimization with identity shape fixed to zero so camera, pose, and expression can refit for the mean-shape control.

The fully refitted mean-shape control was then run. Identity shape was forced to zero while camera, pose, expression, jaw, eyes, eyelids, and intrinsics were allowed to refit. The result was:

```json
{
  "views": 8,
  "mean_shape_refit_average_error_px": 5.742349992829476,
  "previous_no_mica_fitted_shape_average_error_px": 5.880312144215164
}
```

In that run the validation script reports fitted and mean as identical because the fitted identity shape is intentionally zero. This weakens the earlier landmark-only personalization claim: mean FLAME can match or slightly beat the no-MICA fitted-shape landmark score once camera, pose, and expression are allowed to refit. The current no-MICA output remains a working end-to-end geometry artifact, but the optimized identity shape should not yet be described as strongly validated personal head geometry.

### 9.3 Visual inspection

The official result showed, for each of the eight views:

- original crop;
- fitted mesh over the source image;
- a rendered per-view fitted shape.

The third panel must not be mislabeled as the neutral canonical mesh: it includes the view's pose and expression. `canonical.ply` is the shared neutral identity mesh.

Observed result:

- alignment followed front, oblique, tilted, and profile views coherently;
- profile views showed meaningful nose, lips, chin, and cheek depth;
- expressions differed by input as expected because expression is per view;
- scalp and rear head remain prior-driven where photos contain no direct evidence.

### 9.4 Optimizer loss record

The exact final scalar values printed by `track.py` were not pasted into chat, so they are not reconstructed or invented here. The available quantitative result is the post-run landmark diagnostic above, not the tracker's raw training objective.

This distinction matters because the tracking objective is a weighted sum of UV, normal, silhouette, selected landmark, shape, expression, pose, camera, symmetry, and optional prior terms with different units. A lower total objective is meaningful only under the same configuration. Future A/B runs must copy the raw tracking log and export at least:

- final and best total objective;
- each named loss component;
- iteration of the best checkpoint;
- exact weights and optimization size;
- runtime and GPU;
- NaN/exception/frame-skip counts.

The MICA comparison must report both the same post-run geometry metrics and these raw component losses. Do not compare one condition's total loss with another condition if their weights or active terms differ.

## 10. What Losses Actually Drive the Fit

It is inaccurate to describe the baseline as simply “98 landmarks + UV + normal.” The tracker receives PIPNet-98, maps the topology for its own landmark use, but the audited code does not apply one equally weighted loss to all 98 points.

Current important evidence:

- dense predicted UV correspondence;
- predicted surface normals;
- FaRL-derived face silhouette and valid regions;
- active eye contour landmarks;
- eye-closure constraints;
- left and right iris constraints;
- optional mouth landmarks, disabled in the current run;
- regularizers for shape, general shape, expression, pose, camera, and symmetry;
- optional MICA identity prior, disabled in the current run.

The full 68-point landmark loss in the audited tracker is not the main active term in this baseline; selected regions are used. `use_mouth_lmk=False` and the default mouth landmark weight leave mouth evidence mostly to dense normal/UV/silhouette and regularization.

This distinction matters: merely changing “98 landmarks” to “478 landmarks” would not improve the fit unless the tracker defines robust correspondences, region weights, visibility, confidence, and loss terms for those points.

## 11. Current Limitations

- Eight successful outputs do not mean every PIPNet point is reliable under fingers, products, headphones, hair, or extreme profile.
- FaRL is a face parser, not a complete general obstacle segmenter.
- Highest-confidence selection can still choose a different real person if multiple people appear.
- The normal and UV networks currently save 8-bit PNG predictions, losing precision.
- The tracker default optimization size is 256 even though persistent crops are 512.
- FLAME has stable, useful topology but only 5,023 vertices and a limited identity subspace; it cannot represent every pore, eyelid fold, cartilage detail, or arbitrary scalp shape.
- `ignore_mica=True` removes a potentially valuable identity prior.
- The quick identity diagnostic holds camera, pose, and expression fixed and is not the fully refitted control.
- Hair-covered crown and rear scalp remain inferred. More facial landmarks cannot create evidence for invisible scalp.
- This result is geometry only. It does not yet include the Hair App observed-photo UV texture, hairstyle reconstruction, retargeting, collision correction, or GLB.
- Pixel3DMM, FLAME, and related research assets require a separate commercial-license path.

## 12. Improvement Roadmap

The next changes should be introduced one at a time against this frozen no-MICA baseline.

### Completed: MICA identity-prior and init-only A/B

The same eight images and same non-MICA settings were tested with MICA enabled.

MICA's role:

- estimate a photo-based FLAME identity shape initialization/prior;
- give Pixel3DMM a better starting identity than mean FLAME;
- allow dense normal/UV/silhouette evidence to refine it across all views.

Result: MICA is not adopted as the default geometry path for this baseline.

MICA prior run:

- MICA preprocessing completed 8/8;
- MICA tracking produced `canonical.ply`, eight per-view meshes, and a result video;
- canonical displacement versus no-MICA after centroid alignment: mean `4.2749 mm`, median `3.2221 mm`, p95 `8.0128 mm`, max `17.0235 mm`;
- in the no-MICA camera/pose/expression context, MICA shape worsened average landmark error from `5.8803 px` to `7.2801 px`, losing 8/8 views;
- in the MICA camera/pose/expression context, MICA shape improved `6.0530 px` to `5.7006 px`, winning 5/8 views;
- native-run comparison improved only `0.1797 px`, but this is not a fixed-context comparison.

MICA init-only run:

- no-MICA context: MICA init-only shape worsened `5.8803 px` to `7.2036 px`, losing 8/8 views;
- MICA init-only context: MICA shape improved `5.9761 px` to `5.7245 px`, winning 5/8 views;
- native-run comparison improved only `0.1558 px`.

Interpretation:

- MICA changes the final geometry, but the fixed-context test shows the no-MICA fitted shape is preferred under the original no-MICA solution;
- the small native-run gain appears to come largely from camera/pose/expression compensation around the MICA-shaped identity;
- profile and contour-heavy views are especially risky;
- MICA may remain a research reference, but it is not the default baseline for the current Hair App geometry path.

The comparison helper is `experiments/milestone1_geometry_bakeoff/validate_mica_vs_no_mica.py`.

### Priority 1: fully refitted mean-shape control

Completed. Rerun tracking with identity shape fixed to zero while allowing camera, pose, expression, jaw, eyes, eyelids, and intrinsics to optimize. The result matched or slightly beat the no-MICA fitted-shape landmark score, so it did not strengthen the personalization claim.

### Completed: cross-context no-MICA shape versus mean-shape validation

Completed for the private 19-view run. The no-MICA shape won slightly in its own fixed context but lost in the mean-shape context, so the identity-shape claim remains unvalidated by landmarks alone. The next test is not another geometry parameter change; it is a visual texture comparison across the frozen raw FLAME, fitted mean-shape control, and personal no-MICA candidates.

### Completed Diagnostic: observed-photo Texture Baker v1 across the frozen model trio

The first baker now loads the cleaned private Drive layout, reads the frozen
model trio, creates observed texture atlases, writes coverage/confidence/source
maps, renders diagnostic mesh previews, fills black areas with simple material
fallback colors, overlays diagnostic eyes, and generates one-file comparison
sheets for the three Juseop and three Eunchae mesh candidates.

Current representative private output:

```text
output/_comparison/face_texture_model_comparison_8view_wideface_eyes_conf5_v4.png
```

Result: the workflow is reproducible, but the visual quality is not usable for
product decisions. The v1 UV splat approach still leaks occluders, depends on
orthographic debug cameras, has weak lighting/color handling, and cannot fairly
separate the three base mesh candidates. Keep the three mesh candidates active;
do not choose a winner from v1 texture renders.

### Priority 2: Texture Baker v2, camera-aware and front-focused

Build a stronger baker before changing geometry settings. The goal is not a
perfect 360-degree scan. The product target is a personal bald head substrate
that looks credible from the front through about 45 degrees and supports later
hair fitting. Back-of-head and hidden scalp can use generic fallback or
completion when evidence is weak.

Requirements:

1. keep the same user input policy: unconstrained selfies plus app scan frames;
2. score frames/photos for blur, face size, pose, exposure, eye/mouth state,
   landmarks, segmentation reliability, and occlusion;
3. use app scan frames as the more stable geometry/camera coordinate source;
4. use selfies primarily as higher-detail texture evidence;
5. fit or load per-image camera, expression, and lighting before photo/render
   comparison;
6. rasterize mesh triangles into each source photo with z-buffer visibility;
7. weight samples by view angle, texel resolution, sharpness, exposure,
   segmentation confidence, occlusion, and multi-view consistency;
8. preserve observed texture, confidence, source-photo provenance, and
   observed-versus-fallback masks separately;
9. add a front-focused review sheet at `0`, `±15`, `±30`, and `±45` degrees;
10. after the observed layer is stable, add per-user render-to-photo
    optimization for camera, lighting, texture, and only safe small
    geometry/detail corrections.

The per-user optimization stage is not training a network. It is an explicit
optimization loop for one person at a time. A learned network may come later to
predict better initial texture/shape updates and reduce runtime.

### Priority 3: optimization resolution 256 versus 512

Run the same baseline at tracker size 512. The persistent images are already 512, but the default tracker downsamples. Compare identity, regional error, memory, and runtime. Do not assume 512 wins merely because it is larger.

### Priority 4: preserve prediction precision

Modify normal/UV inference to retain float32 `.npy` or a validated 16-bit format alongside preview PNGs. Record confidence when the network exposes it. Compare against the current 8-bit baseline.

### Priority 5: robust regional landmarks

Do not blindly add every MediaPipe point. Add tested regions with visibility and confidence:

- current eyes and irises;
- nose ridge/base;
- brows;
- jaw/contour only when visible;
- outer mouth and corners, preferably on neutral or high-confidence frames.

MediaPipe 478 is useful as a cross-check and possible dense regional source, but it needs an explicit mapping to FLAME or surface constraints. Candidate losses should use robust penalties and downweight occluded or inconsistent points.

### Priority 6: better masks and dense losses

- add a general occluder/unknown mask for hands, phones, products, glasses, headphones, and heavy hair;
- build per-region confidence instead of only accept/reject;
- use angular and multi-scale normal consistency;
- enforce multi-view UV correspondence consistency;
- avoid fitting silhouette to hair or objects;
- record which views support each surface region.

### Priority 7: fine-tune the normal/UV networks

Only after the baseline and A/B tests are understood:

- collect or legally generate Hair App-style multi-view data;
- include selfie lenses, makeup, varied skin tones, occlusion, profile, tilt, pulled-back hair, and real phone compression;
- fine-tune normal and UV predictors with fixed validation identities;
- measure downstream mesh improvement, not just map image loss.

### Priority 8: high-frequency face refinement

If FLAME identity is correct at low frequency but lacks detail, add a face-only displacement or higher-resolution refinement layer with smoothness, symmetry, and observation-confidence constraints. Keep the stable base topology for UV and hair fitting.

### Priority 9: acquire actual scalp evidence

Improve the capture protocol with pulled-back-hair front/temple/profile views, visible ears, crown/rear guidance, and optional depth or VGGT initialization. A head prior may still be necessary, but observed and inferred regions must be labeled separately.

## 13. Immediate Next Experiment

### 13.1 Private 19-view app-scan plus selfie run

Completed on 2026-06-24 in private Drive storage, not in Git:

- input set: selected user selfies plus app-selected scan frames;
- accepted clean views: `19`;
- no-MICA Pixel3DMM tracking completed;
- full no-MICA tracking folder was preserved;
- fully refitted mean-shape control completed with identity shape effectively zero;
- raw FLAME template, fitted mean-shape control, and personal no-MICA were visually compared side by side.

The mean-shape sanity check confirmed that the control was nearly zero identity shape:

```json
{
  "no_mica_shape_l2": 10.628931045532227,
  "mean_shape_l2": 4.09764743380947e-06,
  "shape_difference_l2": 10.62893009185791,
  "shape_param_count": 300
}
```

The cross-context landmark comparison reported:

```json
{
  "views": 19,
  "no_mica_context": {
    "no_mica_shape_error_px": 4.719309781745137,
    "mean_shape_error_px": 4.914750639977585,
    "no_mica_shape_gain_px": 0.19544085823244828
  },
  "mean_shape_context": {
    "no_mica_shape_error_px": 5.123912251678183,
    "mean_shape_error_px": 4.520063043559785,
    "no_mica_shape_gain_px": -0.6038492081183984
  },
  "no_mica_wins_both_contexts": false
}
```

Interpretation:

- the personal no-MICA mesh is visibly different from raw FLAME and from the fitted mean-shape control;
- the no-MICA candidate is still useful as a temporary development mesh;
- the landmark gate does not prove that no-MICA identity shape is better than a refitted mean shape;
- visual texture quality may still separate the three candidates, so the next experiment is to apply observed-photo face texture to all three frozen meshes before making a practical asset decision.

Private artifact rule:

- the personal no-MICA mesh, fitted mean-shape control, and raw FLAME template have been frozen into the private model-trio handoff folder;
- the current private entrypoint for the texture baker is `output/<person>/models/model_trio_for_texture/model_trio_manifest.json` inside the cleaned Drive layout;
- the legacy girl-model experiment is preserved in the same cleaned person-oriented layout, including source photos, preprocessing outputs, and model artifacts;
- keep the generated PLY files, private manifest, source photos, tracking folders, textures, and overlays out of Git;
- commit only the generic helper, contract, metrics summary, and next-step plan.

### 13.2 Current texture result and next experiment

Texture Baker v1 is implemented and pushed. It should be treated as a diagnostic
artifact, not as the product texture path. It proved that the cleaned private
layout, model trio entrypoint, observed texture maps, material fallback, eye
overlay, and comparison-sheet workflow are wired correctly. It also proved that
the current simple splat/fallback approach is too weak.

The next texture experiment at that point was Texture Baker v2, now superseded
by the v3 update below:

1. keep the frozen three-mesh candidate manifest as the entrypoint;
2. keep the user input policy unchanged: selfies plus app scan, no stricter
   capture requirements;
3. build a frame/photo scoring report and reject or downweight weak evidence;
4. use fitted cameras and z-buffer visibility instead of orthographic-only
   texture placement;
5. produce observed texture, confidence, source-photo provenance, and
   observed/fallback masks as separate outputs;
6. generate a front-focused review sheet at `0`, `±15`, `±30`, and `±45`
   degrees, because that is the product-critical viewing range;
7. add per-user render-to-selfie optimization only after the observed layer is
   stable, starting with camera/expression/lighting and texture before any
   geometry/detail corrections.

Only after this should the project return to geometry changes such as tracker
size 512, high-precision maps, regional landmarks, or different identity
constraints. Changing geometry and texture at the same time would make it
unclear whether a visual improvement came from the mesh or the face appearance
layer.

### 13.3 Texture Baker v3 update

Texture Baker v3 is now the latest texture experiment. It does not change the
Pixel3DMM geometry; it keeps the frozen mesh candidates fixed and focuses on
making the photo-derived face texture less broken.

Implemented:

- `experiments/texture_baker/texture_baker_v3.py`;
- `v3_no_lighting` and `v3_lighting_normalized` variants;
- stricter frame filtering with default `--min-score 0.62`;
- weighted multi-frame UV seed texture;
- optional fitted-camera projection pass, disabled by default because it still
  adds forehead/mouth noise;
- whole-face bad/empty texel repair with neighbor fill, mirror fill, material
  fallback, seam smoothing, and skin coherence cleanup;
- per-iteration outputs and metrics for `0..5`;
- fitted-camera comparison sheets and front-to-45 review sheets;
- final texture selection from the earliest clean-enough iteration, currently
  `iter_01`, because later iterations over-smooth identity detail.

Current private outputs:

```text
output/<person>/texture_baker/v3_v3_no_lighting/
output/<person>/texture_baker/v3_v3_lighting_normalized/
output/_comparison/v3_주섭_variant_overview.png
output/_comparison/v3_은채_variant_overview.png
```

Current decision: v3 is cleaner than v1/v2 but still not product-quality, and
it is still not enough to select the final base mesh. The next work is proper
eye/iris/eyelid and mouth materials, better feature preservation for brows and
lips, and safer fitted-camera texture refinement before any geometry changes.

## 14. Notebook Run and Human Gates

The notebook intentionally includes explicit gates.

1. GPU and CUDA architecture check.
2. expected conda install/restart.
3. pinned repository checkout.
4. environment and CUDA extension build.
5. dependency/checkpoint setup.
6. Drive and complete FLAME asset installation.
7. private input discovery.
8. V4 independent no-roll crop.
9. source/crop visual gate.
10. PIPNet and FaRL.
11. preprocessing count/visual gate.
12. Drive preprocessing bundle.
13. `PREPROCESSING_APPROVED=True` only after human inspection.
14. normal/UV inference and exact count gate.
15. tracking.
16. mesh/result visualization.
17. full Drive save and manifest.
18. quantitative evaluation.

Do not bypass a failed count gate merely because later cells can technically run.

## 15. Repository and Privacy Rules

Active executable research file:

- `experiments/milestone1_geometry_bakeoff/pixel3dmm_colab_v4.ipynb`
- `experiments/milestone1_geometry_bakeoff/freeze_model_trio_for_texture.py`

Knowledge files:

- this document for all Pixel3DMM V4 details;
- `docs/10_3d_hair_app_master_plan.md` for the complete product and system plan;
- `docs/history.md` for chronological project decisions;
- `newchat.md` for the compact current handoff.

Removed crop v1/v2/v3 scripts, tests, crop-only notebooks, earlier Pixel3DMM notebooks, and the KaoLRM scaffold remain available in Git history only. Restore them only for a named controlled comparison.

Never commit:

- private photos or scans;
- crop/landmark/segmentation outputs;
- embeddings, meshes, textures, or tracking videos;
- private Drive paths containing identity information;
- notebook output cells containing user data.

## 16. Official Source Links

- Pixel3DMM repository: <https://github.com/SimonGiebenhain/pixel3dmm>
- audited tracker: <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/src/pixel3dmm/tracking/tracker.py>
- tracking configuration: <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/configs/tracking.yaml>
- network inference: <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/scripts/network_inference.py>
- FLAME wrapper: <https://github.com/SimonGiebenhain/pixel3dmm/blob/fcd1fa973c7715b02a8948dfc679dff53cf85924/src/pixel3dmm/tracking/flame/FLAME.py>

## 17. Decision Summary

Current temporary decision:

```text
official FaceBoxes per-photo crop
  + highest-confidence selection
  + margin 1.42
  + persistent 512x512 no-roll coordinate system
  + official PIPNet WFLW-98
  + official FaRL CelebM segmentation
  + Pixel3DMM normal and UV networks
  + no-MICA multi-photo FLAME tracking as the control baseline
```

The baseline is successful but replaceable. The stable target is an editable personal head with honest observed/inferred confidence, not permanent loyalty to Pixel3DMM or FLAME.

## 24. Archived former standalone document: `experiments/texture_baker/README.md`

This section preserves the detailed Texture Baker README that used to live as a
separate active Markdown file. It was moved here on 2026-06-27 because the
custom Texture Baker is no longer the main product-quality path. The content
remains valuable for post-processing ideas, confidence maps, review sheets, and
failure analysis.

---
# Texture Baker Loader

This folder contains the first generic loader for the observed-photo face
texture baker. It resolves private Drive paths and reports the frozen mesh
candidates plus per-frame crop, UV, segmentation, landmark, and crop metadata
inputs.

It does not copy private photos, meshes, masks, textures, or renders into Git.

## Local Windows Check

```powershell
python experiments\texture_baker\texture_baker_loader.py `
  --private-root "G:\내 드라이브\hair_app"
```

## Colab Check

Run this after cloning or pulling the repository in Colab:

```python
from google.colab import drive
drive.mount("/content/drive")

%cd /content/hair_app
!git pull --ff-only
!python experiments/texture_baker/texture_baker_loader.py \
  --private-root /content/drive/MyDrive/hair_app
```

Expected current bundles:

- `주섭`: three frozen mesh candidates from
  `output/주섭/models/model_trio_for_texture/model_trio_manifest.json`.
- `은채`: three frozen mesh candidates from
  `output/은채/models/model_trio_for_texture/model_trio_manifest.json`:
  `raw_flame_template`, `base_flame2023`, and `personal_no_mica`.

The loader accepts both Colab paths such as
`/content/drive/MyDrive/hair_app/...` and local Windows paths such as
`G:\내 드라이브\hair_app\...`.

## First Observed-Texture Smoke Test

Run a tiny one-frame bake before running every frame:

```python
!python experiments/texture_baker/observed_texture_baker.py \
  --private-root /content/drive/MyDrive/hair_app \
  --person 주섭 \
  --atlas-size 256 \
  --max-frames 1 \
  --output-name observed_v0_smoke \
  --splat-radius 1
```

## Current Preview Bake

The cleaner preview path is to pick one good primary front frame for central
face texels, then let secondary frames contribute only where explicitly useful.
This keeps the observed layer reproducible while avoiding blurry multi-view
ghosting.

Juseop current preview:

```python
!python experiments/texture_baker/observed_texture_baker.py \
  --private-root /content/drive/MyDrive/hair_app \
  --person 주섭 \
  --atlas-size 512 \
  --output-name observed_v6_primary00000_faceonly_secondary0_preview \
  --splat-radius 1 \
  --blend-mode weighted \
  --primary-frame-id 00000 \
  --secondary-central-weight 0 \
  --mask-erode-iterations 2 \
  --preview-fill-iterations 8 \
  --preview-fill-min-neighbors 5
```

Eunchae current preview uses frame `00004` as the cleaner front primary, keeps
side/ear labels available, and removes likely hair/headwear occlusion before
baking:

```python
!python experiments/texture_baker/observed_texture_baker.py \
  --private-root /content/drive/MyDrive/hair_app \
  --person 은채 \
  --atlas-size 512 \
  --output-name observed_v15_primary00004_wideface_strict_occlusion_preview \
  --splat-radius 1 \
  --blend-mode weighted \
  --primary-frame-id 00004 \
  --secondary-central-weight 0.02 \
  --primary-side-weight 1.0 \
  --secondary-side-weight 0.0 \
  --mask-erode-iterations 2 \
  --occlusion-margin-iterations 10 \
  --skin-occlusion-filter \
  --skin-occlusion-chroma-threshold 30 \
  --skin-occlusion-luma-threshold 52 \
  --secondary-central-crop-radius-x 0.52 \
  --secondary-central-crop-radius-y 0.78 \
  --preview-fill-iterations 8 \
  --preview-fill-min-neighbors 5
```

Current MVP assumptions:

- Pixel3DMM UV PNG red/green channels are interpreted as U/V.
- V is not flipped by default. Use `--flip-v` only for an explicit A/B.
- Face-label whitelist `2`, `4`, `5`, `6`, `7`, `8`, `9`, `10`, `12`, and
  `13` is enabled by default. Segmentation labels `0`, `1`, `3`, and `14`
  remain excluded by default.
- `--splat-radius 1` is useful for a visible preview. `--splat-radius 0`
  preserves the raw point-splat observations.
- `--blend-mode weighted` uses segmentation, center, exposure, and primary
  frame heuristics. It is still a preview policy, not a validated photometric
  model.
- `--occlusion-margin-iterations` removes pixels near configured hair/headwear
  labels, and `--skin-occlusion-filter` removes skin-label pixels that are too
  far from the frame's skin reference color. These are review heuristics for
  reducing hair/headband leaks, not semantic matting.
- `--secondary-central-crop-radius-x/y` lets non-primary frames contribute only
  from the crop center when a primary frame is selected.
- `base_color_observed.png` is the real observed-photo layer. Optional
  `base_color_preview_filled.png` is only a conservative visualization and
  should not be treated as evidence.
- The baker does not yet perform true triangle rasterization, view-angle
  scoring, seam blending, or completion.

Outputs are written only under the private Drive person folder:

```text
output/<person>/texture_baker/<output-name>/
  base_color_observed.png
  coverage.png
  confidence.png
  source_view_map.png
  base_color_preview_filled.png  # only when preview fill is requested
  texture_manifest.json
```

## Mesh Texture Preview

The flat atlas is a debug artifact. Use the mesh preview script to attach the
observed atlas to FLAME-topology PLY candidates and render quick orthographic
front/oblique checks:

```python
!python experiments/texture_baker/textured_mesh_preview.py \
  --private-root /content/drive/MyDrive/hair_app \
  --person 주섭 \
  --person 은채 \
  --texture-kind preview_filled \
  --uv-mode flip_y \
  --depth-mode max \
  --view front \
  --view left_35 \
  --view right_35 \
  --material-fallback \
  --fallback-confidence-threshold 5 \
  --eye-overlay \
  --write-obj
```

This expects the Pixel3DMM FLAME UV asset at:

```text
shared/models/pixel3dmm_assets/flame_uv_coords.npy
```

Current local Drive preview outputs:

```text
output/<person>/texture_baker/<texture-name>/mesh_texture_preview/<mesh-key>/
  front_flip_y_depth_max.png
  left_35_flip_y_depth_max.png
  right_35_flip_y_depth_max.png
  contact_sheet.png
  <mesh-key>_uv_direct.obj
  <mesh-key>_uv_direct.mtl
  mesh_texture_preview_manifest.json
```

The preview renderer is intentionally simple: CPU orthographic rasterization,
no lighting model, no fitted tracking cameras, and no perspective intrinsics.
For the current Pixel3DMM UV atlas, `--uv-mode flip_y --depth-mode max` is the
visually correct orientation.

Eunchae's current private model trio was normalized to match the Juseop
comparison shape: a shared raw FLAME template baseline, the existing
`base_flame2023` candidate, and the no-MICA canonical candidate. The generated
PLY copies and `model_trio_manifest.json` are private Drive artifacts, not Git
files.

## One-File 8-View Comparison Sheet

For manual model selection, generate one large private PNG with rows as model
candidates and columns as 45-degree yaw views:

```python
!python experiments/texture_baker/make_texture_comparison_sheet.py \
  --private-root /content/drive/MyDrive/hair_app \
  --texture-kind preview_filled \
  --image-size 512 \
  --padding 42 \
  --uv-mode flip_y \
  --depth-mode max \
  --mask-mode none \
  --material-fallback \
  --fallback-confidence-threshold 5 \
  --eye-overlay
```

Local output:

```text
output/_comparison/face_texture_model_comparison_8view_wideface_eyes_conf5_v4.png
output/_comparison/face_texture_model_comparison_8view_wideface_eyes_conf5_v4.json
```

`--material-fallback` fills texture-black sampled areas with simple FLAME-mask
review colors for scalp, neck, ears, lips, and eyeballs. This is currently
better for model choice than full UV diffusion because it reduces black holes
without creating large misleading rear-head streaks.
`--eye-overlay` adds diagnostic iris/pupil markers over the FLAME eyeball
masks, and `--fallback-confidence-threshold 5` replaces only very
low-confidence texture samples with the same material fallback so neck/jaw
speckles are less visually distracting.

For an explicit UV hole-fill A/B, first create private visual completions:

```python
!python experiments/texture_baker/complete_texture_for_review.py \
  --private-root /content/drive/MyDrive/hair_app
```

Then pass `--texture-kind visual_completed` to the sheet generator. Treat that
output as a rough review artifact, not a production texture.

## 2026-06-26 Review Result

The v1 baker proved the private data layout, loader, observed atlas outputs,
mesh preview renderer, fallback materials, eye overlay, and comparison-sheet
workflow. It did not produce product-usable face quality.

Key private outputs from the current review round:

```text
output/은채/texture_baker/observed_v15_primary00004_wideface_strict_occlusion_preview/
output/_comparison/face_texture_model_comparison_8view_wideface_eyes_conf5_v4.png
output/_comparison/face_texture_model_comparison_8view_wideface_eyes_conf5_v4.json
```

Observed problems:

- the raw UV splat baker still leaks hair, headwear, and low-confidence pixels;
- orthographic debug renders do not match actual selfie cameras;
- material fallback reduces black holes but does not make the texture realistic;
- eye overlays are diagnostic markers, not final eye rendering;
- full UV visual completion created misleading rear-head streaks;
- the three base meshes cannot be fairly judged while the texture layer is this weak.

Keep the three mesh candidates active for now. The current front-facing quality
is the limiting factor, not a proven base-mesh winner.

## Texture Baker v2 Plan

The next baker should be camera-aware and front-focused. The product target is
not a perfect 360-degree scan; it is a personal bald head substrate that looks
credible from front through roughly 45 degrees and supports later hair fitting.
Back-of-head and hidden scalp regions may use generic fallback or completion.

Inputs remain unchanged:

- unconstrained user selfies;
- the app scan frame bundle.

Planned v2 stages:

1. score each selfie and scan frame for face size, blur, pose, exposure, eye and
   mouth state, landmark stability, segmentation quality, and occlusion from
   hair, hands, phones, glasses, or headphones;
2. use the app scan as the stable geometry/camera coordinate source;
3. use selfies mainly as high-detail texture evidence;
4. fit or load per-image camera/expression/lighting before comparing photos;
5. project mesh triangles into each source image with z-buffer visibility;
6. weight samples by view angle, texel resolution, sharpness, exposure,
   segmentation confidence, occlusion, and cross-view consistency;
7. maintain observed texture, confidence, source-photo provenance, and
   observed-versus-fallback masks separately;
8. render a front-focused review sheet at `0`, `±15`, `±30`, and `±45` degrees;
9. after the observed layer is stable, add per-user optimization that renders
   the textured model into the selfie camera and minimizes masked losses for
   landmarks, silhouette, skin color, perceptual identity, smoothness, and safe
   low-frequency geometry/detail corrections.

This is initially per-user optimization logic, not training a neural network.
Later, accumulated optimization results can train a network that predicts a
better initial texture/shape update and reduces runtime.

## 2026-06-26 Texture Baker v2 Hybrid Run

Implemented v2 code:

- `evidence_quality_report.py`: scores each private frame for blur, face size,
  pose, exposure, eye/mouth state, landmark stability, segmentation quality,
  occlusion, and skin-color reference.
- `texture_baker_v2.py`: writes a camera-aware/hybrid observed atlas. It keeps
  fitted-camera projection and z-buffer visibility as a diagnostic/fill source,
  but also uses Pixel3DMM UV correspondence maps for central face detail because
  the current checkpoint camera crop calibration is still too rough for a pure
  mesh-projection bake.
- `make_texture_comparison_sheet.py --texture-name`: allows explicit texture
  run selection for one-file review sheets.
- `textured_mesh_preview.py`: defaults now point both people to
  `observed_v2_camera_visibility_front45_preview`.

Current private v2 outputs:

```text
output/Juseop-or-Korean-person-name/texture_baker/observed_v2_camera_visibility_front45_preview/
output/Eunchae-or-Korean-person-name/texture_baker/observed_v2_camera_visibility_front45_preview/
output/_comparison/face_texture_model_comparison_front45_v2.png
output/_comparison/face_texture_model_comparison_front45_v2.json
```

Local command used for the current front-focused sheet:

```powershell
python experiments\texture_baker\make_texture_comparison_sheet.py `
  --private-root "G:\내 드라이브\hair_app" `
  --texture-name observed_v2_camera_visibility_front45_preview `
  --texture-kind preview_filled `
  --image-size 512 `
  --padding 58 `
  --uv-mode flip_y `
  --depth-mode max `
  --mask-mode none `
  --material-fallback `
  --fallback-confidence-threshold 5 `
  --eye-overlay `
  --yaw-degree -45 --yaw-degree -30 --yaw-degree -15 `
  --yaw-degree 0 `
  --yaw-degree 15 --yaw-degree 30 --yaw-degree 45 `
  --output-path "G:\내 드라이브\hair_app\output\_comparison\face_texture_model_comparison_front45_v2.png"
```

Observed result:

- black holes are much less distracting in review renders because material
  fallback and confidence fallback cover low-observation regions;
- front/near-front face identity is more readable than the first pure camera
  v2 attempt;
- Juseop still has strong lighting/color seams on forehead and face;
- Eunchae still has forehead/headband or hair contamination;
- diagnostic eye overlay makes eyes visible but is not product-quality;
- the base mesh winner still should not be chosen purely from this sheet.

Next texture work should focus on completion/occlusion cleanup, not simply more
v1-style UV splat tuning: remove hair/headwear from observed skin regions,
replace low-confidence forehead/scalp/neck with plausible skin material, improve
eye assets, and then return to fitted-camera selfie comparison.

## 2026-06-26 Cleanup/Completion Pass

Implemented `texture_cleanup_completion.py` as a post-process over the v2 atlas.
It keeps the raw observed texture and confidence map intact, then writes a
separate review texture:

```text
base_color_cleanup_completed.png
cleanup_removed_mask.png
completion_replaced_mask.png
base_color_material_reference.png
cleanup_completion_manifest.json
```

Current local command:

```powershell
python experiments\texture_baker\texture_cleanup_completion.py `
  --private-root "G:\내 드라이브\hair_app" `
  --person 주섭 `
  --person 은채 `
  --texture-name observed_v2_camera_visibility_front45_preview `
  --save-debug-masks
```

Current cleanup review sheet:

```text
output/_comparison/face_texture_model_comparison_front45_v2_cleanup.png
output/_comparison/face_texture_model_comparison_front45_v2_cleanup.json
```

What this pass does:

- removes low-confidence or skin-color-outlier texels from skin/scalp/neck
  review use;
- replaces unobserved or unreliable forehead, scalp, neck, boundary, and ear
  areas with simple skin-region materials;
- preserves central observed face detail where confidence/color checks allow it;
- keeps lips/eye regions separate so they can be handled by dedicated assets.

Current result:

- black holes and obvious headwear/hair contamination are reduced;
- hidden or low-confidence scalp/neck is now plausible but flat;
- this is better for model inspection than the raw v2 sheet, but still not
  product-quality;
- the remaining quality bottlenecks are central face color seams, final eye
  assets, lighting normalization, and later render-to-selfie refinement.

## 2026-06-26 Feature/Seam and Fitted-Camera Compare Pass

Extended the cleanup review path instead of choosing a base mesh too early.
The three mesh candidates per person stay active because texture quality is
still the limiting factor.

Code changes:

- `texture_cleanup_completion.py`: adds a feature/seam refinement step after
  cleanup completion. It lightly handles lips, mouth-dark pixels, eye regions,
  eyeball material, and seam-band smoothing between observed and fallback
  material regions.
- `textured_mesh_preview.py`: replaces the pure diagnostic eye dots with a
  more material-like eye overlay and exposes `selfie_optimized` texture lookup.
- `make_texture_comparison_sheet.py`: can now render `selfie_optimized`
  textures on the same front-to-45 review sheet.
- `fitted_camera_selfie_compare.py`: creates fitted-camera crop/render
  comparison sheets, conservative lighting-matched renders, diff maps, and a
  weak per-user UV residual texture preview. This is not neural-network
  training and does not change geometry yet.

Private outputs generated by the current run:

```text
output/_comparison/face_texture_model_comparison_front45_v3_features.png
output/_comparison/face_texture_model_comparison_front45_v3_features.json
output/_comparison/face_texture_model_comparison_front45_v4_selfie_optimized.png
output/_comparison/face_texture_model_comparison_front45_v4_selfie_optimized.json
output/<person>/texture_baker/fitted_camera_selfie_compare_v1/
output/<person>/texture_baker/observed_v2_camera_visibility_front45_preview/base_color_selfie_optimized_preview.png
```

Current fitted-camera command:

```powershell
python experiments\texture_baker\fitted_camera_selfie_compare.py `
  --private-root "<private_root>" `
  --person <person_a> `
  --person <person_b> `
  --texture-name observed_v2_camera_visibility_front45_preview `
  --texture-kind cleanup_completed `
  --max-frames 4 `
  --tile-size 256
```

Current review-sheet command shape:

```powershell
python experiments\texture_baker\make_texture_comparison_sheet.py `
  --private-root "<private_root>" `
  --texture-name observed_v2_camera_visibility_front45_preview `
  --texture-kind cleanup_completed `
  --image-size 512 `
  --padding 58 `
  --uv-mode flip_y `
  --depth-mode max `
  --mask-mode none `
  --material-fallback `
  --eye-overlay `
  --yaw-degree -45 --yaw-degree -30 --yaw-degree -15 `
  --yaw-degree 0 `
  --yaw-degree 15 --yaw-degree 30 --yaw-degree 45 `
  --output-path "<private_root>\output\_comparison\face_texture_model_comparison_front45_v3_features.png"
```

Observed result:

- black/empty regions are now mostly replaced by skin/scalp fallback material;
- eyes and lips are more visible but still look synthetic and need real
  material/geometry handling;
- fitted-camera render comparison now has correct upright projection after
  applying `projection_flip_y`;
- the weak residual pass reduces masked raw luma error on the selected fitted
  frames, but it is intentionally conservative and does not solve identity,
  seam, or lighting by itself;
- the biggest remaining blockers are forehead/central-face seams, eye realism,
  scan/selfie lighting mismatch, and the fact that hidden regions are still
  plausible fallback rather than observed skin.

Next recommended work:

- replace the diagnostic eye overlay with proper eyeball/iris material and
  eyelid-aware masking;
- improve region-specific color blending so forehead, cheeks, jaw, neck, and
  fallback scalp do not read as separate patches;
- make fitted-camera comparison drive stronger but masked UV residual updates
  only on reliable skin regions;
- later add weak camera/lighting/texture optimization per frame, then only
  after that consider low-frequency geometry correction.

## 2026-06-26 Texture Baker v3 Iterative Avatar Bake

Implemented `texture_baker_v3.py` as the next direct texture experiment after
the v2 cleanup and fitted-camera comparison pass. v3 keeps geometry fixed and
tries to build a calmer avatar texture from the same private photos instead of
continuing to tune the first raw UV splat result.

What v3 does:

- scores and filters frames with `evidence_quality_report.py`;
- uses Pixel3DMM UV correspondence maps as the main direct bake source;
- optionally supports a low-weight fitted-camera projection pass, but it is
  disabled by default because it currently reintroduces forehead and mouth
  noise;
- writes two variants: `v3_no_lighting` and `v3_lighting_normalized`;
- runs iterations `0..N`, saving texture, confidence, observed mask, filled
  mask, metrics, fitted-camera comparison sheet, and front-to-45 review sheet;
- uses weighted multi-frame color rather than a single best source texel;
- fills empty/bad texels over the whole skin/scalp/neck/ear region, not only
  the nose;
- applies region-aware neighbor fill, mirror fill, material fallback, seam
  smoothing, and skin coherence cleanup;
- selects the final texture from the earliest clean-enough iteration, currently
  usually `iter_01`, to avoid later over-smoothing.

Current command shape:

```powershell
python experiments\texture_baker\texture_baker_v3.py `
  --private-root "G:\내 드라이브\hair_app" `
  --person 주섭 `
  --person 은채 `
  --variant v3_no_lighting `
  --variant v3_lighting_normalized `
  --output-prefix v3 `
  --iterations 5 `
  --min-score 0.62 `
  --max-abs-yaw 58 `
  --atlas-size 512 `
  --image-size 512
```

Current private outputs:

```text
output/<person>/texture_baker/v3_v3_no_lighting/
output/<person>/texture_baker/v3_v3_lighting_normalized/
output/_comparison/v3_주섭_variant_overview.png
output/_comparison/v3_은채_variant_overview.png
```

Current selected final iterations from the local private run:

| Person | Variant | Selected final | Mean luma error | Seam score | Observed coverage |
| --- | --- | ---: | ---: | ---: | ---: |
| Juseop | no lighting | 1 | 27.48 | 0.640 | 34.2% |
| Juseop | lighting normalized | 1 | 27.12 | 0.631 | 34.3% |
| Eunchae | no lighting | 1 | 36.99 | 1.027 | 23.5% |
| Eunchae | lighting normalized | 1 | 37.16 | 1.114 | 23.6% |

Observed result:

- v3 is cleaner than the raw v1/v2 sheets because black holes and extreme
  patching are mostly removed;
- it is still not product-quality;
- repeated iterations lower numeric error slightly but flatten identity detail,
  so the final texture intentionally selects an early stable iteration;
- lighting normalization helps Juseop slightly in metrics and is close visually;
- Eunchae remains harder because visible forehead/hair/headwear contamination
  and lower observed coverage still dominate;
- eyes, eyelids, mouth interior, lips, and brows need dedicated material or
  geometry handling instead of relying on baked photo pixels;
- the base mesh winner still should not be selected from v3 alone.

Next recommended work:

- implement real eye/iris/eyelid and mouth-interior materials;
- make feature regions preserve stable brows/lips without cartoon material
  flattening;
- improve fitted-camera comparison so it can drive stronger masked texture
  updates without pushing bad forehead/mouth pixels into the atlas;
- after texture stability improves, revisit render-to-selfie optimization and
  only then consider weak low-frequency geometry correction.
