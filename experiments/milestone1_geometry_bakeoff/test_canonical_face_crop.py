import math
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image


sys.path.insert(0, str(Path(__file__).resolve().parent))

from canonical_face_crop import FaceObservation, canonical_crop, transform_points


class CanonicalFaceCropTests(unittest.TestCase):
    def test_levels_eyes_and_keeps_transform_reversible(self):
        image = Image.new("RGB", (800, 600), color=(64, 96, 128))
        center = np.array([400.0, 300.0])
        angle = math.radians(32.0)
        eye_vector = np.array([math.cos(angle), math.sin(angle)]) * 140.0
        left_eye = center - eye_vector / 2.0
        right_eye = center + eye_vector / 2.0
        observation = FaceObservation(
            bbox_xyxy=(285.0, 170.0, 515.0, 430.0),
            left_eye_xy=tuple(left_eye),
            right_eye_xy=tuple(right_eye),
            score=0.98,
        )

        result = canonical_crop(image, observation, output_size=512, bbox_margin=1.42)
        transformed_eyes = transform_points(
            result.source_to_crop,
            [left_eye, right_eye],
        )

        self.assertEqual(result.image.size, (512, 512))
        self.assertAlmostEqual(transformed_eyes[0, 1], transformed_eyes[1, 1], places=7)
        self.assertLess(transformed_eyes[0, 0], transformed_eyes[1, 0])
        np.testing.assert_allclose(
            result.crop_to_source @ result.source_to_crop,
            np.eye(3),
            atol=1e-9,
        )
        self.assertAlmostEqual(result.metadata["roll_degrees_removed"], 32.0, places=6)

    def test_normalizes_face_scale_from_bbox(self):
        image = Image.new("RGB", (1200, 800), color=(255, 255, 255))
        small = FaceObservation(
            bbox_xyxy=(100.0, 100.0, 300.0, 300.0),
            left_eye_xy=(150.0, 170.0),
            right_eye_xy=(250.0, 170.0),
            score=0.9,
        )
        large = FaceObservation(
            bbox_xyxy=(400.0, 100.0, 800.0, 500.0),
            left_eye_xy=(500.0, 240.0),
            right_eye_xy=(700.0, 240.0),
            score=0.9,
        )

        small_result = canonical_crop(image, small, bbox_margin=1.42)
        large_result = canonical_crop(image, large, bbox_margin=1.42)

        self.assertAlmostEqual(
            small_result.metadata["face_occupancy_target"],
            large_result.metadata["face_occupancy_target"],
        )
        self.assertAlmostEqual(
            small_result.metadata["face_occupancy_target"],
            1 / 1.42,
        )

    def test_rejects_invalid_bbox(self):
        image = Image.new("RGB", (512, 512))
        observation = FaceObservation(
            bbox_xyxy=(300.0, 100.0, 200.0, 400.0),
            left_eye_xy=(210.0, 200.0),
            right_eye_xy=(290.0, 200.0),
            score=0.9,
        )

        with self.assertRaisesRegex(ValueError, "invalid face bbox"):
            canonical_crop(image, observation)


if __name__ == "__main__":
    unittest.main()
