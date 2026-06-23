import math
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image


sys.path.insert(0, str(Path(__file__).resolve().parent))

from canonical_face_crop_v2 import (
    FaceObservationV2,
    analyze_landmark_geometry,
    canonical_crop_v2,
    select_primary_face,
    transform_points,
)


def rotate_points(points, center, degrees):
    angle = math.radians(degrees)
    matrix = np.asarray(
        [[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]],
        dtype=np.float64,
    )
    center_array = np.asarray(center, dtype=np.float64)
    return [tuple((matrix @ (np.asarray(point) - center_array) + center_array).tolist()) for point in points]


class CanonicalFaceCropV2Tests(unittest.TestCase):
    def test_reliable_frontal_landmarks_apply_roll_and_keep_transform_reversible(self):
        image = Image.new("RGB", (800, 600), color=(64, 96, 128))
        points = rotate_points(
            [(330, 250), (470, 250), (400, 310), (360, 360), (440, 360)],
            center=(400, 300),
            degrees=24.0,
        )
        observation = FaceObservationV2(
            bbox_xyxy=(270.0, 150.0, 530.0, 450.0),
            landmarks5_xy=tuple(points),
            score=0.98,
        )

        result = canonical_crop_v2(image, observation)
        transformed = transform_points(result.source_to_crop, points[:2])

        self.assertTrue(result.metadata["landmark_geometry"]["roll_reliable"])
        self.assertAlmostEqual(result.metadata["roll_degrees_applied"], 24.0, places=6)
        self.assertAlmostEqual(transformed[0, 1], transformed[1, 1], places=7)
        np.testing.assert_allclose(
            result.crop_to_source @ result.source_to_crop,
            np.eye(3),
            atol=1e-9,
        )

    def test_profile_like_fake_eye_skips_roll_without_rejecting_crop(self):
        image = Image.new("RGB", (500, 500), color=(120, 100, 80))
        observation = FaceObservationV2(
            bbox_xyxy=(120.0, 100.0, 340.0, 390.0),
            landmarks5_xy=(
                (155.0, 195.0),
                (245.0, 215.0),
                (250.0, 240.0),
                (210.0, 310.0),
                (260.0, 315.0),
            ),
            score=0.92,
        )

        geometry = analyze_landmark_geometry(observation)
        result = canonical_crop_v2(image, observation)

        self.assertFalse(geometry["roll_reliable"])
        self.assertLess(geometry["eye_nose_balance"], 0.35)
        self.assertEqual(result.metadata["roll_degrees_applied"], 0.0)
        self.assertIn("roll_skipped_unreliable_landmarks", result.metadata["warnings"])
        self.assertIn("profile_candidate", result.metadata["warnings"])
        self.assertEqual(result.image.size, (512, 512))

    def test_largest_face_beats_tiny_high_confidence_background_face(self):
        primary = FaceObservationV2(
            bbox_xyxy=(500.0, 250.0, 900.0, 700.0),
            landmarks5_xy=(
                (610.0, 410.0),
                (790.0, 410.0),
                (700.0, 500.0),
                (650.0, 590.0),
                (750.0, 590.0),
            ),
            score=0.91,
        )
        background = FaceObservationV2(
            bbox_xyxy=(70.0, 50.0, 150.0, 140.0),
            landmarks5_xy=(
                (90.0, 82.0),
                (125.0, 82.0),
                (108.0, 100.0),
                (98.0, 120.0),
                (118.0, 120.0),
            ),
            score=0.999,
        )

        selection = select_primary_face([background, primary], image_size=(1000, 800))

        self.assertEqual(selection.selected_index, 1)
        self.assertEqual(len(selection.candidate_rankings), 2)

    def test_reflection_removes_artificial_black_and_records_validity(self):
        image = Image.new("RGB", (180, 180), color=(30, 80, 140))
        observation = FaceObservationV2(
            bbox_xyxy=(5.0, 5.0, 125.0, 155.0),
            landmarks5_xy=(
                (30.0, 45.0),
                (95.0, 65.0),
                (62.0, 90.0),
                (45.0, 120.0),
                (85.0, 132.0),
            ),
            score=0.95,
        )

        result = canonical_crop_v2(image, observation, bbox_margin=1.60)
        pixels = np.asarray(result.image)
        validity = np.asarray(result.observed_source_mask)

        self.assertGreater(pixels.min(), 0)
        self.assertTrue(np.any(validity == 0))
        self.assertLess(result.metadata["observed_source_fraction"], 1.0)
        self.assertIn("reflected_padding_used", result.metadata["warnings"])

    def test_rejects_invalid_landmark_count(self):
        observation = FaceObservationV2(
            bbox_xyxy=(10.0, 10.0, 100.0, 120.0),
            landmarks5_xy=((20.0, 30.0), (60.0, 30.0)),
            score=0.9,
        )

        with self.assertRaisesRegex(ValueError, "five points"):
            canonical_crop_v2(Image.new("RGB", (200, 200)), observation)


if __name__ == "__main__":
    unittest.main()
