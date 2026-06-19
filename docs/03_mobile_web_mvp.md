# Mobile Web MVP

The current MVP is a mobile-first React + Vite web app that validates the guided scan and base-profile flow.

It still does not run real hairstyle synthesis, but it now runs real camera capture, real-time face landmark analysis, automatic good-frame capture, backend scan upload, and base profile preview.

## User Flow

1. User taps `Start Scan`.
2. The browser requests camera permission and starts the front-facing camera.
3. The app loads MediaPipe Face Landmarker.
4. User completes four scan steps:
   - `front`
   - `left`
   - `right`
   - `hairline`
5. Each step automatically collects 20 good samples.
6. When all steps reach 100%, the frontend uploads the scan bundle to the backend.
7. The backend stores the scan and returns a generated base profile.
8. The frontend shows a base profile preview.
9. User can select a hairstyle reference image.
10. The `Generate` button currently shows a placeholder result state.

## Frontend Scope

Implemented in `frontend/src/App.jsx` and `frontend/src/scanAnalyzer.js`:

- Browser camera startup through `navigator.mediaDevices.getUserMedia`.
- MediaPipe Face Landmarker loading through `@mediapipe/tasks-vision`.
- Real-time frame analysis.
- Scan progress and quality feedback.
- Automatic frame capture without requiring the user to manually take photos.
- Per-step sample collection.
- Scan bundle upload to `POST /api/scan`.
- Base profile preview with image, landmark dots, hairline guide, and summary metrics.

## Scan Quality Checks

The frontend estimates whether a frame is good enough using:

- Face detection.
- Face size and distance.
- Screen centering.
- Brightness.
- Sharpness.
- Pose/yaw.
- Roll/upright angle.
- Movement stability.
- Step-specific requirements for front, side, and hairline views.

## Backend Scope

Implemented in `backend/main.py`:

- Receives completed scan bundles.
- Stores frame images and sample metadata under `backend/storage/scans/{scan_id}/`.
- Writes `metadata.json`.
- Calls `ai_engine.base_profile.build_base_profile`.
- Writes `base_profile.json`.
- Serves stored images through `/storage`.

## Placeholder Scope

Still placeholder:

- Actual style reference upload persistence.
- Actual hairstyle synthesis.
- Actual generated result image.
- Long-term database-backed storage.
