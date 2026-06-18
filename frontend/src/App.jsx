import { useMemo, useState } from "react";

const SCAN_STEPS = ["front", "left", "right", "hairline"];

function App() {
  const [scanStarted, setScanStarted] = useState(false);
  const [activeStep, setActiveStep] = useState("front");
  const [referenceName, setReferenceName] = useState("");
  const [generationStarted, setGenerationStarted] = useState(false);

  const activeStepIndex = useMemo(
    () => SCAN_STEPS.indexOf(activeStep),
    [activeStep],
  );

  function handleStartScan() {
    setScanStarted(true);
    setActiveStep("front");
    setGenerationStarted(false);
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

        <button className="primary-button" type="button" onClick={handleStartScan}>
          Start Scan
        </button>

        <section className="preview-panel" aria-label="Camera preview placeholder">
          <div className="camera-frame">
            <div className="face-guide" />
            <span>{scanStarted ? activeStep : "camera preview"}</span>
          </div>
        </section>

        <section className="scan-steps" aria-label="Scan steps">
          {SCAN_STEPS.map((step, index) => (
            <button
              className={index === activeStepIndex ? "step active" : "step"}
              key={step}
              type="button"
              onClick={() => setActiveStep(step)}
            >
              <span>{index + 1}</span>
              {step}
            </button>
          ))}
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
          disabled={!scanStarted}
          type="button"
          onClick={handleGenerate}
        >
          Generate
        </button>

        <section className="result-panel" aria-label="Result image placeholder">
          <div className="result-placeholder">
            {generationStarted ? "result image placeholder" : "waiting for generate"}
          </div>
        </section>
      </section>
    </main>
  );
}

export default App;

