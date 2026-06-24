# Milestone 1: Pixel3DMM Hairless Geometry Baseline

Last synchronized: 2026-06-24
Status: V4 preprocessing Gate A/B/C passed 8/8 and was saved; normal/UV Gate D awaits a live rerun

## Active Notebook

This directory intentionally keeps only one executable notebook:

- `pixel3dmm_colab_v4.ipynb`

It contains the complete Colab flow: pinned Pixel3DMM checkout, A100/H100 environment setup, validated FLAME assets, per-image no-roll crop, PIPNet 98 landmarks, FaRL segmentation, preprocessing gates, Drive artifact backup, normal/UV inference, FLAME tracking, mesh preview, and run manifest.

Earlier Pixel3DMM notebooks, the KaoLRM scaffold, and crop v1/v2/v3 code, tests, and crop-only notebooks were removed on 2026-06-24. Their conclusions remain in `docs/history.md`, `docs/12_pixel3dmm_preprocessing_contract.md`, `docs/13_pixel3dmm_v4_live_run_2026-06-23.md`, and Git history. They are not current execution paths.

## Current Result

- Environment and CUDA extensions: passed on A100.
- FLAME2020/2023, masks, and landmark embedding: installed and validated.
- Per-image FaceBoxes crop: 8/8 passed after switching primary-face selection to confidence-first.
- PIPNet 98 landmarks: 8/8 passed.
- FaRL segmentation: 8/8 passed.
- Complete private preprocessing bundle: saved to Google Drive; never commit it to Git.
- Normal/UV inference: first run stopped at the PyTorch 2.6+ `weights_only=True` compatibility change.
- V4 fix: the trusted official checkpoint is loaded with `weights_only=False`; this fix still needs a live rerun.
- Tracking and final mesh: not yet completed.

## Exact Resume Order

1. Open the latest `pixel3dmm_colab_v4.ipynb` in a fresh GPU Colab runtime.
2. Run it from the top so every runtime-local dependency and compatibility patch is recreated.
3. Approve preprocessing only after the crop/PIPNet/FaRL visual gate is valid.
4. Run normal and UV inference.
5. Require `expected/normals/uv: 8 8 8` before tracking.
6. Run multi-image FLAME tracking and confirm a non-empty mesh.
7. Save logs, config, manifest, mesh, and scores to the private Drive run directory.

The chronological error log and old-runtime patch instructions are in `docs/13_pixel3dmm_v4_live_run_2026-06-23.md` §11.

## Input and Privacy

Use at least five high-quality views where possible: front, left/right three-quarter, left/right profile, and pulled-back-hair hairline views. Avoid beauty filters and geometric portrait warps.

Photos, landmarks, masks, textures, meshes, and run folders are biometric-sensitive private data. Keep them in private storage only. This repository may contain code, empty notebooks, non-identifying configuration, and score templates, but never the actual user artifacts.

## Evaluation Gate

Do not adopt Pixel3DMM because the notebook merely runs. Inspect identity, nose/cheek/jaw geometry, side contour, ears/scalp topology, hairline usefulness, and execution reliability. Hidden scalp and rear-head regions are prior estimates rather than measured truth.

Pixel3DMM is currently a research baseline and possible teacher, not a permanently selected production engine. Candidate comparisons such as KaoLRM may be recreated later with the same inputs if the Pixel3DMM result is insufficient; their obsolete notebooks are not retained here.

## License

Pixel3DMM is CC BY-NC 4.0, and FLAME assets have separate terms. A successful research run does not establish commercial permission.
