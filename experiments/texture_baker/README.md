# Texture Baker Experiments

Last updated: 2026-06-27

## 1. Current Status

Texture Baker v1/v2/v3 is a research baseline, not the current product-quality
path.

The current main head-generation candidate is FaceBuilder/KeenTools automation
inside headless Blender:

```text
experiments/facebuilder_bridge/
```

Keep this folder because it records what was tried, what failed, and what ideas
may still be useful for post-processing.

## 2. Original Goal

The original goal was:

```text
Pixel3DMM/FLAME base mesh candidates
  + private selfies / app scan frames
  -> observed face texture
  -> completed bald-head material
  -> review sheets for base mesh selection
```

The user wanted to compare Juseop and Eunchae across three base mesh candidates
and judge which model looked best after skin texture was applied.

## 3. Private Entrypoint

Historical private entrypoint:

```text
output/<person>/models/model_trio_for_texture/model_trio_manifest.json
```

Private root examples should stay local/Drive-only. Do not commit real photos,
meshes, landmarks, masks, textures, renders, or review sheets.

## 4. v1 Loader and First Bake

v1 proved basic loading and rendering:

- loaded model trio manifests;
- rendered candidate meshes;
- used available texture/correspondence evidence;
- generated first diagnostic sheets.

Observed result:

- large black/unfilled regions;
- face texture covered only a small useful area;
- eyes and mouth were crude placeholders;
- quality was too low for base-model selection.

## 5. v2 Texture Baker

v2 added more serious texture logic:

- evidence quality scoring;
- segmentation confidence;
- view/camera diagnostics;
- z-buffer visibility pass;
- Pixel3DMM UV correspondence use;
- color correction attempts;
- front-to-45 review sheets;
- cleanup/completion helper scripts.

What improved:

- fewer completely empty regions;
- better review sheet structure;
- clearer distinction between observed and fallback areas;
- easier debugging of coverage and frame quality.

What failed:

- camera projection was still too heuristic;
- texture seams remained obvious;
- forehead, mouth, and central-face areas could receive bad pixels;
- Eunchae had lower useful coverage and headwear/hair leakage;
- eyes, mouth, lips, and brows were not solved by texture baking alone.

## 6. Cleanup and Completion

Cleanup/completion attempted to:

- remove low-confidence or color-outlier pixels;
- remove likely hair/headwear leakage;
- fill scalp, neck, ears, and unobserved boundary regions;
- keep observed and completed textures separate;
- reduce black holes in review sheets.

This made the output easier to inspect but also made hidden areas flat and
generic. It did not solve identity quality.

## 7. v3 Iterative Avatar Bake

v3 was built after the user rejected v2 as far below product standard.

Implemented ideas:

- `v3_no_lighting`;
- `v3_lighting_normalized`;
- frame filtering with stricter score thresholds;
- weighted multi-frame seed texture;
- optional fitted-camera projection pass, disabled by default because it
  reintroduced noise;
- whole-face bad/empty texel repair;
- neighbor fill;
- mirror fill;
- material fallback;
- seam smoothing;
- skin coherence cleanup;
- outputs for iterations `0..5`;
- metrics and review sheets per iteration;
- final selection from an early clean iteration instead of blindly using the
  last iteration.

Representative private metrics:

| Person | Variant | Selected final | Mean luma error | Seam score | Observed coverage |
| --- | --- | ---: | ---: | ---: | ---: |
| Juseop | no lighting | 1 | 27.48 | 0.640 | 34.2% |
| Juseop | lighting normalized | 1 | 27.12 | 0.631 | 34.3% |
| Eunchae | no lighting | 1 | 36.99 | 1.027 | 23.5% |
| Eunchae | lighting normalized | 1 | 37.16 | 1.114 | 23.6% |

Important lesson: repeated iterations can lower numeric error while visually
destroying identity. Later iterations tended to smooth away nose, lips, skin
detail, and natural contrast.

## 8. Why It Is Not the Main Path Now

The texture baker struggled because:

- photo pixels must land on the correct 3D surface, and small camera errors are
  very visible;
- fixed geometry cannot fully explain different selfies;
- occlusions and lighting differences require strong filtering;
- completion can remove holes but cannot invent real identity detail reliably;
- eyes, mouth, eyelids, brows, lips, ears, scalp, and hairline need specialized
  material/geometry handling;
- the final result was not close enough to product quality.

This is why the project pivoted to FaceBuilder/KeenTools automation.

## 9. Ideas Worth Reusing

Even though the baker is not the main path, useful ideas remain:

- photo/frame scoring;
- observed versus fallback region masks;
- confidence maps;
- front-to-45 review sheets;
- lighting-normalization experiments;
- metrics plus human visual review;
- private manifest/output discipline;
- material fallback for scalp, neck, ears, and hidden regions.

These can be reused in FaceBuilder post-processing.

## 10. Future Use

Return to this folder only for one of these reasons:

- compare FaceBuilder result against the Pixel3DMM baseline;
- reuse review sheet or confidence-map utilities;
- build a post-processing step for FaceBuilder textures;
- run a named controlled experiment requested by the user.

Do not spend more time tuning v3 as the main product path without a specific
reason.
