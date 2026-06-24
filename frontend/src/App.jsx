import { useEffect, useMemo, useRef, useState } from "react";
import {
  SCAN_STEPS,
  SCAN_STEP_CONFIG,
  analyzeScanFrame,
  captureVideoFrame,
  createScanSample,
  getFaceLandmarker,
  getScanTargetSamples,
  measureFrameQuality,
} from "./scanAnalyzer.js";

const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

function createInitialScanState(step) {
  return {
    error: "",
    instruction:
      step === "front"
        ? "Start Scan을 누르면 정면 스캔을 시작합니다."
        : "앞 단계가 완료되면 자동으로 시작됩니다.",
    metrics: null,
    progress: 0,
    qualityScore: 0,
    samplesCount: 0,
    status: "idle",
    targetSamples: getScanTargetSamples(step),
  };
}

function createInitialScanStates() {
  return Object.fromEntries(
    SCAN_STEPS.map((step) => [step, createInitialScanState(step)]),
  );
}

function createEmptyStepMap(valueFactory) {
  return Object.fromEntries(SCAN_STEPS.map((step) => [step, valueFactory()]));
}

function createInitialUploadState() {
  return {
    baseProfile: null,
    error: "",
    message: "스캔이 완료되면 서버에 업로드합니다.",
    scanId: "",
    status: "idle",
  };
}

function createScanSessionId() {
  return crypto.randomUUID?.() ?? `scan_${Date.now()}`;
}

function getNextStep(step) {
  const index = SCAN_STEPS.indexOf(step);
  return SCAN_STEPS[index + 1] ?? null;
}

