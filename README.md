# Hair App

Hair App is a mobile web MVP for personalized hairstyle synthesis. The project uses guided face scanning to collect structured face, hairline, and side-profile data, then turns that scan bundle into a reusable personal base profile for future hairstyle generation.

The current product is not a finished hairstyle synthesizer yet. It now validates the scan and base-profile layer: the browser opens the camera, MediaPipe Face Landmarker analyzes the face in real time, high-quality frames are captured automatically, and the FastAPI backend stores the scan data and creates a base profile JSON.

## Project Goal

Build a simple end-to-end foundation that lets a user:

- Complete a guided four-step face scan.
- Collect front, left, right, and hairline landmark samples.
- Save good frame images and structured landmark data.
- Generate a personal base profile from the scan bundle.
- Preview the base profile with a representative image and landmark overlay.
- Later combine the base profile with a hairstyle reference image for synthesis.

## Core Idea

The product combines three layers:

- Guided scanning: collect consistent face views instead of relying on one random selfie.
- Personal base profile: preserve raw landmarks, best frames, derived face metrics, hairline guide points, and synthesis anchors.
- Hairstyle synthesis: adapt a high-performance general image-editing model with identity preservation, hair masks, landmarks, and hairline controls.

This should help future synthesis models understand the user's face structure, hairline context, and side-profile cues better than a single input photo alone.

The base profile is not sent to a foundation model as raw JSON by default. Its detailed data is converted into practical controls such as frame selection, masks, hairline guides, layout inputs, and post-generation identity checks.

## Current MVP Scope

Implemented:

- React + Vite mobile-friendly frontend.
- Real browser camera preview through `getUserMedia`.
- MediaPipe Face Landmarker integration in the frontend.
- Guided scan steps: `front`, `left`, `right`, `hairline`.
- Per-step quality checks for face detection, framing, distance, lighting, sharpness, pose, and stability.
- Automatic capture of 20 good samples per scan step.
- Scan bundle upload to `POST /api/scan`.
- FastAPI backend with file-based scan storage.
- Stored scan metadata, frame images, per-sample JSON, and `base_profile.json`.
- Base profile preview with representative front image, face landmark overlay, hairline guide overlay, and summary metrics.

Still placeholder:

- Real hairstyle reference image persistence.
- Real hair synthesis inference.
- Real result image generation.
- Database, authentication, billing, and production deployment.

## Data Flow

1. The user taps `Start Scan`.
2. The frontend starts the camera and loads MediaPipe Face Landmarker.
3. The app scans four steps: `front`, `left`, `right`, and `hairline`.
4. Each step automatically saves good frames and landmarks until it reaches 100%.
5. The frontend sends one complete scan bundle to `POST /api/scan`.
6. The backend creates `backend/storage/scans/{scan_id}/`.
7. The backend writes frame images, sample JSON files, `metadata.json`, and `base_profile.json`.
8. The frontend displays the base profile preview returned by the backend.

## API Routes

- `POST /api/scan`: stores a completed scan bundle and returns a base profile.
- `GET /api/scan/{scan_id}`: reads stored scan metadata.
- `GET /api/base-profile/{scan_id}`: reads a stored base profile.
- `POST /api/style-reference`: placeholder style reference route.
- `POST /api/generate`: placeholder generation route.
- `GET /api/result/{result_id}`: placeholder result route.

## Hair Synthesis Direction

The project now prioritizes high-performance general image editing over hair-only research models. StableHairV2 proved that a specialized paper model can run successfully while still being a poor product fit: normal portraits lost identity and produced severe artifacts.

The next controlled Colab benchmark will compare `Qwen-Image-Edit-2511`, `HiDream-O1-Image`, `FLUX.2 [klein] Base 4B`, and `LongCat-Image-Edit`. The first two are quality and multi-reference candidates; the latter two are especially interesting for practical fine-tuning and training-code access.

Hair App-specific value will come from the pipeline around the foundation model:

- select the best source frame from the scan bundle.
- create face, hair, and protected-region masks.
- provide the portrait and hairstyle reference as separate inputs when supported.
- preserve identity with face similarity and landmark checks.
- enforce hairline anchors and copy protected pixels back when appropriate.
- fine-tune with LoRA or editing SFT after a baseline model wins.

Current experiment state:

- `StableHairV2`: executed successfully in Colab, but normal portraits produced severe artifacts and weak identity preservation.
- `FLUX.1 Kontext [dev]`: informally tested through a Hugging Face Space; the observed result was not strong enough to select it.
- `Qwen-Image-Edit-2511` and `HiDream-O1-Image`: selected for the next controlled baseline and not yet run in Colab.
- `HunyuanImage-3.0-Instruct`: technically capable, but excluded because of its eight-H100 recommendation and South Korea license exclusion.

## Continue In A New Chat

Read `AGENTS.md` and `newchat.md` first. `newchat.md` contains the compact current state, decisions, known experiment results, Git status, and immediate next step.

## Project Structure

```text
hair_app/
  README.md
  docs/
    01_problem_definition.md
    02_idea_evolution.md
    03_mobile_web_mvp.md
    04_scan_pipeline.md
    05_base_model_design.md
    06_hair_synthesis_pipeline.md
    07_hair_engine_experiment_plan.md
    08_general_image_editing_strategy.md
  newchat.md
  frontend/
    index.html
    package.json
    vite.config.js
    src/
      App.jsx
      main.jsx
      scanAnalyzer.js
      styles.css
  backend/
    main.py
    requirements.txt
    storage/              # local runtime data, ignored by git
  ai_engine/
    __init__.py
    face_landmark.py
    base_profile.py
    hair_synthesis.py
    postprocess.py
  experiments/
  assets/
```

## Local Development

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Backend:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt
cd backend
uvicorn main:app --reload
```

Default local URLs:

- Frontend: `http://127.0.0.1:5173/`
- Backend docs: `http://127.0.0.1:8000/docs`
