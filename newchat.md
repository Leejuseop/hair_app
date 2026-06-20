# Hair App New-Chat Handoff

Last synchronized: 2026-06-20

This is the compact handoff for continuing Hair App in a fresh AI chat. Read `AGENTS.md` first, then this file. Treat the repository and current `git status` as the source of truth when this summary and code differ.

## First Actions In A New Chat

1. Run `git status --short --branch`.
2. Do not discard local changes; they are intentional unless the user says otherwise.
3. Read the specific docs linked below before changing that subsystem.
4. Do not commit or push unless the user explicitly asks.

## Repository State

- Local workspace: `C:\Users\User\Documents\hair_app`
- GitHub: `https://github.com/Leejuseop/hair_app`
- Branch: `main`, tracking `origin/main`
- StableHairV2 baseline commit before this handoff: `f7269c0 docs: record StableHairV2 baseline results`.
- This handoff is intended to be committed with the documentation synchronization. Run `git log -1 --oneline` and `git status --short --branch` for the actual latest state.

## Product Goal

Hair App is a mobile web MVP for personalized hairstyle preview.

Primary still-image goal:

```text
user portrait + hairstyle reference + personal scan controls -> realistic edited portrait
```

A future real-time AR mode is possible, but it is not the current implementation target.

The guided scan exists because a normal two-image editor may distort identity or ignore the user's real hairline. Scan data should improve source-frame selection, masking, hairline alignment, geometric validation, and output ranking.

## Current Implementation

### Frontend

- React 18 + Vite mobile web app.
- Real camera through `getUserMedia`.
- MediaPipe Face Landmarker runs in `VIDEO` mode with one face.
- Guided scan order: `front`, `left`, `right`, `hairline`.
- Each step automatically collects 20 good samples; the user does not press a capture button.
- Frame checks include detection, face size/distance, centering, brightness, sharpness, yaw, roll, and stability.
- After all four steps complete, the frontend uploads one scan bundle to `POST /api/scan`.
- Base profile preview displays the best front image, landmarks, hairline guide, and derived metrics.
- Hairstyle file input exists, but the file is not persisted.
- `Generate` and the result image are placeholders.

Important files:

- `frontend/src/App.jsx`
- `frontend/src/scanAnalyzer.js`
- `frontend/src/styles.css`

### Backend

- FastAPI backend in `backend/main.py`.
- Real routes:
  - `POST /api/scan`
  - `GET /api/scan/{scan_id}`
  - `GET /api/base-profile/{scan_id}`
- Placeholder routes:
  - `POST /api/style-reference`
  - `POST /api/generate`
  - `GET /api/result/{result_id}`
- Scan data is stored as local files under `backend/storage/scans/{scan_id}/`; there is no database yet.
- `backend/storage/` is ignored by Git.

Storage shape:

```text
backend/storage/scans/{scan_id}/
  metadata.json
  base_profile.json
  front/
  left/
  right/
  hairline/
```

### AI Engine

- `ai_engine/base_profile.py` is real and generates `base_profile.json` version `0.1`.
- It preserves raw landmark samples and adds best assets, derived metrics, synthesis anchors, and preview data.
- `face_landmark.py`, `hair_synthesis.py`, and `postprocess.py` remain placeholders.
- The current base profile is structured 2D scan data, not a 3D avatar or trained AI model.

## Current Synthesis Direction

The project has moved away from using a hair-only research model as the primary engine.

Current architecture:

1. Use a high-performance general open-weight image-editing foundation model.
2. Supply user portrait and hairstyle reference separately when multi-reference editing is supported.
3. Convert scan JSON into useful controls rather than expecting the model to understand raw JSON.
4. Preserve identity with masks, protected-region compositing, face similarity, landmark checks, retry, and ranking.
5. Fine-tune the best raw baseline with LoRA or editing SFT.

Do not train a foundation model from scratch. Building the Hair App-specific pipeline, data, controls, losses, and deployment around an existing foundation is the intended engineering and learning project.

## Model Experiments And Decisions

### StableHairV2

- Official inference was successfully run in Google Colab after fixing Drive file IDs, pinning `huggingface_hub==0.30.0`, downloading SD 1.5 locally, and patching fp16 dtypes.
- It outputs a multi-view MP4 and expects a bald or hair-cleared identity source.
- A normal source portrait plus hairstyle reference produced severe face/background artifacts and poor identity preservation.
- It is a completed negative baseline, not the next MVP engine.
- The exact rerun recipe is preserved in `docs/07_hair_engine_experiment_plan.md`.

