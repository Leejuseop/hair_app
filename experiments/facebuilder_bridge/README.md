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

Runs the current private v1/v2/v3/v4 FaceBuilder comparison batch from normal
Python. It prepares version/person folders, writes input manifests, launches
Blender in background mode, and builds individual plus cross-version review
sheets.

Versions:

- `v1`: original photos + raw FaceBuilder texture.
- `v2`: original photos for auto-align, same-size preprocessed photos for
  texture bake, raw FaceBuilder texture material.
- `v3`: original photos + postprocessed cleanup texture material.
- `v4`: preprocessed texture photos + postprocessed cleanup texture material.

The current v1-v4 experiment intentionally does not reject photos by quality
score. Every readable photo is attempted in every version so the only variables
are texture-input preprocessing and texture-output post-processing.

Example:

```powershell
python experiments\facebuilder_bridge\facebuilder_version_runner.py `
  --clean
```

Path defaults can be overridden with `--drive-root`, `--juseop-dir`,
`--eunchae-dir`, or the `HAIR_APP_DRIVE_ROOT`, `HAIR_APP_JUSEOP_DIR`, and
`HAIR_APP_EUNCHAE_DIR` environment variables.

Useful options:

```powershell
  --version v4 `
  --person juseop `
  --max-images 2 `
  --skip-blender
```

Private output layout:

```text
<drive_root>/output/facebuilder_v1/<person>/
<drive_root>/output/facebuilder_v2/<person>/
<drive_root>/output/facebuilder_v3/<person>/
<drive_root>/output/facebuilder_v4/<person>/
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
<drive_root>/output/_comparison/facebuilder_v1_v4/<person>_facebuilder_v1_v4_comparison.png
```

### `blender_facebuilder_batch_scene.py`

Runs inside Blender. It consumes the manifest written by
`facebuilder_version_runner.py`, creates a FaceBuilder head, adds image
candidates as cameras, tries auto-align, bakes texture, applies Hair App
material/post-process preparation, exports OBJ/GLB, renders review yaw images,
and writes `run_manifest.json`.

The Blender automation now mirrors FaceBuilder's UI import/auto-align state more
closely before texture baking:

- read EXIF/focal data for each photo candidate;
- center the FaceBuilder geometry projection after each camera import;
- after auto-align, update all camera positions and focal lengths before
  TextureBuilder runs.

This matters because TextureBuilder uses per-photo camera projection state, not
just the final mesh vertices. A head mesh can compare as nearly identical while
the baked texture is badly different if those projection values are stale.

The current post-process includes only a heuristic baked-texture cleanup:

- keep the raw FaceBuilder bake;
- create a separate `facebuilder_texture_bald_cleanup.png`;
- conservatively replace large dark blobs and obvious color leaks with a skin
  reference;
- write `bald_texture_cleanup_report.json`;
- keep the raw FaceBuilder texture as the default material/GLB/review texture;
- use the cleanup texture only when `--use-cleanup-texture` is explicitly set.

This is deliberately not treated as final product quality. The heuristic cleanup
is a controlled ablation step, not a final semantic matting system. The next
required step is semantic scalp/skin/occlusion cleanup.

### `texture_bake_settings_probe.py`

Runs inside Blender against an existing private `.blend` file and bakes several
FaceBuilder TextureBuilder setting variants. It is a parity/debugging tool for
checking whether an automated bake matches the Blender UI `Create Texture`
button result.

Example:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" `
  --background "<private_facebuilder_scene.blend>" `
  --python "C:\Users\User\Desktop\hair_app\experiments\facebuilder_bridge\texture_bake_settings_probe.py" `
  -- `
  --output-dir "<private_output_dir>\texture_settings_probe" `
  --reference "<private_manual_texture.png>"
