# Hair App

Hair App is a mobile web MVP for personalized hairstyle synthesis. The project explores guided face scanning, personal base model generation, and reference-driven hair rendering to help users preview hairstyles on a face model that matches their own head shape and facial proportions.

## Project Goal

Build a simple end-to-end MVP that lets a user:

- Complete a guided face scan flow.
- Upload a target hairstyle reference image.
- Generate a personalized hairstyle preview.
- Review a placeholder result image while the real AI pipeline is developed.

## Core Idea

The product combines two major ideas:

- Guided face scanning: collect structured front, left, right, and hairline views so the system can understand the user's face and head geometry.
- Personal base model generation: convert scan outputs into a reusable personal profile that can support hairstyle synthesis across multiple references.

The MVP keeps the interface, API boundaries, and AI module boundaries clear while deferring camera capture, real face landmarking, 3D reconstruction, and image synthesis.

## MVP Scope

Included in this initial setup:

- React + Vite mobile-friendly frontend.
- Start scan flow UI with four scan steps.
- Camera preview placeholder.
- Hairstyle reference image upload input.
- Generate button.
- Result image placeholder.
- FastAPI backend with placeholder routes.
- AI engine module stubs for future implementation.
- Project documentation for the problem, MVP, scan pipeline, base model, and hair synthesis pipeline.

Not included yet:

- Real camera capture.
- Real file upload persistence.
- Face landmark detection.
- Personal base model generation.
- Hair synthesis or post-processing.
- Authentication, billing, or production deployment.

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
  frontend/
    index.html
    package.json
    vite.config.js
    src/
      App.jsx
      main.jsx
      styles.css
  backend/
    main.py
    requirements.txt
  ai_engine/
    __init__.py
    face_landmark.py
    base_profile.py
    hair_synthesis.py
    postprocess.py
  experiments/
    .gitkeep
  assets/
    .gitkeep
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
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

