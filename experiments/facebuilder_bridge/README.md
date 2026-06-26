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

Conclusion: full app automation is not solved yet, but the important bridge is
possible. Codex can run Blender headlessly, drive key FaceBuilder operations,
write diagnostics, and iterate on scripts without the user manually clicking
every step.

## Current Limitations

- Auto-align quality still affects final geometry/texture heavily.
- FaceBuilder can fail face detection on occluded/glasses images.
- The current v0 runner only proves feasibility with a small photo subset.
- It does not yet implement photo scoring, retry policy, batch solving, export,
  review sheets, or bald-head cleanup.
- FaceBuilder mesh topology may or may not be directly suitable for Hair App
  hair fitting; this must be evaluated after better exports.
- The bridge does not modify KeenTools internals or bypass licensing.

## Next Work

1. Build automation v1 for all accepted Juseop/Eunchae photos.
2. Add pre-FaceBuilder photo scoring:
   - blur;
   - face detection confidence;
   - pose/yaw;
   - lighting;
   - occlusion from glasses, hands, phone, hair, headwear;
   - eye closed / mouth open;
   - landmark stability if available.
3. Add automatic retry/reject logic around failed or weak alignment.
4. Export private mesh/texture candidates and write manifests.
5. Generate front-to-45 review sheets for visual comparison.
6. Design post-processing for a clean bald-head substrate:
   - remove hair/headwear/shirt leakage;
   - fill scalp/neck/rear head;
   - improve eyes, mouth, lips, ears, and skin material;
   - prepare GLB-ready regions for hair fitting.
