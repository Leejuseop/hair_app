# FaceBuilder Bridge

This folder contains local bridge tools for evaluating FaceBuilder/KeenTools as
Hair App's primary bald-head generation engine.

The tools are diagnostic and automation-proving scripts. They should not commit
private photos, private meshes, private textures, `.blend` files, review
renders, or any other biometric output.

## Why This Exists

The custom Pixel3DMM/FLAME Texture Baker v1/v2/v3 path produced useful research
artifacts but visibly poor identity quality. FaceBuilder generated a much more
promising head/texture result from the same kind of user photos, so the current
project direction is to test whether FaceBuilder can be automated enough for
Hair App's product flow.

The target is:

```text
private selfies / app scan frames
  -> automated FaceBuilder solve in headless Blender
  -> private mesh + texture + blend
  -> Hair App cleanup/post-process
  -> bald-head GLB and hair fitting
```

## Scripts

### `inspect_facebuilder_export.py`

Inspects a private FaceBuilder OBJ/MTL/texture export without calling
KeenTools. It parses geometry, checks material linkage, writes summary metrics,
and creates a CPU-rendered yaw review sheet.

Example:

```powershell
python experiments\facebuilder_bridge\inspect_facebuilder_export.py `
  --obj "<private_export_dir>\facebuilder_juseop.obj" `
  --texture "<private_export_dir>\texture.png" `
  --output-dir "C:\Users\User\Desktop\hair_app\private_outputs\facebuilder_bridge\juseop_export_v0"
```

Private outputs:

```text
summary.json
texture_preview.png
render_contact_sheet.png
render_yaw_*.png
```

### `blender_facebuilder_smoke.py`

Runs inside Blender background mode and uses no private photos. It verifies:

- Blender can load the KeenTools extension;
- `pykeentools` imports;
- a FaceBuilder object can be created;
- `detect_faces` can be called on a generated blank image;
- TextureBuilder API objects are visible.

Example:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" `
  --background `
  --python "C:\Users\User\Desktop\hair_app\experiments\facebuilder_bridge\blender_facebuilder_smoke.py" `
  -- `
  --output "C:\Users\User\Desktop\hair_app\private_outputs\facebuilder_bridge\headless_smoke.json"
```

### `blender_facebuilder_scene_probe.py`

Runs inside Blender background mode against an existing private `.blend` file.
It can inspect FaceBuilder heads/cameras/pin counts, try code-only auto-align on
unpinned cameras, and optionally run TextureBuilder.

Example:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" `
  --background "<private_blend_file>" `
  --python "C:\Users\User\Desktop\hair_app\experiments\facebuilder_bridge\blender_facebuilder_scene_probe.py" `
  -- `
  --try-align-unpinned `
  --max-align-attempts 1 `
  --output "C:\Users\User\Desktop\hair_app\private_outputs\facebuilder_bridge\scene_probe.json"
```

Optional texture bake flags:

```powershell
  --bake-texture `
  --texture-output "C:\Users\User\Desktop\hair_app\private_outputs\facebuilder_bridge\texture_bake.png"
```

### `blender_facebuilder_auto_scene_v0.py`

Starts from an empty Blender session, creates a FaceBuilder head, adds the first
N images from a private folder as FaceBuilder cameras, attempts code-only
auto-align, optionally bakes a texture, and optionally saves a private `.blend`.

Example:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" `
  --background `
  --python "C:\Users\User\Desktop\hair_app\experiments\facebuilder_bridge\blender_facebuilder_auto_scene_v0.py" `
  -- `
  --person "juseop" `
  --input-dir "<private_photo_dir>" `
  --max-images 2 `
  --bake-texture `
  --save-blend `
  --output-dir "C:\Users\User\Desktop\hair_app\private_outputs\facebuilder_bridge\auto_scene_v0_juseop"
```

### `facebuilder_version_runner.py`

Runs the current private v1/v2/v3 FaceBuilder comparison batch from normal
Python. It prepares version/person folders, scores photos, writes input
manifests, launches Blender in background mode, and builds review sheets.

Versions:

- `v1`: all photos, baseline FaceBuilder auto-align, no pre-score rejection.
- `v2`: v1 plus photo quality scoring and selection.
- `v3`: v2 plus face-centered alignment candidates and a stricter texture gate.

The v3 texture gate is intentionally conservative: frontal/color-clean crops can
contribute to texture, while profile or heavily clipped photos can still help
alignment but are disabled for texture baking. This reduced some background and
colored-light leakage, but it is not a final semantic cleanup system.

Example:

```powershell
python experiments\facebuilder_bridge\facebuilder_version_runner.py `
  --quality-threshold 0.80 `
  --clean
```

Path defaults can be overridden with `--drive-root`, `--juseop-dir`,
`--eunchae-dir`, or the `HAIR_APP_DRIVE_ROOT`, `HAIR_APP_JUSEOP_DIR`, and
`HAIR_APP_EUNCHAE_DIR` environment variables.

Useful options:

```powershell
  --version v3 `
  --person juseop `
  --max-images 2 `
  --skip-blender
```

Private output layout:

```text
<drive_root>/output/facebuilder_v1/<person>/
<drive_root>/output/facebuilder_v2/<person>/
<drive_root>/output/facebuilder_v3/<person>/
  00_input_manifest/
  01_working_images/
  02_alignment/
  03_facebuilder_scene/
  04_exports/
  05_postprocess/
  06_glb/
  07_review_sheets/
  logs/
```

Batch-level summaries:

```text
<drive_root>/output/facebuilder_versions_batch_manifest.json
<drive_root>/output/facebuilder_versions_summary.json
<drive_root>/output/facebuilder_versions_summary.md
```

