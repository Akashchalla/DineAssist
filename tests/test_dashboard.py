"""Dashboard behavior with fake API responses; no production records are changed."""

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from dashboard.client import APIClient, APIError
from dashboard.presentation import FOOTPRINT, action_permissions, duration, floor_layout, floor_scene, summary

ROOT = Path(__file__).resolve().parents[1]


def sample_snapshot():
    return {
        "source": {"id": "test-run", "status": "running", "mode": "video", "fresh": True,
                   "source_seconds": 12, "greeting_seconds": 5, "staff_ids": [],
                   "latest_people": [{"track_id": 1, "table_id": "table_1"}]},
        "mapping": {"frame_size": {"width": 200, "height": 100}, "tables": [
            {"id": "table_1", "polygon": [[10, 10], [90, 10], [90, 90], [10, 90]]},
            {"id": "table_2", "polygon": [[110, 10], [190, 10], [190, 90], [110, 90]]},
        ]},
        "tables": [
            {"id": "table_1", "state": "occupied", "observed": True, "available": False,
             "state_elapsed_seconds": 10, "seated_seconds": 10, "customer_count": 2,
             "staff_count": 0, "greeted_at": None, "greeting_alerted": True, "greeting_due_in_seconds": 0},
            {"id": "table_2", "state": "free", "observed": True, "available": True,
             "state_elapsed_seconds": 12, "seated_seconds": None, "customer_count": 0,
             "staff_count": 0, "greeted_at": None, "greeting_alerted": False},
        ],
    }


class DashboardLogicTests(unittest.TestCase):
    def test_stale_and_offline_never_count_as_available(self):
        data = sample_snapshot()
        self.assertEqual(summary(data)["available"], 1)
        self.assertIsNone(summary(data, connected=False)["available"])
        data["source"]["fresh"] = False
        self.assertIsNone(summary(data)["available"])
        self.assertFalse(action_permissions(data, data["tables"][0])["greet"])

    def test_finished_recording_can_be_corrected_but_is_not_live(self):
        data = sample_snapshot()
        data["source"].update(status="completed", fresh=False)
        self.assertTrue(action_permissions(data, data["tables"][0])["greet"])
        self.assertFalse(action_permissions(data, data["tables"][0])["label_staff"])
        self.assertIsNone(summary(data)["available"])

    def test_durations_and_floor_scene(self):
        self.assertEqual(duration(None), "—")
        self.assertEqual(duration(65), "01:05")
        self.assertEqual(duration(3661), "1:01:01")
        data = sample_snapshot()
        scene = floor_scene(data, "table_2")
        self.assertEqual([t["id"] for t in scene["tables"]], ["table_1", "table_2"])
        first, second = scene["tables"]
        self.assertTrue(second["selected"])
        self.assertFalse(first["selected"])
        self.assertLess(first["x"], second["x"])  # left/right order from the camera map is kept
        # Guests come from detections: two matched customers, no invented staff.
        self.assertEqual((first["customers"], first["staff"]), (2, 0))
        self.assertTrue(first["attention"])
        self.assertEqual(first["greeting"], "overdue")
        self.assertEqual(scene["status"], "live")
        focused = floor_scene(data, None, focus="Free")
        self.assertEqual([t["dim"] for t in focused["tables"]], [True, False])
        data["source"].update(status="completed", fresh=False)
        self.assertEqual(floor_scene(data)["status"], "finished")

    def test_floor_layout_has_no_overlaps(self):
        mapping = {"frame_size": {"width": 200, "height": 100}, "tables": [
            {"id": f"t{i}", "polygon": [[10 + i, 40], [30 + i, 40], [30 + i, 60], [10 + i, 60]]} for i in range(6)]}
        layout = floor_layout(mapping)
        ids = list(layout)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                (ax, ay, sa), (bx, by, sb) = layout[a], layout[b]
                (aw, ah), (bw, bh) = FOOTPRINT[sa], FOOTPRINT[sb]
                self.assertFalse(abs(ax - bx) < (aw + bw) / 2 and abs(ay - by) < (ah + bh) / 2, (a, b))

    def test_resolved_greeting_leaves_attention_queue(self):
        data = sample_snapshot()
        self.assertEqual(summary(data)["attention"], 1)
        data["tables"][0]["greeted_at"] = 12
        self.assertEqual(summary(data)["attention"], 0)

    @patch("dashboard.client.requests.request")
    def test_api_client_sends_expected_run_and_table(self, request):
        request.return_value.json.return_value = {"ok": True}
        client = APIClient("http://127.0.0.1:8000")
        client.confirm("run-1", "table_2", "clean")
        self.assertEqual(request.call_args.args, ("POST", "http://127.0.0.1:8000/api/tables/table_2/clean"))
        self.assertEqual(request.call_args.kwargs["json"], {"run_id": "run-1"})