```

## Local Verification on 2026-06-27 And 2026-06-28

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

Retired version batch:

- The previous private v1/v2/v3 outputs were retired on 2026-06-28 because
  they were generated before the camera/projection parity fix and with a
  cleanup pass that was too aggressive.
- Bulk private outputs were removed from Drive.
- Representative private review sheets were archived under:
  `G:\내 드라이브\hair_app\output\history_archive\retired_facebuilder_v1_v2_v3_20260628\`

Current v1-v4 batch run:

| Version | Person | Selected | Rejected | Preproc | Aligned | Failed | TexCams | Texture | Cleanup | OBJ | GLB | Review |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- |
| v1 | juseop | 11 | 0 | 0 | 10 | 1 | 10 | yes | yes | yes | yes | yes |
| v1 | eunchae | 8 | 0 | 0 | 7 | 1 | 7 | yes | yes | yes | yes | yes |
| v2 | juseop | 11 | 0 | 11 | 10 | 1 | 10 | yes | yes | yes | yes | yes |
| v2 | eunchae | 8 | 0 | 8 | 7 | 1 | 7 | yes | yes | yes | yes | yes |
| v3 | juseop | 11 | 0 | 0 | 10 | 1 | 10 | yes | yes | yes | yes | yes |
| v3 | eunchae | 8 | 0 | 0 | 7 | 1 | 7 | yes | yes | yes | yes | yes |
| v4 | juseop | 11 | 0 | 11 | 10 | 1 | 10 | yes | yes | yes | yes | yes |
| v4 | eunchae | 8 | 0 | 8 | 7 | 1 | 7 | yes | yes | yes | yes | yes |

Cross-version comparison sheets:

- `G:\내 드라이브\hair_app\output\_comparison\facebuilder_v1_v4\juseop_facebuilder_v1_v4_comparison.png`
- `G:\내 드라이브\hair_app\output\_comparison\facebuilder_v1_v4\eunchae_facebuilder_v1_v4_comparison.png`

Texture bake parity check:

- Manual reference: the user created `ha.png` in Blender by pressing
  FaceBuilder Texture > `Create Texture` after auto-aligning the same 10 Juseop
  photos.
- Previous headless bake called the correct `bake_tex` function, but it skipped
  parts of the UI camera/projection update flow. It matched the solved mesh, but
  not the texture projection state.
- The previous raw headless texture differed from `ha.png` by mean RGB error
  about `18.14`.
- Sweeping TextureBuilder settings alone did not solve the issue; the best
  tested settings variant still had mean RGB error about `15.44`.
- After matching the UI import/auto-align camera updates, the automated raw bake
  differed from `ha.png` by mean RGB error about `0.12`, which is close enough
  to treat as the same FaceBuilder texture bake path.
- The old heuristic cleanup texture still differed badly from the manual raw
  reference and should not be used as the default material.

Conclusion: the automation bridge is now real enough to generate comparable
private v1/v2/v3/v4 artifacts without manual clicking. Codex can run Blender
headlessly, drive key FaceBuilder operations, write diagnostics, export GLB, and
iterate on scripts.

Quality conclusion: v1 is now the correct raw FaceBuilder baseline. v2/v4 prove
that same-size preprocessed texture photos can be swapped in successfully, but
the first conservative non-face mute creates visible neutral patches and is not
good enough. v3/v4 prove that postprocessed texture material can be routed into
GLB/review output, but the heuristic cleanup is still not product quality.
Visible problems remain: hair/scalp patches, eye material, mouth/nostril
regions, neck/ear seams, clothing/background leakage, and non-semantic
over-replacement.

## Current Limitations

- Auto-align quality still affects final geometry/texture heavily.
- FaceBuilder can fail face detection on occluded/glasses images.
- The current v1/v2/v3/v4 runner is a local research pipeline, not production job
  orchestration.
- Photo scoring exists as a diagnostic report but is intentionally disabled as
  a rejection gate in the current v1-v4 ablation.
- The same-size preprocessed-photo pass is heuristic. It reduces some obvious
  texture pollution but can create large neutral skin-color patches on the
  rendered head.
- The cleanup pass is heuristic color/component replacement, not semantic
  matting. It can reduce ugly artifacts but cannot reliably know "hair versus
  eyebrow" or "skin versus background."
- FaceBuilder mesh topology may or may not be directly suitable for Hair App
  hair fitting; this must be evaluated after better exports.
- The bridge does not modify KeenTools internals or bypass licensing.

## Next Work

1. Review v1/v2/v3/v4 private sheets with the user.
2. Replace heuristic input preprocessing and cleanup with semantic processing:
   - face/skin/scalp/hair/background/neck/ear masks;
   - eye, iris, eyelid, mouth, lip, brow, and nostril materials;
   - confidence and provenance maps for observed versus filled regions.
3. Reintroduce stronger input analysis before FaceBuilder after the current
   ablation is understood:
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
