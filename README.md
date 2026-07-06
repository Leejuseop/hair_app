# Hair App

Hair App은 일반 셀카와 앱 카메라 스캔을 바탕으로, 헤어스타일을 3D로 미리 확인할 수 있는 개인 헤드 아바타를 만드는 R&D/prototype 프로젝트입니다.

목표는 완벽한 360도 3D 스캔이 아니라, 헤어 앱에서 중요한 정면부터 약 45도 측면까지 자연스럽게 보이는 "대머리 헤드 + 이후 합성할 헤어" 기반을 만드는 것입니다.

## 핵심 목표

- 사용자는 정형화된 촬영을 강하게 요구받지 않고, 일반 셀카와 앱 스캔만 제공합니다.
- 얼굴 정면, 약측면, 헤어라인, 두상 느낌이 헤어스타일 판단에 충분히 자연스럽게 보여야 합니다.
- 보이지 않는 뒤통수나 두피 영역은 실제 복원보다 자연스러운 fallback을 우선합니다.
- 사진에서 실제로 관측된 영역과 추정해서 메운 영역을 구분해 관리합니다.
- 최종 결과는 모바일 앱에서 볼 수 있는 3D head/GLB asset으로 정리하는 것을 목표로 합니다.

## 현재 파이프라인

현재 실험 방향은 FaceBuilder/Blender 기반입니다.

1. 셀카와 앱 스캔 사진을 수집합니다.
2. 얼굴 기준 crop과 자동 정렬을 수행합니다.
3. FaceBuilder로 기본 head mesh와 raw texture를 생성합니다.
4. 얼굴 parsing, object mask, hairline 정보를 이용해 texture 오염을 찾습니다.
5. 머리카락, 손, 물체, 옷, 배경이 얼굴 texture에 섞인 부분을 제거하거나 보정합니다.
6. 눈썹, 눈, 입술 같은 세부 요소는 피부와 분리해서 별도 복원합니다.
7. 이후 헤어 asset을 얹기 좋은 bald head asset으로 정리합니다.

## 현재 작업 상태

아직 제품 완성본은 아니고, 품질을 끌어올리는 실험 단계입니다.

지금 집중하는 부분은 다음입니다.

- FaceBuilder raw texture에서 머리카락, 물체, 옷 오염 제거
- 헤어라인 기준으로 두피/이마/얼굴 영역 정리
- 눈썹, 눈, 입술 재질을 자연스럽게 복원
- 각 단계별 review sheet로 품질 비교
- 나중에 헤어 합성을 위한 bald head GLB 준비

## 이전 실험

Pixel3DMM/FLAME 기반 3DMM 후보와 자체 Texture Baker도 실험했습니다. 이 경로는 visibility, UV, confidence, completion 같은 개념을 검증하는 데 도움이 되었지만, 현재 제품 품질 후보는 FaceBuilder 기반 파이프라인으로 옮겨가고 있습니다.

자세한 실험 기록은 `docs/history.md`에 남겨두었습니다.

## Privacy

이 저장소에는 private 얼굴 데이터와 생성 산출물을 넣지 않습니다.

Git에 넣지 않는 것:

- 사용자 셀카와 앱 스캔 프레임
- crop, landmark, mask, segmentation 결과
- private mesh, OBJ, MTL, GLB
- texture, render, review sheet
- Google Drive 또는 로컬 private output

Git에는 코드, 문서, private 데이터를 처리하는 스크립트만 저장합니다.

## Status

현재 상태는 R&D/prototype입니다. 단기 목표는 "일반 셀카 + 앱 스캔만으로 헤어 앱에 쓸 수 있는 개인 3D bald head 기반을 만들 수 있는가"를 검증하는 것입니다.
