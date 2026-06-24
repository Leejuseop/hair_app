import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";

export const SCAN_TARGET_SAMPLES = 12;
export const SCAN_STEPS = [
  "front",
  "left_45",
  "right_45",
  "left_profile",
  "right_profile",
  "hairline",
];

export const SCAN_STEP_CONFIG = {
  front: {
    geometryRole: "front_geometry",
    label: "Front geometry scan",
    readyInstruction: "정면을 보고 입을 편하게 다문 상태로 얼굴을 중앙에 맞춰주세요.",
    selected3dmmLimit: 2,
    shortLabel: "Front",
    targetSamples: 12,
    type: "front",
  },
  left_45: {
    direction: -1,
    geometryRole: "left_oblique_geometry",
    label: "Left 45° scan",
    readyInstruction: "왼쪽 45도 얼굴이 보이게 천천히 고개를 돌려주세요.",
    selected3dmmLimit: 2,
    shortLabel: "L 45°",
    targetSamples: 10,
    targetYawProxy: -0.34,
    type: "oblique",
  },
  right_45: {
    direction: 1,
    geometryRole: "right_oblique_geometry",
    label: "Right 45° scan",
    readyInstruction: "오른쪽 45도 얼굴이 보이게 천천히 고개를 돌려주세요.",
    selected3dmmLimit: 2,
    shortLabel: "R 45°",
    targetSamples: 10,
    targetYawProxy: 0.34,
    type: "oblique",
  },
  left_profile: {
    direction: -1,
    geometryRole: "left_profile_geometry",
    label: "Left profile scan",
    readyInstruction: "왼쪽 측면에 가깝게 돌려 코·입·턱 옆선이 보이게 해주세요.",
    selected3dmmLimit: 1,
    shortLabel: "L Side",
    targetSamples: 8,
    targetYawProxy: -0.6,
    type: "profile",
  },
  right_profile: {
    direction: 1,
    geometryRole: "right_profile_geometry",
    label: "Right profile scan",
    readyInstruction: "오른쪽 측면에 가깝게 돌려 코·입·턱 옆선이 보이게 해주세요.",
    selected3dmmLimit: 1,
    shortLabel: "R Side",
    targetSamples: 8,
    targetYawProxy: 0.6,
    type: "profile",
  },
  hairline: {
    geometryRole: "hairline_geometry",
    label: "Hairline scan",
    readyInstruction:
      "이마와 헤어라인이 보이게 앞머리를 살짝 치우고 정면을 유지해주세요.",
    selected3dmmLimit: 2,
    shortLabel: "Hairline",
    targetSamples: 12,
    type: "hairline",
  },
};

export function getScanTargetSamples(step) {
  return SCAN_STEP_CONFIG[step]?.targetSamples ?? SCAN_TARGET_SAMPLES;
}