function App() {
  const analysisCanvasRef = useRef(document.createElement("canvas"));
  const lastSampleAtRef = useRef(createEmptyStepMap(() => 0));
  const previousLandmarksRef = useRef(createEmptyStepMap(() => null));
  const scanBundleRef = useRef(null);
  const scanSamplesRef = useRef(createEmptyStepMap(() => []));
  const scanSessionIdRef = useRef(createScanSessionId());
  const uploadedSessionRef = useRef(null);
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [activeStep, setActiveStep] = useState("front");
  const [cameraError, setCameraError] = useState("");
  const [cameraStatus, setCameraStatus] = useState("idle");
  const [generationStarted, setGenerationStarted] = useState(false);
  const [referenceName, setReferenceName] = useState("");
  const [scanRunId, setScanRunId] = useState(0);
  const [scanStarted, setScanStarted] = useState(false);
  const [scanStates, setScanStates] = useState(createInitialScanStates);
  const [uploadState, setUploadState] = useState(createInitialUploadState);

  const activeScan = scanStates[activeStep];
  const activeStepIndex = useMemo(
    () => SCAN_STEPS.indexOf(activeStep),
    [activeStep],
  );
  const allStepsComplete = useMemo(
    () => SCAN_STEPS.every((step) => scanStates[step].status === "complete"),
    [scanStates],
  );

  useEffect(() => {
    return () => {
      stopCameraStream();
    };
  }, []);

  function stopCameraStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }

  function updateScanState(step, patch) {
    setScanStates((current) => ({
      ...current,
      [step]: {
        ...current[step],
        ...patch,
      },
    }));
  }

  function resetScanSession() {
    lastSampleAtRef.current = createEmptyStepMap(() => 0);
    previousLandmarksRef.current = createEmptyStepMap(() => null);
    scanBundleRef.current = null;
    scanSamplesRef.current = createEmptyStepMap(() => []);
    scanSessionIdRef.current = createScanSessionId();
    uploadedSessionRef.current = null;
    setUploadState(createInitialUploadState());
    setScanStates({
      ...createInitialScanStates(),
      front: {
        ...createInitialScanState("front"),
        instruction: "카메라를 준비하는 중입니다.",
        status: "loading",
      },
    });
  }

  function buildScanBundle() {
    const completed = SCAN_STEPS.every(
      (step) =>
        scanSamplesRef.current[step].length >= getScanTargetSamples(step),
    );

    scanBundleRef.current = {
      completedAt: completed ? new Date().toISOString() : null,
      reconstructionIntent: {
        bundleType: "upload_plus_guided_scan_geometry_input",
        selected3dmmStrategy: "backend_stepwise_best_frames",
        version: "0.2",
      },
      scanSessionId: scanSessionIdRef.current,
      steps: Object.fromEntries(
        SCAN_STEPS.map((step) => [
          step,
          {
            progress: Math.min(
              100,
              Math.round(
                (scanSamplesRef.current[step].length /
                  getScanTargetSamples(step)) *
                  100,
              ),
            ),
            samples: scanSamplesRef.current[step],
            status:
              scanSamplesRef.current[step].length >= getScanTargetSamples(step)
                ? "complete"
                : "pending",
            targetSamples: getScanTargetSamples(step),
          },
        ]),
      ),
    };

    return scanBundleRef.current;
  }

  async function handleStartScan() {
    setActiveStep("front");
    setCameraError("");
    setCameraStatus("loading");
    setGenerationStarted(false);
    setScanStarted(true);
    resetScanSession();
    setScanRunId((current) => current + 1);

    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraStatus("error");
      setCameraError("This browser does not support camera access.");
      updateScanState("front", {
        error: "camera_not_supported",
        instruction: "이 브라우저에서는 카메라 접근을 지원하지 않습니다.",
        status: "error",
      });
      return;
    }

    try {
      stopCameraStream();
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: "user",
          height: { ideal: 720 },
          width: { ideal: 1280 },
        },
      });

      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }

      setCameraStatus("active");
    } catch (error) {
      stopCameraStream();
      setCameraStatus("error");
      setCameraError(
        error?.name === "NotAllowedError"
          ? "Camera permission was blocked."
          : "Camera could not be started.",
      );
      updateScanState("front", {
        error: error?.name ?? "camera_error",
        instruction: "카메라를 시작하지 못했습니다.",
        status: "error",
      });
    }
  }

  useEffect(() => {
    if (!scanStarted || cameraStatus !== "active") {
      return undefined;
    }

    const activeTargetSamples = getScanTargetSamples(activeStep);

    if (scanSamplesRef.current[activeStep].length >= activeTargetSamples) {
      return undefined;
    }

    let animationFrameId = 0;
    let cancelled = false;
    let lastAnalysisAt = 0;
    let lastVideoTime = -1;
    let nextStepTimeoutId = 0;
    const currentStep = activeStep;

    async function runScanStep() {
      updateScanState(currentStep, {
        instruction: "얼굴 분석 모델을 준비하는 중입니다.",
        status: "loading",
      });

      try {
        const faceLandmarker = await getFaceLandmarker();

        if (cancelled) {
          return;
        }

        updateScanState(currentStep, {
          instruction: SCAN_STEP_CONFIG[currentStep].readyInstruction,
          status: "scanning",
        });

        function analyzeNextFrame() {
          if (cancelled) {
            return;
          }

          const video = videoRef.current;
          const now = performance.now();

          if (
            video &&
            video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA &&
            video.currentTime !== lastVideoTime &&
            now - lastAnalysisAt > 90
          ) {
            lastAnalysisAt = now;
            lastVideoTime = video.currentTime;

            const result = faceLandmarker.detectForVideo(video, now);
            const frameQuality = measureFrameQuality(
              video,
              analysisCanvasRef.current,
            );
            const analysis = analyzeScanFrame({
              frameQuality,
              previousLandmarks: previousLandmarksRef.current[currentStep],
              result,
              step: currentStep,
            });

            previousLandmarksRef.current[currentStep] =
              result.faceLandmarks?.[0] ??
              previousLandmarksRef.current[currentStep];

            let samplesCount = scanSamplesRef.current[currentStep].length;

            if (
              analysis.isGood &&
              samplesCount < getScanTargetSamples(currentStep) &&
              now - lastSampleAtRef.current[currentStep] > 350
            ) {
              const sample = createScanSample({
                analysis,
                imageDataUrl: captureVideoFrame(video),
                sampleIndex: samplesCount,
                step: currentStep,
              });

              scanSamplesRef.current[currentStep] = [
                ...scanSamplesRef.current[currentStep],
                sample,
              ];
              lastSampleAtRef.current[currentStep] = now;
              samplesCount = scanSamplesRef.current[currentStep].length;
            }

            const progress = Math.min(
              100,
              Math.round(
                (samplesCount / getScanTargetSamples(currentStep)) * 100,
              ),
            );
            const isComplete = progress >= 100;

            if (isComplete) {
              buildScanBundle();
            }

            updateScanState(currentStep, {
              error: "",
              instruction: isComplete
                ? `${SCAN_STEP_CONFIG[currentStep].label} 완료. 좋은 프레임이 저장됐습니다.`
                : analysis.instruction,
              metrics: analysis.metrics,
              progress,
              qualityScore: analysis.qualityScore,
              samplesCount,
              status: isComplete ? "complete" : "scanning",
              targetSamples: getScanTargetSamples(currentStep),
            });

            if (isComplete) {
              const nextStep = getNextStep(currentStep);

              if (nextStep) {
                nextStepTimeoutId = window.setTimeout(() => {
                  if (!cancelled) {
                    setActiveStep(nextStep);
                  }
                }, 900);
              }

              return;
            }
          }

          animationFrameId = requestAnimationFrame(analyzeNextFrame);
        }

        animationFrameId = requestAnimationFrame(analyzeNextFrame);
      } catch (error) {
        if (cancelled) {
          return;
        }

        updateScanState(currentStep, {
          error: error?.message ?? "face_model_error",
          instruction: "얼굴 분석 모델을 불러오지 못했습니다.",
          status: "error",
        });
      }
    }

    runScanStep();

    return () => {
      cancelled = true;
      cancelAnimationFrame(animationFrameId);
      window.clearTimeout(nextStepTimeoutId);
    };
  }, [activeStep, cameraStatus, scanRunId, scanStarted]);

  useEffect(() => {
    if (!allStepsComplete || !scanBundleRef.current) {
      return undefined;
    }

    const sessionId = scanSessionIdRef.current;

    if (uploadedSessionRef.current === sessionId) {
      return undefined;
    }

    let cancelled = false;
    uploadedSessionRef.current = sessionId;

    async function uploadScanBundle() {
      setUploadState({
        baseProfile: null,
        error: "",
        message: "스캔 데이터를 서버에 저장하고 베이스 프로필을 생성하는 중입니다.",
        scanId: "",
        status: "uploading",
      });

      try {
        const response = await fetch(`${API_BASE_URL}/api/scan`, {
          body: JSON.stringify(scanBundleRef.current),
          headers: {
            "Content-Type": "application/json",
          },
          method: "POST",
        });

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(errorText || "scan upload failed");
        }

        const data = await response.json();

        if (cancelled) {
          return;
        }

        setUploadState({
          baseProfile: data.base_profile,
          error: "",
          message: "베이스 프로필이 준비됐습니다.",
          scanId: data.scan_id,
          status: "ready",
        });
      } catch (error) {
        if (cancelled) {
          return;
        }

        uploadedSessionRef.current = null;
        setUploadState({
          baseProfile: null,
          error: error?.message ?? "scan upload failed",
          message: "스캔 데이터를 서버에 저장하지 못했습니다.",
          scanId: "",
          status: "error",
        });
      }
    }

    uploadScanBundle();

    return () => {
      cancelled = true;
    };
  }, [allStepsComplete]);

  function canOpenStep(step) {
    if (!scanStarted) {
      return false;
    }

    const index = SCAN_STEPS.indexOf(step);
    return SCAN_STEPS.slice(0, index).every(
      (previousStep) => scanStates[previousStep].status === "complete",
    );
  }

  function handleGenerate() {
    setGenerationStarted(true);
  }

  return (
    <main className="app-shell">
      <section className="screen">
        <header className="app-header">
          <p className="eyebrow">Hair App MVP</p>
          <h1>Personal hairstyle preview</h1>
          <p className="intro">
            Guided scanning and reference-based generation placeholders for the
            first Hair App mobile web flow.
          </p>
        </header>

        <button
          className="primary-button"
          disabled={cameraStatus === "loading"}
          type="button"
          onClick={handleStartScan}
        >
          {cameraStatus === "loading" ? "Starting Camera..." : "Start Scan"}
        </button>

        <section className="preview-panel" aria-label="Camera preview">
          <div className={`camera-frame ${activeStep}`}>
            <video
              autoPlay
              className={
                cameraStatus === "active"
                  ? "camera-video visible"
                  : "camera-video"
              }
              muted
              playsInline
              ref={videoRef}
            />
            <div className="face-guide" />
            <span>
              {allStepsComplete
                ? "scan complete"
                : cameraStatus === "active"
                  ? activeStep
                  : cameraStatus === "loading"
                    ? "starting camera"
                    : "camera preview"}
            </span>
          </div>
          {cameraError ? <p className="camera-error">{cameraError}</p> : null}
        </section>

        {scanStarted ? (
          <section className="scan-panel" aria-label="Scan progress">
            <div className="scan-panel-heading">
              <div>
                <p>{SCAN_STEP_CONFIG[activeStep].label}</p>
                <strong>{activeScan.progress}%</strong>
              </div>
              <span className={`scan-status ${activeScan.status}`}>
                {activeScan.status}
              </span>
            </div>
            <div className="progress-track">
              <div style={{ width: `${activeScan.progress}%` }} />
            </div>
            <p className="scan-instruction">
          {allStepsComplete
                ? "전체 스캔 완료. 3DMM 입력 후보 프레임과 랜드마크가 준비됐습니다."
                : activeScan.instruction}
            </p>
            <div className="scan-metrics">
              <span>
                Frames {activeScan.samplesCount}/{activeScan.targetSamples}
              </span>
              <span>Quality {Math.round(activeScan.qualityScore * 100)}%</span>
              <span>
                Yaw{" "}
                {activeScan.metrics?.yawProxy !== undefined
                  ? activeScan.metrics.yawProxy
                  : "-"}
              </span>
              <span>
                Pitch{" "}
                {activeScan.metrics?.pitchProxy !== undefined
                  ? activeScan.metrics.pitchProxy
                  : "-"}
              </span>
            </div>
          </section>
        ) : null}

        <section className="scan-steps" aria-label="Scan steps">
          {SCAN_STEPS.map((step, index) => {
            const stepState = scanStates[step];
            const isActive = index === activeStepIndex;
            const isComplete = stepState.status === "complete";

            return (
              <button
                className={[
                  "step",
                  isActive ? "active" : "",
                  isComplete ? "complete" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                disabled={!canOpenStep(step)}
                key={step}
                type="button"
                onClick={() => setActiveStep(step)}
              >
                <span>{isComplete ? "✓" : index + 1}</span>
                {SCAN_STEP_CONFIG[step].shortLabel ?? step}
              </button>
            );
          })}
        </section>

        <label className="upload-box">
          <span>Hairstyle reference image</span>
          <input
            accept="image/*"
            type="file"
            onChange={(event) =>
              setReferenceName(event.target.files?.[0]?.name ?? "")
            }
          />
          <strong>{referenceName || "No image selected"}</strong>
        </label>

        <button
          className="generate-button"
          disabled={uploadState.status !== "ready"}
          type="button"
          onClick={handleGenerate}
        >
          Generate
        </button>

        <section className="result-panel" aria-label="Result image placeholder">
          <div className="result-placeholder">
            {generationStarted
              ? "result image placeholder"
              : "waiting for generate"}
          </div>
        </section>

        {allStepsComplete ? (
          <BaseProfilePreview uploadState={uploadState} />
        ) : null}
      </section>
    </main>
  );
}

function BaseProfilePreview({ uploadState }) {
  const profile = uploadState.baseProfile;
  const preview = profile?.preview;
  const imageUrl = resolveApiAssetUrl(preview?.front_image_url);
  const landmarks = preview?.landmarks ?? [];
  const hairlinePoints = Object.values(preview?.hairline_points ?? {});
  const faceMetrics = profile?.derived_metrics?.face ?? {};
  const hairlineMetrics = profile?.derived_metrics?.hairline ?? {};
  const reconstructionBundle = profile?.reconstruction_bundle ?? {};
  const sideMetrics = profile?.derived_metrics?.side_profile ?? {};

  return (
    <section className="base-profile-panel" aria-label="Base profile preview">
      <div className="base-profile-heading">
        <div>
          <p>Base Profile Preview</p>
          <strong>{uploadState.status}</strong>
        </div>
        {uploadState.scanId ? <span>{uploadState.scanId.slice(0, 8)}</span> : null}
      </div>
      <p className={`upload-message ${uploadState.status}`}>
        {uploadState.message}
      </p>
      {uploadState.error ? (
        <p className="upload-error">{uploadState.error}</p>
      ) : null}

      {profile && imageUrl ? (
        <>
          <div className="profile-preview-image">
            <img alt="Base profile front preview" src={imageUrl} />
            <svg aria-hidden="true" viewBox="0 0 100 100">
              {landmarks.map((point, index) => (
                <circle
                  cx={point.x * 100}
                  cy={point.y * 100}
                  key={`${point.x}-${point.y}-${index}`}
                  r="0.28"
                />
              ))}
              {hairlinePoints.length > 1 ? (
                <polyline
                  points={hairlinePoints
                    .map((point) => `${point.x * 100},${point.y * 100}`)
                    .join(" ")}
                />
              ) : null}
            </svg>
          </div>

          <div className="profile-metrics">
            <Metric label="Face ratio" value={faceMetrics.face_ratio} />
            <Metric label="Jaw proxy" value={faceMetrics.jaw_width_proxy} />
            <Metric
              label="Forehead"
              value={hairlineMetrics.forehead_height_proxy}
            />
            <Metric
              label="Side symmetry"
              value={sideMetrics.oblique_symmetry_proxy?.yaw_delta}
            />
            <Metric
              label="3DMM frames"
              value={reconstructionBundle.selected_count}
            />
          </div>
        </>
      ) : null}
    </section>
  );
}

function Metric({ label, value }) {
  return (
    <span>
      <small>{label}</small>
      <strong>{value ?? "-"}</strong>
    </span>
  );
}

function resolveApiAssetUrl(url) {
  if (!url) {
    return "";
  }

  if (url.startsWith("http")) {
    return url;
  }

  return `${API_BASE_URL}${url}`;
}

export default App;
