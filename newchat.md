# Hair App New-Chat Handoff

Last synchronized: 2026-06-24
Current architecture source of truth: `docs/10_3d_hair_app_master_plan.md`
Current Pixel3DMM runbook: `docs/13_pixel3dmm_v4_live_run_2026-06-23.md`

## Start Here

1. Run `git status --short --branch` and inspect the current code.
2. Read `AGENTS.md`.
3. For the current experiment, read this file, the milestone README, and docs 12–13.
4. Do not commit private photos, landmarks, masks, textures, meshes, or Drive run folders.

## Current Product Direction

Hair App targets a real editable 3D pipeline rather than a single 2D edited image:

```text
multiple user photos + guided hairline/head scan
  -> reusable hairless head mesh
  -> observed multi-photo face UV texture

hairstyle reference
  -> independent strand hair

head + hair
  -> retargeting + collision correction
  -> rotatable GLB + optional renders
```

The current research stack is MediaPipe capture guidance, Pixel3DMM geometry baseline, a future Hair App UV baker, a strand-hair baseline such as DiffLocks, custom fitting/collision correction, and GLB delivery. Every model choice remains replaceable after same-input evaluation. FastAvatar is not the current core because Gaussian representation conflicts with the editable UV mesh and independent-hair requirement.

## Current Implementation Boundary

Implemented today:

- React + Vite mobile scan flow for `front`, `left`, `right`, and `hairline`;
- MediaPipe Face Landmarker quality guidance and automatic sample collection;
- FastAPI scan upload/storage and `base_profile.json` version `0.1`;
- representative-image, landmark, and hairline-guide previews.

Not implemented yet:

- selfie multi-upload and star UI;
- production 3D reconstruction/UV baking;
- hairstyle persistence and strand reconstruction;
- hair retargeting/collision correction;
- GPU job queue, GLB result viewer, and final 3D result API.

## Pixel3DMM V4 Exact State

Only one executable repository notebook is retained:

- `experiments/milestone1_geometry_bakeoff/pixel3dmm_colab_v4.ipynb`

Live A100 result from 2026-06-23:

- environment/CUDA extensions passed;
- FLAME assets passed;
- FaceBoxes per-image, margin 1.42, 512×512, no-roll crop passed 8/8;
- confidence-first selection fixed the profile image false-positive crop;
- PIPNet WFLW 98 landmarks passed 8/8;
- FaRL segmentation passed 8/8;
- count gate was `8/8/8/8/8/8`;
- the complete private preprocessing bundle was saved to Drive;
- normal inference then stopped at PyTorch 2.6+ checkpoint loading because `weights_only=True` became the default.

The latest V4 notebook patches the trusted official Lightning checkpoint load to `weights_only=False`. This fix is implemented locally and in Git, but normal/UV has not yet been confirmed in a live runtime. Tracking and mesh output therefore remain incomplete.

## Immediate Next Step

Recommended after returning:

1. Open the latest V4 notebook in a fresh A100/H100 Colab runtime.
2. Run from the top; do not reuse only fragments from an old runtime unless necessary.
3. Confirm preprocessing again and set `PREPROCESSING_APPROVED=True` only after visual inspection.
4. Run normal/UV inference and require `expected/normals/uv: 8 8 8`.
5. Only then run `track.py`, preview the mesh, and save the full run bundle.

If the old Colab runtime is still alive, docs 13 §11 contains the exact checkpoint compatibility patch and rerun command.

## Repository Cleanup Decision

On 2026-06-24 the repository was simplified to the final V4 notebook only. The following executable artifacts were removed because they were superseded or no longer part of the immediate path:

- crop v1/v2/v3 Python implementations and unit tests;
- crop-only v1/v2/v3 Colab notebooks;
- the original and Safe Pixel3DMM notebooks;
- the old KaoLRM notebook scaffold.

The historical reasoning remains in docs 11–13 and Git history. Do not reintroduce those files unless a concrete same-input A/B experiment requires them.

## Key Documents

- `README.md`: project overview and implemented boundary.
- `docs/04_scan_pipeline.md`: capture and preprocessing flow.
- `docs/10_3d_hair_app_master_plan.md`: complete 3D plan and decision gates.
- `docs/12_pixel3dmm_preprocessing_contract.md`: final no-roll crop/PIPNet/FaRL contract.
- `docs/13_pixel3dmm_v4_live_run_2026-06-23.md`: exact errors, fixes, artifacts, and resume instructions.
- `experiments/milestone1_geometry_bakeoff/README.md`: concise current experiment status.
