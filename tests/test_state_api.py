"""Exercise lifecycle behavior through the API with a controllable clock."""

import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.api import create_app


class StateAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "test.sqlite3"
        self.zones = Path(self.temp.name) / "zones.json"
        self.zones.write_text(json.dumps({
            "schema_version": 1, "camera_id": "test", "frame_size": {"width": 100, "height": 100},
            "coordinate_system": "original_frame_pixels",
            "tables": [{"id": "table_1", "polygon": [[0, 0], [99, 0], [99, 99], [0, 99]]}],
        }))
        self.now = 1000.0
        self.client = self.enterContext(TestClient(create_app(self.database, self.zones, lambda: self.now))) if hasattr(self, "enterContext") else None
        if self.client is None:  # Python 3.10 unittest lacks enterContext.
            self.client = TestClient(create_app(self.database, self.zones, lambda: self.now))
            self.client.__enter__()
            self.addCleanup(self.client.__exit__, None, None, None)
        self.frame = 0
        self.run = self.start()

    def start(self, mode="video", greeting_seconds=300):
        response = self.client.post("/api/runs", json={"mode": mode, "greeting_seconds": greeting_seconds})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["source"]["id"]

    def observe(self, second, ids=(1,), table="table_1"):
        self.now = 1000 + second
        self.frame += 1
        response = self.client.post(f"/api/runs/{self.run}/observations", json={
            "frame_number": self.frame, "media_seconds": second,
            "people": [{"track_id": identity, "table_id": table} for identity in ids],
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["tables"][0]

    def occupied(self):
        for second in (0, 1, 2):
            result = self.observe(second)
        self.assertEqual(result["state"], "occupied")
        return result

    def alerts(self):
        return self.client.get("/api/alerts").json()

    def test_arrival_debounce_and_brief_missing_detection(self):
        self.assertEqual(self.observe(0)["state"], "free")
        self.assertFalse(self.client.get("/api/tables").json()["tables"][0]["available"])
        self.assertEqual(self.observe(1, ())["state"], "free")
        self.assertEqual(self.observe(2)["state"], "free")
        self.assertEqual(self.observe(4)["state"], "occupied")
        self.assertEqual(self.observe(5, ())["state"], "occupied")
        self.assertEqual(self.observe(6)["state"], "occupied")
        self.assertEqual(self.observe(7, ())["state"], "occupied")
        self.assertEqual(self.observe(9, ())["state"], "occupied")
        self.assertEqual(self.observe(10, ())["state"], "needs_cleaning")
        self.observe(11, ())
        self.assertEqual([a["details"]["type"] for a in self.alerts()], ["needs_cleaning"])

    def test_five_minute_alert_exact_boundary_and_once_per_visit(self):
        self.occupied()
        for second in range(3, 302):
            self.observe(second)
        self.assertEqual(self.alerts(), [])
        self.observe(302)
        self.observe(303)
        self.assertEqual(len(self.alerts()), 1)
        self.assertEqual(self.alerts()[0]["details"]["type"], "ungreeted")

    def test_manual_greeting_suppresses_alert_and_logs_once(self):
        self.occupied()
        for _ in range(2):
            response = self.client.post("/api/tables/table_1/greet", json={"run_id": self.run})
            self.assertEqual(response.status_code, 200)
        for second in range(3, 304):
            self.observe(second)
        self.assertEqual(self.alerts(), [])
        events = self.client.get("/api/events").json()
        self.assertEqual(sum(e["kind"] == "staff_interaction" for e in events), 1)

    def test_cleaning_confirmation_and_new_visit_reset(self):
        self.occupied()
        self.assertEqual(self.client.post("/api/tables/table_1/clean", json={"run_id": self.run}).status_code, 409)
        self.observe(3, ())
        self.assertEqual(self.observe(6, ())["state"], "needs_cleaning")
        response = self.client.post("/api/tables/table_1/clean", json={"run_id": self.run})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tables"][0]["state"], "free")
        self.observe(7)
        table = self.observe(9)
        self.assertEqual(table["state"], "occupied")
        self.assertEqual(table["seated_seconds"], 0)
        self.assertIsNone(table["greeted_at"])
        changes = [e["details"]["to"] for e in self.client.get("/api/events").json() if e["kind"] == "state_changed"]
        self.assertEqual(changes, ["free", "occupied", "needs_cleaning", "free", "occupied"])

    def test_staff_label_excluded_from_customers_and_automatic_greeting(self):
        self.occupied()
        self.observe(3, (1, 2))
        self.assertEqual(self.client.post("/api/staff/2", json={"run_id": self.run}).status_code, 200)
        table = self.observe(4, (1, 2))
        self.assertEqual(table["customer_count"], 1)
        self.assertEqual(table["staff_count"], 1)
        self.assertIsNotNone(table["greeted_at"])
        self.observe(5, ())
        self.assertEqual(self.observe(8, ())["state"], "needs_cleaning")
        self.assertEqual(self.observe(9, (2,))["state"], "free")

    def test_unknown_person_cannot_clean_a_dirty_table(self):
        self.occupied()
        self.observe(3, ())
        self.observe(6, ())
        self.assertEqual(self.observe(7, (99,))["state"], "needs_cleaning")
        self.assertEqual(self.client.post("/api/tables/table_1/clean", json={"run_id": self.run}).status_code, 409)

    def test_gap_is_not_evidence_of_departure(self):
        self.occupied()
        self.observe(3, ())
        self.assertEqual(self.observe(20, ())["state"], "occupied")
        self.assertEqual(self.observe(23, ())["state"], "needs_cleaning")

    def test_video_clock_freezes_when_no_observations_and_at_eof(self):
        self.occupied()
        self.now += 600
        self.client.app.state.store.tick()
        result = self.client.get("/api/tables").json()
        self.assertFalse(result["source"]["fresh"])
        self.assertEqual(result["tables"][0]["seated_seconds"], 0)
        self.assertEqual(self.alerts(), [])
        self.client.post(f"/api/runs/{self.run}/stop", json={"reason": "completed"})
        self.assertEqual(self.client.get("/api/tables").json()["source"]["status"], "completed")

    def test_live_clock_tick_and_stale_source(self):
        self.client.post(f"/api/runs/{self.run}/stop", json={})
        self.run = self.start("live", greeting_seconds=3)
        self.occupied()
        self.now = 1005
        self.client.app.state.store.tick()
        self.assertEqual(len(self.alerts()), 1)
        self.now = 1100
        self.client.app.state.store.tick()
        result = self.client.get("/api/tables").json()
        self.assertFalse(result["source"]["fresh"])
        self.assertEqual(result["tables"][0]["state"], "occupied")
        self.assertEqual(result["tables"][0]["seated_seconds"], 3)

    def test_validation_duplicates_old_run_and_pagination(self):
        self.assertEqual(self.client.post("/api/runs", json={}).status_code, 409)
        self.observe(0)
        body = {"frame_number": self.frame, "media_seconds": 0, "people": []}
        self.assertEqual(self.client.post(f"/api/runs/{self.run}/observations", json=body).status_code, 409)
        body.update(frame_number=2, media_seconds="NaN")
        self.assertEqual(self.client.post(f"/api/runs/{self.run}/observations", json=body).status_code, 422)
        body.update(media_seconds=1, people=[{"track_id": 1, "table_id": "bad"}])
        self.assertEqual(self.client.post(f"/api/runs/{self.run}/observations", json=body).status_code, 422)
        self.assertEqual(self.client.post("/api/tables/missing/greet", json={"run_id": self.run}).status_code, 404)
        self.client.post(f"/api/runs/{self.run}/stop", json={})
        old = self.run
        self.run = self.start()
        self.assertNotEqual(old, self.run)
        body.update(people=[])
        self.assertEqual(self.client.post(f"/api/runs/{old}/observations", json=body).status_code, 409)
        self.assertEqual(self.client.get("/api/tables").json()["source"]["staff_ids"], [])
        first = self.client.get("/api/events?limit=1").json()[0]
        following = self.client.get(f"/api/events?after_id={first['id']}&limit=1").json()[0]
        self.assertGreater(following["id"], first["id"])

    def test_database_persists_and_restart_marks_source_interrupted(self):
        self.occupied()
        self.client.post("/api/tables/table_1/greet", json={"run_id": self.run})
        # Simulate restart with a second store on the same DB after saving state.
        with TestClient(create_app(self.database, self.zones, lambda: self.now)) as restarted:
            snapshot = restarted.get("/api/tables").json()
            self.assertEqual(snapshot["source"]["status"], "interrupted")
            self.assertEqual(snapshot["tables"][0]["state"], "occupied")
            self.assertIsNotNone(snapshot["tables"][0]["greeted_at"])
            self.assertGreater(len(restarted.get("/api/events").json()), 2)


if __name__ == "__main__":
    unittest.main()
