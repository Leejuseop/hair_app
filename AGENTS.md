# AGENTS.md

Project working rules for AI coding agents working on Hair App.

## Documentation Sync Rule

This project is expected to evolve over a long period. Keep documentation aligned with the actual project state.

- When code behavior changes, update the related README or docs file in the same work session.
- When API routes, request/response shapes, storage formats, data flow, setup steps, or user-facing behavior change, update documentation.
- When the product direction or technical strategy changes, update an existing docs file or create a new one under `docs/`.
- If a change does not require documentation updates, mention that explicitly in the final response.
- Documentation should describe the current implementation clearly and separate it from future plans.

## New-Chat Handoff Rule

`newchat.md` is the compact handoff file for continuing this project in a fresh AI chat.

- Read `AGENTS.md` and `newchat.md` before starting substantial work in a new chat.
- Update `newchat.md` whenever implementation status, product direction, model experiments, major blockers, or the immediate next step changes.
- Keep `newchat.md` concise and link to detailed docs instead of copying long experiment logs.
- Record whether important changes are committed and pushed so a new chat does not overwrite intentional working-tree changes.

## Current Product Direction

Hair App is a mobile web MVP for personalized hairstyle synthesis.

The current foundation is:

- Guided four-step face scanning: `front`, `left`, `right`, `hairline`.
- MediaPipe Face Landmarker in the frontend.
- Automatic good-frame capture and scan bundle upload.
- FastAPI backend storage under `backend/storage/scans/{scan_id}/`.
- Personal `base_profile.json` generation.
- Base profile preview in the frontend.

The next major direction is a high-performance general image-editing foundation model combined with Hair App-specific identity preservation, hair masks, landmarks, hairline anchors, and output validation. Hair-only research models are no longer the primary MVP path. StableHairV2 remains documented as a completed negative baseline.

Current near-term priority:

1. Benchmark `Qwen-Image-Edit-2511` and `HiDream-O1-Image` with the same portrait and hairstyle-reference inputs.
2. Benchmark `FLUX.2 [klein] Base 4B` and `LongCat-Image-Edit` as practical adaptation candidates.
3. Select one model using Hair App-specific identity, hairstyle, hairline, and artifact scores.
4. Start with LoRA or editing SFT before considering architecture changes.

`HunyuanImage-3.0-Instruct` is not an active candidate: its official recommendation is eight 80 GB GPUs, and its community license excludes South Korea from the licensed territory.

## Implementation Rules

- Keep the implementation simple and MVP-focused unless the user asks for a broader build.
- Prefer existing project patterns over introducing new abstractions.
- Do not wire a production synthesis route until a baseline model wins the controlled benchmark.
- Treat masks, landmarks, and the base profile as Hair App controls around or inside the foundation model; do not assume every model accepts them natively.
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
