# AGENTS.md

Project working rules for AI coding agents working on Hair App.

## Documentation Sync Rule

This project is expected to evolve over a long period. Keep documentation aligned with the actual project state.

- When code behavior changes, update the related README or docs file in the same work session.
- When API routes, request/response shapes, storage formats, data flow, setup steps, or user-facing behavior change, update documentation.
- When the product direction or technical strategy changes, update an existing docs file or create a new one under `docs/`.
- If a change does not require documentation updates, mention that explicitly in the final response.
- Documentation should describe the current implementation clearly and separate it from future plans.

## Current Product Direction

Hair App is a mobile web MVP for personalized hairstyle synthesis.

The current foundation is:

- Guided four-step face scanning: `front`, `left`, `right`, `hairline`.
- MediaPipe Face Landmarker in the frontend.
- Automatic good-frame capture and scan bundle upload.
- FastAPI backend storage under `backend/storage/scans/{scan_id}/`.
- Personal `base_profile.json` generation.
- Base profile preview in the frontend.

The next major direction is open-source hair synthesis model experimentation. Current performance-first priority:

1. `StableHairV2` / `HairPort`
2. `Stable-Hair`
3. `HairFusion`
4. `HairFastGAN`

## Implementation Rules

- Keep the implementation simple and MVP-focused unless the user asks for a broader build.
- Prefer existing project patterns over introducing new abstractions.
- Do not implement real AI synthesis until the model experiment direction is explicitly chosen.
- Keep placeholder routes clearly labeled as placeholders.
- Preserve raw scan/landmark data when possible; summaries should not replace detailed data.
- Treat `backend/storage/` as local runtime data that should stay out of git.

## Frontend Rules

- The frontend is React + Vite.
- Keep the UI mobile-friendly.
- Preserve the current scan flow unless the user asks to redesign it.
- If camera, scan, or upload behavior changes, verify the user-facing state text and docs.

## Backend Rules

- The backend is FastAPI.
- Keep API responses simple JSON for now.
- Keep file-based storage until the user explicitly decides to add a database.
- If storage layout changes, update `README.md` and `docs/04_scan_pipeline.md`.
- If `base_profile.json` changes, update `docs/05_base_model_design.md`.

## Git Rules

- Do not commit or push unless the user asks.
- Before committing, check `git status --short --branch`.
- Stage only files related to the requested change.
- After pushing, report the commit hash and branch.
