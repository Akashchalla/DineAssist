"""Check geometry independently of YOLO's changing predictions."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from detect_people import TableZones


class TableZoneTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "zones.json"
        self.document = {
            "schema_version": 1, "coordinate_system": "original_frame_pixels",
            "frame_size": {"width": 200, "height": 100},
            "tables": [
                {"id": "left", "polygon": [[10, 10], [90, 10], [90, 90], [10, 90]]},
                {"id": "right", "polygon": [[110, 10], [190, 10], [190, 90], [110, 90]]},
            ],
        }

    def zones(self, shape=(100, 200, 3)):
        self.path.write_text(json.dumps(self.document))
        return TableZones(self.path, shape)

    def test_person_inside_and_person_outside(self):
        zones = self.zones()
        self.assertEqual(zones.match([20, 20, 40, 70], .15), ("left", 1.0))
        self.assertEqual(zones.match([95, 20, 105, 70], .15), (None, 0.0))

    def test_tiny_overlap_does_not_count(self):
        self.assertIsNone(self.zones().match([89, 20, 120, 70], .8)[0])

    def test_person_spanning_tables_assigned_to_stronger_only(self):
        self.assertEqual(self.zones().match([80, 20, 150, 70], .15)[0], "right")

    def test_concave_polygon_uses_outline_not_enclosing_rectangle(self):
        self.document["tables"] = [{"id": "L", "polygon": [
            [10, 10], [90, 10], [90, 40], [40, 40], [40, 90], [10, 90],
        ]}]
        zones = self.zones()
        self.assertEqual(zones.match([50, 50, 80, 80], .15), (None, 0.0))
        self.assertEqual(zones.match([15, 50, 30, 80], .15), ("L", 1.0))

    def test_clipped_and_invalid_boxes(self):
        zones = self.zones()
        self.assertEqual(zones.match([-10, 20, 40, 70], .15)[0], "left")
        for box in ([300, 20, 320, 70], [20, 20, 20, 50], [50, 50, 10, 10], [float("nan"), 0, 20, 20]):
            self.assertEqual(zones.match(box, .15), (None, 0.0))

    def test_rejects_video_resolution_mismatch(self):
        with self.assertRaisesRegex(ValueError, "size differs"):
            self.zones((200, 400, 3))

    def test_rejects_duplicate_ids_and_outside_corners(self):
        self.document["tables"][1]["id"] = "left"
        with self.assertRaisesRegex(ValueError, "unique"):
            self.zones()
        self.document["tables"] = [{"id": "bad", "polygon": [[-10, 10], [90, 10], [90, 90], [-10, 90]]}]
        with self.assertRaisesRegex(ValueError, "outside"):
            self.zones()


if __name__ == "__main__":
    unittest.main()