class DashboardUITests(unittest.TestCase):
    def setUp(self):
        self.data = sample_snapshot()
        self.events = [{"id": 1, "kind": "alert", "run_id": "test-run", "table_id": "table_1",
                        "recorded_at": "2026-10-24T18:00:00+00:00", "source_seconds": 7,
                        "details": {"type": "ungreeted", "message": "Greeting overdue"}}]
        self.snapshot_patch = patch.object(APIClient, "snapshot", side_effect=lambda: deepcopy(self.data))
        self.snapshot_mock = self.snapshot_patch.start()
        self.addCleanup(self.snapshot_patch.stop)
        self.events_patch = patch.object(APIClient, "events", side_effect=lambda run, after: [e for e in self.events if e["id"] > after])
        self.events_patch.start()
        self.addCleanup(self.events_patch.stop)
        self.action_patch = patch.object(APIClient, "confirm", side_effect=self.confirm)
        self.action_mock = self.action_patch.start()
        self.addCleanup(self.action_patch.stop)
        self.staff_patch = patch.object(APIClient, "staff", return_value={})
        self.staff_mock = self.staff_patch.start()
        self.addCleanup(self.staff_patch.stop)
        self.waitlist = {"topic": "tableflow-test", "server": "https://ntfy.sh", "entries": []}
        for name, kwargs in {"waitlist": {"side_effect": lambda: deepcopy(self.waitlist)},
                             "add_party": {"return_value": {}}, "notify_party": {"return_value": {}},
                             "close_party": {"return_value": {}}}.items():
            patcher = patch.object(APIClient, name, **kwargs)
            setattr(self, f"{name}_mock", patcher.start())
            self.addCleanup(patcher.stop)
        self.app = AppTest.from_file(str(ROOT / "dashboard/app.py"), default_timeout=20)

    def confirm(self, run_id, table_id, action):
        table = next(t for t in self.data["tables"] if t["id"] == table_id)
        if action == "greet":
            table["greeted_at"] = 12
        else:
            table.update(state="free", available=True)
        return deepcopy(self.data)

    def run_app(self):
        self.app.run()
        self.assertEqual(len(self.app.exception), 0, str(self.app.exception))

    def test_render_and_greeting_button_updates_server_and_queue(self):
        self.run_app()
        self.assertEqual(self.app.metric[0].value, "1")
        self.assertFalse(self.app.button(key="greet").disabled)
        self.app.button(key="greet").click().run()
        self.assertFalse(self.app.exception)
        self.action_mock.assert_called_once_with("test-run", "table_1", "greet")
        self.assertTrue(self.app.button(key="greet").disabled)
        self.assertEqual(self.app.metric[3].value, "0")

    def test_cleaning_action_and_selection(self):
        self.data["tables"][1].update(state="needs_cleaning", available=False)
        self.run_app()
        self.app.selectbox(key="selected_table").select("table_2").run()
        self.assertFalse(self.app.button(key="clean").disabled)
        self.app.button(key="clean").click().run()
        self.assertFalse(self.app.exception)
        self.action_mock.assert_called_once_with("test-run", "table_2", "clean")
        self.assertTrue(self.app.button(key="clean").disabled)

    def test_offline_caches_map_but_disables_actions(self):
        self.run_app()
        self.snapshot_mock.side_effect = APIError("Cannot reach the restaurant service.")
        self.run_app()
        self.assertTrue(self.app.error)
        self.assertEqual(self.app.metric[0].value, "—")
        self.assertTrue(self.app.button(key="greet").disabled)

    def test_offline_initial_load_and_waiting_for_first_run(self):
        self.snapshot_mock.side_effect = APIError("Cannot reach the restaurant service.")
        self.run_app()
        self.assertTrue(self.app.button(key="refresh_empty"))
        self.data.update(source=None, tables=[])
        self.snapshot_mock.side_effect = lambda: deepcopy(self.data)
        self.run_app()
        self.assertEqual(self.app.metric[0].value, "—")

    def test_staff_label_and_activity_filter(self):
        self.run_app()
        self.app.button(key="staff_add").click().run()
        self.staff_mock.assert_called_once_with("test-run", 1, True)
        self.app.selectbox(key="event_category").select("Alerts").run()
        self.assertFalse(self.app.exception)
        self.assertEqual(len(self.app.dataframe[-1].value), 1)

    def test_action_conflict_is_shown_without_false_success(self):
        self.run_app()
        self.action_mock.side_effect = APIError("This run is no longer active.")
        self.app.button(key="greet").click().run()
        self.assertTrue(any("no longer active" in e.value for e in self.app.error))
        self.assertFalse(self.app.button(key="greet").disabled)


class WaitlistUITests(unittest.TestCase):
    setUp = DashboardUITests.setUp
    confirm = DashboardUITests.confirm
    run_app = DashboardUITests.run_app

    def test_text_guest_for_free_table(self):
        self.waitlist["entries"] = [{"id": 7, "name": "Akash", "party_size": 2, "status": "waiting",
                                     "added_at": "2026-10-24T18:00:00+00:00", "table_id": None, "notified_at": None}]
        self.run_app()
        self.assertTrue(any("Table 2 is ready." in m.value for m in self.app.markdown))
        self.assertEqual(self.app.selectbox(key="wl_table_7").value, "table_2")  # the only free table
        self.app.button(key="wl_notify_7").click().run()
        self.assertFalse(self.app.exception)
        self.notify_party_mock.assert_called_once_with(7, "table_2")

    def test_add_party_and_seat_texted_party(self):
        self.run_app()
        self.app.text_input(key="wl_name").input("Maya")
        self.app.number_input(key="wl_size").set_value(4)
        self.app.button[[b.label for b in self.app.button].index("Add to waitlist")].click().run()
        self.add_party_mock.assert_called_once_with("Maya", 4)
        self.waitlist["entries"] = [{"id": 8, "name": "Maya", "party_size": 4, "status": "notified",
                                     "added_at": "2026-10-24T18:00:00+00:00", "table_id": "table_2",
                                     "notified_at": "2026-10-24T18:05:00+00:00"}]
        self.run_app()
        self.app.button(key="wl_seat_8").click().run()
        self.close_party_mock.assert_called_once_with(8, "seated")


if __name__ == "__main__":
    unittest.main()
