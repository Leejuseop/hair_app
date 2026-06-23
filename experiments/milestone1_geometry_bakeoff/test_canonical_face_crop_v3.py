import math
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image


sys.path.insert(0, str(Path(__file__).resolve().parent))

from canonical_face_crop_v2 import FaceObservationV2
from canonical_face_crop_v3 import (
    CANONICAL_FIVE_POINT_TEMPLATE,
    canonical_crop_v3,
    estimate_five_point_roll,
)


def make_observation(points, score=0.98):
    points = np.asarray(points, dtype=np.float64)
    minimum = points.min(axis=0) - np.asarray([80.0, 100.0])
    maximum = points.max(axis=0) + np.asarray([80.0, 100.0])
    return FaceObservationV2(
        bbox_xyxy=(float(minimum[0]), float(minimum[1]), float(maximum[0]), float(maximum[1])),
        landmarks5_xy=tuple(tuple(float(value) for value in point) for point in points),
        score=score,
    )


def rotate_template(degrees, scale=100.0, translation=(300.0, 280.0), template=None):
    points = np.asarray(
        CANONICAL_FIVE_POINT_TEMPLATE if template is None else template,
        dtype=np.float64,
    )
    angle = math.radians(degrees)
    rotation = np.asarray(
        [[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]],
        dtype=np.float64,
    )
    return scale * points @ rotation.T + np.asarray(translation, dtype=np.float64)


class CanonicalFaceCropV3Tests(unittest.TestCase):
    def test_exact_five_point_constellation_recovers_known_roll(self):
        observation = make_observation(rotate_template(27.0))

        fit = estimate_five_point_roll(observation)

        self.assertAlmostEqual(fit["roll_degrees"], 27.0, places=6)
        self.assertLess(fit["normalized_fit_residual"], 1e-10)
        self.assertEqual(fit["warnings"], [])

    def test_five_point_fit_is_less_sensitive_than_eye_line_to_one_bad_eye(self):
        true_roll = 12.0
        points = rotate_template(true_roll)
        points[1] += np.asarray([0.0, 45.0])
        observation = make_observation(points)
        eye_vector = points[1] - points[0]
        eye_only_roll = math.degrees(math.atan2(eye_vector[1], eye_vector[0]))

        fit = estimate_five_point_roll(observation)

        self.assertLess(
            abs(fit["roll_degrees"] - true_roll),
            abs(eye_only_roll - true_roll),
        )

    def test_yaw_like_horizontal_compression_keeps_roll_close(self):
        distorted = CANONICAL_FIVE_POINT_TEMPLATE.copy()
        distorted[:, 0] *= 0.58
        distorted[2, 0] += 0.12
        distorted[3:, 0] += 0.07
        observation = make_observation(rotate_template(-18.0, template=distorted))

        fit = estimate_five_point_roll(observation)

        self.assertAlmostEqual(fit["roll_degrees"], -18.0, delta=2.0)

    def test_crop_applies_five_point_roll_and_keeps_v2_contract(self):
        observation = make_observation(rotate_template(21.0, translation=(350.0, 300.0)))
        image = Image.new("RGB", (700, 600), color=(80, 120, 160))

        result = canonical_crop_v3(image, observation)

        self.assertEqual(result.image.size, (512, 512))
        self.assertEqual(result.observed_source_mask.size, (512, 512))
        self.assertEqual(result.metadata["version"], "0.3")
        self.assertEqual(result.metadata["roll_method"], "nose_anchored_five_point_similarity")
        self.assertAlmostEqual(result.metadata["roll_degrees_applied"], 21.0, places=6)
        np.testing.assert_allclose(
            result.crop_to_source @ result.source_to_crop,
            np.eye(3),
            atol=1e-9,
        )

    def test_extreme_five_point_roll_is_skipped_but_crop_is_kept(self):
        observation = make_observation(rotate_template(58.0))
        image = Image.new("RGB", (700, 600), color=(80, 120, 160))

        result = canonical_crop_v3(image, observation)

        self.assertAlmostEqual(result.metadata["roll_degrees_proposed"], 58.0, places=6)
        self.assertEqual(result.metadata["roll_degrees_applied"], 0.0)
        self.assertIn("roll_skipped_extreme_five_point_fit", result.metadata["warnings"])
        self.assertEqual(result.image.size, (512, 512))


if __name__ == "__main__":
    unittest.main()
