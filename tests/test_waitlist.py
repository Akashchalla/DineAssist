"""Waitlist and "table ready" messages, with a fake sender (nothing leaves the computer)."""

import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.waitlist import NotifyError


class WaitlistTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "test.sqlite3"
        self.zones = Path(self.temp.name) / "zones.json"
        self.zones.write_text(json.dumps({
            "schema_version": 1, "camera_id": "test", "frame_size": {"width": 100, "height": 100},
            "coordinate_system": "original_frame_pixels",
            "tables": [{"id": "table_1", "polygon": [[0, 0], [49, 0], [49, 99], [0, 99]]},
                       {"id": "table_3", "polygon": [[50, 0], [99, 0], [99, 99], [50, 99]]}],
        }))
        self.sent, self.fail = [], False
        self.client = self.open_client()
        self.now = 1000.0

    def open_client(self):
        def sender(server, topic, title, message):
            if self.fail:
                raise NotifyError("network down")
            self.sent.append((server, topic, title, message))
        client = TestClient(create_app(self.database, self.zones, lambda: self.now, sender=sender))
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def add(self, name="Akash", size=2, **extra):
        response = self.client.post("/api/waitlist", json={"name": name, "party_size": size, **extra})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def test_text_guest_for_free_table_and_hold_it(self):
        entry = self.add()
        response = self.client.post(f"/api/waitlist/{entry}/notify", json={"table_id": "table_3"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "notified")
        server, topic, title, message = self.sent[0]
        self.assertEqual(title, "Table 3 is ready")
        self.assertIn("Hi Akash, table 3 is ready for your party of 2", message)
        self.assertTrue(topic.startswith("tableflow-"))
        # The table is now held: a second party can't be texted for it.
        other = self.add("Maya", 4)
        clash = self.client.post(f"/api/waitlist/{other}/notify", json={"table_id": "table_3"})
        self.assertEqual(clash.status_code, 409)
        self.assertIn("held for Akash", clash.json()["detail"])
        self.assertEqual(self.client.post(f"/api/waitlist/{entry}/close", json={"status": "seated"}).status_code, 200)
        self.assertEqual([e["name"] for e in self.client.get("/api/waitlist").json()["entries"]], ["Maya"])

    def test_occupied_table_is_refused_and_failure_keeps_party_waiting(self):
        run = self.client.post("/api/runs", json={}).json()["source"]["id"]
        for frame, second in enumerate((0, 1, 2), start=1):
            self.client.post(f"/api/runs/{run}/observations", json={
                "frame_number": frame, "media_seconds": second, "people": [{"track_id": 1, "table_id": "table_1"}]})
        entry = self.add()
        busy = self.client.post(f"/api/waitlist/{entry}/notify", json={"table_id": "table_1"})
        self.assertEqual(busy.status_code, 409)
        self.assertIn("isn't free", busy.json()["detail"])
        self.fail = True
        failed = self.client.post(f"/api/waitlist/{entry}/notify", json={"table_id": "table_3"})
        self.assertEqual(failed.status_code, 502)
        self.assertEqual(self.client.get("/api/waitlist").json()["entries"][0]["status"], "waiting")
        self.fail = False
        self.assertEqual(self.client.post(f"/api/waitlist/{entry}/notify", json={"table_id": "table_3"}).status_code, 200)
        kinds = [e["kind"] for e in self.client.get(f"/api/events?run_id={run}").json()]
        self.assertIn("guest_notified", kinds)

    def test_validation_personal_topic_and_stable_restaurant_topic(self):
        self.assertEqual(self.client.post("/api/waitlist", json={"name": "", "party_size": 2}).status_code, 422)
        self.assertEqual(self.client.post("/api/waitlist", json={"name": "A", "party_size": 0}).status_code, 422)
        self.assertEqual(self.client.post("/api/waitlist", json={"name": "A", "party_size": 2, "topic": "bad topic!"}).status_code, 422)
        entry = self.add("Sam", 1, topic="sams-phone")
        self.client.post(f"/api/waitlist/{entry}/notify", json={"table_id": "table_1"})
        self.assertEqual(self.sent[-1][1], "sams-phone")
        self.assertEqual(self.client.post("/api/waitlist/999/notify", json={"table_id": "table_1"}).status_code, 404)
        self.assertEqual(self.client.post(f"/api/waitlist/{entry}/notify", json={"table_id": "table_9"}).status_code, 404)
        topic = self.client.get("/api/waitlist").json()["topic"]
        self.assertEqual(self.open_client().get("/api/waitlist").json()["topic"], topic)


if __name__ == "__main__":
    unittest.main()