### `blender_facebuilder_batch_scene.py`

Runs inside Blender. It consumes the manifest written by
`facebuilder_version_runner.py`, creates a FaceBuilder head, adds image
candidates as cameras, tries auto-align, bakes texture, applies Hair App
material/post-process preparation, exports OBJ/GLB, renders review yaw images,
and writes `run_manifest.json`.

The current post-process includes only a heuristic baked-texture cleanup:

- keep the raw FaceBuilder bake;
- create a separate `facebuilder_texture_bald_cleanup.png`;
- replace empty texels, large dark blobs, and obvious color leaks with a skin
  reference;
- write `bald_texture_cleanup_report.json`;
- use the cleanup texture for the current GLB and review renders.

This is deliberately not treated as final product quality. The next required
step is semantic scalp/skin/occlusion cleanup.

## Local Verification on 2026-06-27

Environment:

- Blender executable:
  `C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`
- Blender version observed: 5.1.2
- KeenTools version observed: 2026.2.0
- KeenTools extension path:
  `C:\Users\User\AppData\Roaming\Blender Foundation\Blender\5.1\extensions\user_default\keentools`
- Core `pykeentools` code is compiled as a local `.pyd`; it is not readable
  Python source and must be treated as a licensed black-box dependency.

Smoke test:

- background Blender loaded KeenTools;
- `pykeentools` status was `PYKEENTOOLS_OK`;
- FaceBuilder object construction worked;
- `detect_faces` was callable;
- TextureBuilder API objects were visible.

Existing-scene probe:

- tested against the user's private FaceBuilder `.blend`;
- scene had one FaceBuilder head, 11 cameras, and 6 cameras with pins before
  probing;
- re-aligning an already pinned camera succeeded;
- among five unpinned cameras, four auto-align attempts succeeded and one
  failed with zero detected faces;
- the no-face case is likely the eyeglasses selfie the user mentioned;
- texture baking ran in background mode and saved a private PNG.

Empty-scene automation v0:

- started from a blank Blender session;
- created a FaceBuilder head;
- selected two private Juseop photos;
- added them as cameras;
- one photo auto-aligned with preset pins;
- one photo failed face detection;
- texture baking still succeeded from the aligned photo;
- a private `.blend`, private texture PNG, and `result.json` were saved under
  `private_outputs/facebuilder_bridge/`.

Version batch run:

| Version | Person | Selected | Rejected | Aligned | Failed | TexCams | Texture | Cleanup | OBJ | GLB | Review |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- |
| v1 | juseop | 11 | 0 | 10 | 1 | 10 | yes | yes | yes | yes | yes |
| v1 | eunchae | 8 | 0 | 7 | 1 | 7 | yes | yes | yes | yes | yes |
| v2 | juseop | 7 | 4 | 6 | 1 | 6 | yes | yes | yes | yes | yes |
| v2 | eunchae | 7 | 1 | 6 | 1 | 6 | yes | yes | yes | yes | yes |
| v3 | juseop | 7 | 4 | 7 | 0 | 2 | yes | yes | yes | yes | yes |
| v3 | eunchae | 7 | 1 | 7 | 0 | 1 | yes | yes | yes | yes | yes |

Conclusion: the automation bridge is now real enough to generate comparable
private v1/v2/v3 artifacts without manual clicking. Codex can run Blender
headlessly, drive key FaceBuilder operations, write diagnostics, export GLB, and
iterate on scripts.

Quality conclusion: v3 is the best current automated version, but it is still
not product quality. It improves failure rate and reduces the worst photo
contamination, yet visible problems remain: hair/scalp patches, eye material,
mouth/nostril regions, neck/ear seams, and occasional texture leakage from
photo background or clothing.

## Current Limitations

- Auto-align quality still affects final geometry/texture heavily.
- FaceBuilder can fail face detection on occluded/glasses images.
- The current v1/v2/v3 runner is a local research pipeline, not production job
  orchestration.
- Photo scoring is still coarse. It uses sharpness, exposure, contrast,
  clipping, resolution, OpenCV face size/center signals, and simple color-cast
  scoring, but it does not yet use robust landmarks, eye/mouth state, glasses,
  hands, phone, hair, or segmentation confidence.
- The cleanup pass is heuristic color/component replacement, not semantic
  matting. It can reduce ugly artifacts but cannot reliably know "hair versus
  eyebrow" or "skin versus background."
- FaceBuilder mesh topology may or may not be directly suitable for Hair App
  hair fitting; this must be evaluated after better exports.
- The bridge does not modify KeenTools internals or bypass licensing.

## Next Work

1. Review v1/v2/v3 private sheets and decide whether v3 is the right base for
   the next pass.
2. Replace heuristic cleanup with semantic post-processing:
   - face/skin/scalp/hair/background/neck/ear masks;
   - eye, iris, eyelid, mouth, lip, brow, and nostril materials;
   - confidence and provenance maps for observed versus filled regions.
3. Add stronger input analysis before FaceBuilder:
   - robust landmarks;
   - pose/yaw;
   - eye closed / mouth open;
   - glasses, phone, hand, hair, and headwear occlusion;
   - segmentation confidence;
   - lighting and color normalization.
4. Evaluate mesh strategy:
   - use FaceBuilder mesh directly if scalp mapping and hair collision work;
   - otherwise transfer/retopologize to a controlled app head mesh.
5. After the bald-head substrate is credible, move to hair reconstruction,
   hairline-aware fitting, collision correction, and mobile GLB/viewer work.