### FLUX.1 Kontext Dev

- The user informally tried a Hugging Face Space.
- The observed result was not satisfactory.
- This does not evaluate the newer FLUX.2 family.

### Active Baseline Order

1. `Qwen-Image-Edit-2511`
   - First controlled Colab baseline.
   - Explicit multi-image editing support.
   - LoRA recipes exist in ModelScope DiffSynth-Studio.
2. `HiDream-O1-Image` full
   - Second controlled baseline.
   - 8B unified model with editing, multi-reference personalization, native 2K, layout, and skeleton controls.
3. `FLUX.2 [klein] Base 4B`
   - Practical multi-reference fine-tuning candidate.
   - Small Apache 2.0 base checkpoint designed for LoRA/customization.
4. `LongCat-Image-Edit`
   - 6B model with official edit SFT, LoRA, DPO, and edit-DPO code.
   - Documented pipeline is single-reference, so exact hairstyle-reference transfer may need adaptation.
5. `Step1X-Edit-v1p2`
   - Additional reasoning-oriented instruction-editing baseline.

Qwen and HiDream have not yet been run in Colab for Hair App. Do not describe them as tested.

### HunyuanImage-3.0-Instruct

- Technically attractive: reasoning-based editing and fusion of up to three input images.
- 80B total parameters, 13B active MoE.
- Official recommendation for Instruct and Instruct-Distil: at least eight 80 GB GPUs.
- Distil reduces sampling to eight steps but does not remove the large memory requirement.
- Tencent's community license excludes South Korea from the licensed territory.
- Therefore it is excluded from the active Hair App implementation shortlist.
- `zxcemk4/HunyuanImage-3.0-Instruct` is only a personal mirror of the official checkpoint: 86 files, about 168.7 GB, 32 identical weight shards, no quantization or hardware reduction.

## Immediate Next Step

Create a clean Colab baseline for `Qwen-Image-Edit-2511` using:

- the same source portrait used in prior experiments.
- the same hairstyle-reference image.
- an explicit prompt that transfers only the hairstyle and preserves face, pose, expression, clothing, lighting, and background.
- multiple fixed seeds with saved inputs, prompts, runtime, and outputs.

Then run the same test with `HiDream-O1-Image` and compare:

- identity similarity.
- hairstyle-reference similarity.
- hairline and temple fit.
- landmark displacement.
- background and clothing preservation.
- visible artifacts.
- GPU memory and inference time.

Do not fine-tune until these raw baselines are compared. If quality is close, prefer the model with the simpler and cheaper tuning path.

## Colab And Tooling Notes

- The user has access to paid Colab GPUs, including high-end options when available.
- Previous Colab work was performed by giving the user complete copy-paste cells.
- Direct control of the user's Colab browser was attempted but unavailable in the current environment, so do not claim that browser automation works without reconnecting and verifying it.
- Large model files in `/content` disappear when the Colab runtime is deleted; Google Drive files persist.

## Documentation Map

- `README.md`: project overview, current implementation, and active direction.
- `docs/01_problem_definition.md`: product problem and hypothesis.
- `docs/02_idea_evolution.md`: why the direction changed.
- `docs/03_mobile_web_mvp.md`: current frontend/backend user flow.
- `docs/04_scan_pipeline.md`: capture data and storage layout.
- `docs/05_base_model_design.md`: `base_profile.json` design.
- `docs/06_hair_synthesis_pipeline.md`: planned synthesis architecture.
- `docs/07_hair_engine_experiment_plan.md`: historical StableHairV2 run and exact Colab recovery recipe.
- `docs/08_general_image_editing_strategy.md`: active model shortlist and benchmark plan.

## Working Rules And User Preferences

- Communicate in Korean and keep explanations direct.
- The user sometimes asks for an answer or plan before execution; obey that wording exactly.
- Keep the implementation simple and MVP-focused.
- Update relevant docs in the same session whenever code, APIs, storage, behavior, experiments, or strategy changes.
- Preserve raw scan data; summaries must not replace detailed landmarks.
- Do not commit or push unless explicitly asked.
- Before committing, inspect status and stage only intended files.
- Never overwrite unrelated local changes.

## Local Development

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Backend:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt
cd backend
uvicorn main:app --reload
```

- Frontend: `http://127.0.0.1:5173/`
- Backend docs: `http://127.0.0.1:8000/docs`
- Two local servers are expected: Vite serves the browser UI and FastAPI serves APIs/storage.