const MEDIAPIPE_VERSION = "0.10.35";
const WASM_URL = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MEDIAPIPE_VERSION}/wasm`;
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task";

const KEY_POINTS = {
  foreheadTop: 10,
  foreheadCenter: 151,
  chin: 152,
  noseTip: 1,
  noseBridge: 168,
  leftEyeOuter: 33,
  rightEyeOuter: 263,
  leftBrowOuter: 70,
  rightBrowOuter: 300,
  mouthLeft: 61,
  mouthRight: 291,
  leftCheek: 234,
  rightCheek: 454,
  leftTemple: 127,
  rightTemple: 356,
};

let faceLandmarkerPromise;

export function getFaceLandmarker() {
  if (!faceLandmarkerPromise) {
    faceLandmarkerPromise = FilesetResolver.forVisionTasks(WASM_URL).then(
      (vision) =>
        FaceLandmarker.createFromOptions(vision, {
          baseOptions: {
            modelAssetPath: MODEL_URL,
          },
          numFaces: 1,
          minFaceDetectionConfidence: 0.55,
          minFacePresenceConfidence: 0.55,
          minTrackingConfidence: 0.55,
          outputFacialTransformationMatrixes: true,
          runningMode: "VIDEO",
        }),
    );
  }

  return faceLandmarkerPromise;
}

export function measureFrameQuality(video, canvas) {
  const width = 96;
  const height = 72;
  canvas.width = width;
  canvas.height = height;

  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(video, 0, 0, width, height);

  const { data } = context.getImageData(0, 0, width, height);
  const luminance = new Float32Array(width * height);
  let sum = 0;

  for (let index = 0, pixel = 0; index < data.length; index += 4, pixel += 1) {
    const value =
      0.2126 * data[index] +
      0.7152 * data[index + 1] +
      0.0722 * data[index + 2];
    luminance[pixel] = value;
    sum += value;
  }

  let gradientSum = 0;
  let gradientCount = 0;

  for (let y = 1; y < height; y += 1) {
    for (let x = 1; x < width; x += 1) {
      const offset = y * width + x;
      gradientSum +=
        Math.abs(luminance[offset] - luminance[offset - 1]) +
        Math.abs(luminance[offset] - luminance[offset - width]);
      gradientCount += 2;
    }
  }

  const brightness = sum / luminance.length / 255;
  const averageGradient = gradientSum / gradientCount;
  const sharpness = clamp((averageGradient - 3) / 24, 0, 1);

  return {
    brightness,
    sharpness,
  };
}

export function analyzeScanFrame({
  frameQuality,
  previousLandmarks,
  result,
  step,
}) {
  const landmarks = result.faceLandmarks?.[0];

  if (!landmarks) {
    return createEmptyAnalysis("얼굴이 보이게 화면 안으로 들어와 주세요.");
  }

  const common = getCommonFaceMetrics({
    frameQuality,
    landmarks,
    previousLandmarks,
    result,
  });

  const stepConfig = SCAN_STEP_CONFIG[step];

  if (stepConfig?.type === "oblique" || stepConfig?.type === "profile") {
    return analyzeTurnedFrame({ common, step, stepConfig });
  }

  if (stepConfig?.type === "hairline") {
    return analyzeHairlineFrame(common);
  }

  return analyzeFrontFrame(common);
}

export function captureVideoFrame(video) {
  const sourceWidth = video.videoWidth;
  const sourceHeight = video.videoHeight;
  const targetWidth = Math.min(sourceWidth, 720);
  const targetHeight = Math.round((targetWidth / sourceWidth) * sourceHeight);

  const canvas = document.createElement("canvas");
  canvas.width = targetWidth;
  canvas.height = targetHeight;

  const context = canvas.getContext("2d");
  context.drawImage(video, 0, 0, targetWidth, targetHeight);

  return canvas.toDataURL("image/jpeg", 0.82);
}

export function createScanSample({ analysis, imageDataUrl, sampleIndex, step }) {
  const stepConfig = SCAN_STEP_CONFIG[step];

  return {
    id: `${step}_${String(sampleIndex + 1).padStart(3, "0")}`,
    capturedAt: new Date().toISOString(),
    geometry: {
      source: "app_guided_scan",
      targetYawProxy: stepConfig?.targetYawProxy ?? 0,
      useFor: ["geometry_evidence", "texture_reference"],
      viewRole: stepConfig?.geometryRole ?? step,
    },
    imageDataUrl,
    landmarks: analysis.landmarks,
    quality: {
      score: analysis.qualityScore,
      ...analysis.metrics,
    },
    scanStep: step,
    selection: {
      candidateFor3dmm: true,
      selected3dmmLimit: stepConfig?.selected3dmmLimit ?? 1,
    },
    ...analysis.sample,
  };
}

function createEmptyAnalysis(instruction) {
  return {
    faceDetected: false,
    instruction,
    isGood: false,
    landmarks: null,
    metrics: null,
    qualityScore: 0,
    sample: null,
  };
}

function getCommonFaceMetrics({
  frameQuality,
  landmarks,
  previousLandmarks,
  result,
}) {
  const bounds = getLandmarkBounds(landmarks);
  const points = getKeyPoints(landmarks);
  const transformationMatrix = getTransformationMatrix(result);
  const matrixYaw = getMatrixYaw(transformationMatrix);
  const eyeDistance = distance(points.leftEyeOuter, points.rightEyeOuter);
  const eyeMidpoint = midpoint(points.leftEyeOuter, points.rightEyeOuter);
  const faceCenter = {
    x: (bounds.minX + bounds.maxX) / 2,
    y: (bounds.minY + bounds.maxY) / 2,
  };
  const width = bounds.maxX - bounds.minX;
  const height = bounds.maxY - bounds.minY;
  const centerOffset = {
    x: faceCenter.x - 0.5,
    y: faceCenter.y - 0.5,
  };
  const roll = radiansToDegrees(
    Math.atan2(
      points.rightEyeOuter.y - points.leftEyeOuter.y,
      points.rightEyeOuter.x - points.leftEyeOuter.x,
    ),
  );
  const yawProxy =
    (points.noseTip.x - eyeMidpoint.x) / Math.max(eyeDistance, 0.001);
  const pitchProxy =
    (points.noseTip.y - eyeMidpoint.y) /
    Math.max(points.chin.y - eyeMidpoint.y, 0.001);
  const mouthSymmetry =
    Math.abs(
      distance(points.mouthLeft, points.noseTip) -
        distance(points.mouthRight, points.noseTip),
    ) / Math.max(distance(points.mouthLeft, points.mouthRight), 0.001);
  const stability = measureStability(landmarks, previousLandmarks);

  const baseMetrics = {
    bounds: roundBounds(bounds),
    brightness: round(frameQuality.brightness),
    centerOffset: {
      x: round(centerOffset.x),
      y: round(centerOffset.y),
    },
    faceHeight: round(height),
    faceTop: round(bounds.minY),
    faceWidth: round(width),
    matrixYaw: matrixYaw === null ? null : round(matrixYaw),
    mouthSymmetry: round(mouthSymmetry),
    pitchProxy: round(pitchProxy),
    roll: round(roll),
    sharpness: round(frameQuality.sharpness),
    stability: round(stability.value),
    yawProxy: round(yawProxy),
  };

  return {
    bounds,
    centerOffset,
    frameQuality,
    height,
    landmarks,
    metrics: baseMetrics,
    mouthSymmetry,
    points,
    roll,
    stability,
    transformationMatrix,
    width,
    yawProxy,
  };
}

function analyzeFrontFrame(common) {
  const scores = getCommonScores(common);
  const qualityScore =
    scores.centered * 0.19 +
    scores.size * 0.17 +
    scores.frontYaw * 0.18 +
    scores.roll * 0.1 +
    scores.symmetry * 0.08 +
    scores.brightness * 0.11 +
    scores.sharpness * 0.07 +
    scores.stability * 0.1;
  const checks = {
    brightEnough: common.frameQuality.brightness >= 0.2,
    centered:
      Math.abs(common.centerOffset.x) <= 0.18 &&
      Math.abs(common.centerOffset.y) <= 0.2,
    distanceOk: common.height >= 0.43 && common.height <= 0.82,
    frontFacing: Math.abs(common.yawProxy) <= 0.2 && Math.abs(common.roll) <= 10,
    stable: common.stability.isStable,
  };

  return createAnalysisResult({
    common,
    instruction: getFrontInstruction({ checks, common }),
    isGood:
      checks.brightEnough &&
      checks.centered &&
      checks.distanceOk &&
      checks.frontFacing &&
      checks.stable &&
      qualityScore >= 0.72,
    qualityScore,
  });
}

function analyzeTurnedFrame({ common, step, stepConfig }) {
  const direction = stepConfig.direction;
  const directedYaw = common.yawProxy * direction;
  const scores = getCommonScores(common);
  const isProfile = stepConfig.type === "profile";
  const angleScore = isProfile
    ? scoreByRange(directedYaw, 0.34, 0.48, 0.72, 0.84)
    : scoreByRange(directedYaw, 0.12, 0.22, 0.46, 0.58);
  const qualityScore =
    scores.centered * 0.18 +
    scores.sideSize * 0.14 +
    angleScore * 0.31 +
    scores.sideRoll * 0.08 +
    scores.brightness * 0.1 +
    scores.sharpness * 0.07 +
    scores.stability * 0.12;
  const checks = {
    brightEnough: common.frameQuality.brightness >= 0.2,
    centered:
      Math.abs(common.centerOffset.x) <= 0.22 &&
      Math.abs(common.centerOffset.y) <= 0.22,
    distanceOk: common.height >= 0.38 && common.height <= 0.82,
    sideFacing: isProfile
      ? directedYaw >= 0.4 && directedYaw <= 0.84
      : directedYaw >= 0.16 && directedYaw <= 0.58,
    stable: common.stability.isStable,
    upright: Math.abs(common.roll) <= 15,
  };

  return createAnalysisResult({
    common,
    instruction: getTurnedInstruction({
      checks,
      common,
      directedYaw,
      isProfile,
      step,
    }),
    isGood:
      checks.brightEnough &&
      checks.centered &&
      checks.distanceOk &&
      checks.sideFacing &&
      checks.stable &&
      checks.upright &&
      qualityScore >= (isProfile ? 0.62 : 0.66),
    qualityScore,
  });
}

function analyzeHairlineFrame(common) {
  const scores = getCommonScores(common);
  const topMarginScore = scoreByRange(common.bounds.minY, 0.035, 0.07, 0.18, 0.26);
  const qualityScore =
    scores.centered * 0.17 +
    scores.hairlineSize * 0.14 +
    scores.frontYaw * 0.14 +
    scores.roll * 0.08 +
    topMarginScore * 0.21 +
    scores.brightness * 0.12 +
    scores.sharpness * 0.06 +
    scores.stability * 0.08;
  const checks = {
    brightEnough: common.frameQuality.brightness >= 0.2,
    centered:
      Math.abs(common.centerOffset.x) <= 0.2 &&
      Math.abs(common.centerOffset.y) <= 0.24,
    distanceOk: common.height >= 0.34 && common.height <= 0.78,
    frontFacing: Math.abs(common.yawProxy) <= 0.24 && Math.abs(common.roll) <= 12,
    stable: common.stability.isStable,
    topVisible: common.bounds.minY >= 0.035 && common.bounds.minY <= 0.26,
  };

  return createAnalysisResult({
    common,
    instruction: getHairlineInstruction({ checks, common }),
    isGood:
      checks.brightEnough &&
      checks.centered &&
      checks.distanceOk &&
      checks.frontFacing &&
      checks.stable &&
      checks.topVisible &&
      qualityScore >= 0.68,
    qualityScore,
  });
}

function createAnalysisResult({ common, instruction, isGood, qualityScore }) {
  return {
    faceDetected: true,
    instruction,
    isGood,
    landmarks: compactLandmarks(common.landmarks),
    metrics: common.metrics,
    qualityScore: round(qualityScore),
    sample: {
      bbox: common.metrics.bounds,
      keyPoints: compactKeyPoints(common.points),
      metrics: common.metrics,
      pose: {
        matrixYaw: common.metrics.matrixYaw,
        pitchProxy: common.metrics.pitchProxy,
        roll: common.metrics.roll,
        yawProxy: common.metrics.yawProxy,
      },
      transformationMatrix: common.transformationMatrix,
    },
  };
}

function getCommonScores(common) {
  return {
    brightness: scoreByRange(common.frameQuality.brightness, 0.2, 0.3, 0.78, 0.9),
    centered:
      scoreByLimit(Math.abs(common.centerOffset.x), 0.05, 0.2) * 0.6 +
      scoreByLimit(Math.abs(common.centerOffset.y), 0.07, 0.22) * 0.4,
    frontYaw: scoreByLimit(Math.abs(common.yawProxy), 0.08, 0.24),
    hairlineSize: scoreByRange(common.height, 0.34, 0.42, 0.68, 0.78),
    roll: scoreByLimit(Math.abs(common.roll), 4, 12),
    sharpness: common.frameQuality.sharpness,
    sideRoll: scoreByLimit(Math.abs(common.roll), 6, 16),
    sideSize: scoreByRange(common.height, 0.38, 0.48, 0.72, 0.82),
    size: scoreByRange(common.height, 0.43, 0.52, 0.72, 0.82),
    stability: common.stability.score,
    symmetry: scoreByLimit(common.mouthSymmetry, 0.08, 0.2),
  };
}

function getFrontInstruction({ checks, common }) {
  if (!checks.brightEnough) {
    return "조명을 조금 더 밝게 해주세요.";
  }

  if (common.height < 0.43) {
    return "조금 더 가까이 와주세요.";
  }

  if (common.height > 0.82) {
    return "조금 뒤로 가주세요.";
  }

  if (common.centerOffset.x < -0.18) {
    return "얼굴을 화면 오른쪽으로 조금 옮겨주세요.";
  }

  if (common.centerOffset.x > 0.18) {
    return "얼굴을 화면 왼쪽으로 조금 옮겨주세요.";
  }

  if (common.centerOffset.y < -0.2) {
    return "얼굴을 조금 아래로 내려주세요.";
  }

  if (common.centerOffset.y > 0.2) {
    return "얼굴을 조금 위로 올려주세요.";
  }

  if (Math.abs(common.roll) > 10) {
    return "고개를 기울이지 말고 수평으로 맞춰주세요.";
  }

  if (Math.abs(common.yawProxy) > 0.2) {
    return "정면을 바라봐 주세요.";
  }

  if (common.frameQuality.sharpness < 0.18 || !checks.stable) {
    return "좋아요. 잠시만 움직이지 말아주세요.";
  }

  return "좋아요. 그대로 유지하세요.";
}

function getTurnedInstruction({ checks, common, directedYaw, isProfile, step }) {
  const sideText = step.startsWith("left") ? "왼쪽" : "오른쪽";
  const targetText = isProfile ? "측면" : "45도";

  if (!checks.brightEnough) {
    return "조명을 조금 더 밝게 해주세요.";
  }

  if (common.height < 0.38) {
    return "조금 더 가까이 와주세요.";
  }

  if (common.height > 0.82) {
    return "조금 뒤로 가주세요.";
  }

  if (!checks.centered) {
    return "얼굴이 화면 중앙에 머물도록 맞춰주세요.";
  }

  if (!checks.upright) {
    return "고개를 기울이지 말고 수평을 유지해주세요.";
  }

  if (directedYaw < -0.08) {
    return `반대 방향입니다. ${sideText}으로 고개를 돌려주세요.`;
  }

  if (directedYaw < (isProfile ? 0.4 : 0.16)) {
    return `${sideText} ${targetText} 얼굴이 보이게 고개를 더 돌려주세요.`;
  }

  if (directedYaw > (isProfile ? 0.84 : 0.58)) {
    return "너무 많이 돌렸어요. 얼굴을 조금만 정면 쪽으로 돌려주세요.";
  }

  if (common.frameQuality.sharpness < 0.18 || !checks.stable) {
    return "좋아요. 그 각도에서 잠시만 멈춰주세요.";
  }

  return `좋아요. ${sideText} ${targetText} 각도를 그대로 유지하세요.`;
}

function getHairlineInstruction({ checks, common }) {
  if (!checks.brightEnough) {
    return "조명을 조금 더 밝게 해주세요.";
  }

  if (common.height < 0.34) {
    return "이마와 헤어라인이 잘 보이게 조금 더 가까이 와주세요.";
  }

  if (common.height > 0.78) {
    return "헤어라인이 잘리지 않게 조금 뒤로 가주세요.";
  }

  if (common.bounds.minY < 0.035) {
    return "머리 윗부분이 잘려요. 얼굴을 조금 아래로 내려주세요.";
  }

  if (common.bounds.minY > 0.26) {
    return "헤어라인이 더 보이게 얼굴을 조금 위로 올려주세요.";
  }

  if (!checks.centered) {
    return "이마가 화면 중앙에 오도록 맞춰주세요.";
  }

  if (!checks.frontFacing) {
    return "헤어라인 스캔은 정면을 유지해주세요.";
  }

  if (common.frameQuality.sharpness < 0.18 || !checks.stable) {
    return "좋아요. 이마가 보이게 잠시만 멈춰주세요.";
  }

  return "좋아요. 이마와 헤어라인이 잘 보입니다.";
}

function getLandmarkBounds(landmarks) {
  return landmarks.reduce(
    (bounds, landmark) => ({
      maxX: Math.max(bounds.maxX, landmark.x),
      maxY: Math.max(bounds.maxY, landmark.y),
      minX: Math.min(bounds.minX, landmark.x),
      minY: Math.min(bounds.minY, landmark.y),
    }),
    {
      maxX: Number.NEGATIVE_INFINITY,
      maxY: Number.NEGATIVE_INFINITY,
      minX: Number.POSITIVE_INFINITY,
      minY: Number.POSITIVE_INFINITY,
    },
  );
}

function getKeyPoints(landmarks) {
  return Object.fromEntries(
    Object.entries(KEY_POINTS).map(([name, index]) => [name, landmarks[index]]),
  );
}

function compactLandmarks(landmarks) {
  return landmarks.map((landmark) => ({
    x: round(landmark.x),
    y: round(landmark.y),
    z: round(landmark.z),
  }));
}

function compactKeyPoints(points) {
  return Object.fromEntries(
    Object.entries(points).map(([name, point]) => [
      name,
      {
        x: round(point.x),
        y: round(point.y),
        z: round(point.z),
      },
    ]),
  );
}

function getTransformationMatrix(result) {
  const matrix = result.facialTransformationMatrixes?.[0];
  const values = matrix?.data ?? matrix?.getAsFloat32Array?.();

  return values ? Array.from(values).map(round) : null;
}

function getMatrixYaw(matrix) {
  if (!matrix || matrix.length < 11) {
    return null;
  }

  return radiansToDegrees(Math.atan2(matrix[8], matrix[10]));
}

function measureStability(landmarks, previousLandmarks) {
  if (!previousLandmarks) {
    return {
      isStable: true,
      score: 0.8,
      value: 0,
    };
  }

  const indices = Object.values(KEY_POINTS);
  const movement =
    indices.reduce((sum, index) => {
      const current = landmarks[index];
      const previous = previousLandmarks[index];

      return (
        sum +
        Math.abs(current.x - previous.x) +
        Math.abs(current.y - previous.y)
      );
    }, 0) / indices.length;

  return {
    isStable: movement < 0.018,
    score: scoreByLimit(movement, 0.006, 0.026),
    value: movement,
  };
}

function distance(first, second) {
  return Math.hypot(first.x - second.x, first.y - second.y);
}

function midpoint(first, second) {
  return {
    x: (first.x + second.x) / 2,
    y: (first.y + second.y) / 2,
    z: ((first.z ?? 0) + (second.z ?? 0)) / 2,
  };
}

function scoreByLimit(value, idealMax, hardMax) {
  if (value <= idealMax) {
    return 1;
  }

  if (value >= hardMax) {
    return 0;
  }

  return 1 - (value - idealMax) / (hardMax - idealMax);
}

function scoreByRange(value, hardMin, idealMin, idealMax, hardMax) {
  if (value >= idealMin && value <= idealMax) {
    return 1;
  }

  if (value < hardMin || value > hardMax) {
    return 0;
  }

  if (value < idealMin) {
    return (value - hardMin) / (idealMin - hardMin);
  }

  return 1 - (value - idealMax) / (hardMax - idealMax);
}

function radiansToDegrees(radians) {
  return (radians * 180) / Math.PI;
}

function round(value) {
  return Math.round(value * 1000) / 1000;
}

function roundBounds(bounds) {
  return {
    maxX: round(bounds.maxX),
    maxY: round(bounds.maxY),
    minX: round(bounds.minX),
    minY: round(bounds.minY),
  };
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}
