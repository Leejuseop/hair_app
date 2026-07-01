# AGENTS.md

Rules for AI coding agents working on Hair App.

## Start Here

Before changing code or docs:

1. run `git status --short --branch --ignored`;
2. read `newchat.md`;
3. read the relevant docs under `docs/`;
4. inspect the actual code/scripts before relying on summaries;
5. do not revert user or previous-agent changes unless the user explicitly asks.

## Current Direction

As of 2026-06-30, the main head-generation candidate is FaceBuilder/KeenTools
automation through headless Blender.

The intended product pipeline is:

```text
ordinary selfies + in-app scan frames
  -> photo/frame scoring
  -> automated FaceBuilder solve in Blender
  -> private bald-head mesh and texture
  -> Hair App mask-aware texture correction and post-processing
  -> hair fitting/collision
  -> mobile GLB/viewer
```

The immediate next technical step is Step 6 v04 forehead edge/detail recovery
from the Step 5 `blend` baseline in
`experiments/facebuilder_mask_aware_correction/`. Step 6 v01 hard black
skin-hole fill is complete as a conservative safety pass, v02 forehead tone
repair is complete as a safe but visually weak tone pass, and v03 forehead
uniform-tone replacement is complete as a diagnostic pass that reduces patches
but looks too flat.

Pixel3DMM/FLAME and Texture Baker v1/v2/v3 are research baselines and fallback
experiments. They are not the current main quality path unless the user asks to
return to them.

## Documentation Sync Rule

Docs are part of the project state, not optional notes.

Update docs in the same change when you:

- change product direction;
- add or remove an experiment;
- change a pipeline contract, file format, API, path, or manifest;
- learn that a previous direction failed;
- verify a tool or automation path;
- change privacy or Git handling.

Keep current implementation and future plans clearly separated. Do not describe
planned workers, models, APIs, or app screens as already implemented.

## New-Chat Handoff Rule

`newchat.md` is the compact handoff for the next conversation.

Update it when:

- the main direction changes;
- a major experiment succeeds or fails;
- a new blocker appears;
- a new immediate next step becomes clear;
- code is pushed that changes how the project should resume.

Do not copy every long experiment log into `newchat.md`; link to the relevant
detailed doc instead.

## Privacy Rules

Never commit private biometric data or private generated assets:

- selfies, scan frames, or source photo folders;
- crops, masks, landmarks, UV maps, tracking videos;
- private OBJ/MTL/PLY/GLB exports;
- private textures, renders, screenshots, review sheets;
- private Drive output folders or identity-revealing paths in examples.

Allowed in Git:

- code;
- docs;
- scripts that operate on private files;
- generic/fake manifests and placeholder paths.

Private local output folders currently ignored:

```text
private_exports/
private_outputs/
```

Before staging, run `git status --short --ignored` and inspect the staged diff.

## FaceBuilder/KeenTools Notes

KeenTools FaceBuilder is used as a black-box engine through Blender and the
local extension APIs.

Important constraints:

- do not reverse-engineer compiled `.pyd` binaries;
- do not bypass licensing;
- do not commit private `.blend`, texture, or mesh outputs;
- keep automation scripts diagnostic until they have repeatable quality checks.

Useful bridge folder:

```text
experiments/facebuilder_bridge/
```

## Engineering Rules

- Prefer small, reversible changes.
- Keep private paths in docs as placeholders unless a local-only diagnostic note
  genuinely needs the exact path.
- For manual edits, use `apply_patch`.
- Use `rg`/`rg --files` for searching.
- Run focused verification before committing.
- If a change is only documentation, still check Git status and staged diff
  carefully.

## Git Rules

- Work on the current branch unless the user asks for a branch.
- Never use destructive commands like `git reset --hard` or `git checkout --`
  without explicit user approval.
- Commit only relevant code/docs.
- Push after commit when the user asks for it.
