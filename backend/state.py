"""Persistent table lifecycle. No camera or machine-learning code lives here."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import RLock
import time
from uuid import uuid4


class Conflict(ValueError):
    """An action is valid in general, but not in the current state."""


def utc(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


class TableStore:
    def __init__(self, database, zone_file, clock=time.time):
        self.clock = clock
        self.lock = RLock()
        self.mapping = json.loads(Path(zone_file).read_text())
        self.ids = [t["id"] for t in self.mapping["tables"]]
        if not self.ids or len(self.ids) != len(set(self.ids)):
            raise ValueError("The map needs at least one table and unique table IDs.")
        Path(database).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(database), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, started_at REAL NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(id),
                table_id TEXT, kind TEXT NOT NULL, recorded_at TEXT NOT NULL,
                source_seconds REAL NOT NULL, details TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_run ON events(run_id, id);
        """)
        # An API restart must not pretend the old detector is still connected.
        with self.lock, self.db:
            for row in self.db.execute("SELECT payload FROM runs").fetchall():
                run = json.loads(row["payload"])
                if run["status"] == "running":
                    run["status"] = "interrupted"
                    self._event(run, None, "source_stopped", {"reason": "API restarted"})
                    self._save(run)

    def close(self):
        with self.lock:
            self.db.close()

    def _load(self, run_id=None):
        if run_id:
            row = self.db.execute("SELECT payload FROM runs WHERE id=?", (run_id,)).fetchone()
        else:
            row = self.db.execute("SELECT payload FROM runs ORDER BY started_at DESC, rowid DESC LIMIT 1").fetchone()
        if row is None:
            if run_id:
                raise KeyError("Run not found")
            return None
        return json.loads(row["payload"])

    def _save(self, run):
        self.db.execute("UPDATE runs SET payload=? WHERE id=?", (json.dumps(run), run["id"]))

    def _event(self, run, table_id, kind, details):
        timestamp = utc(self.clock())
        self.db.execute(
            "INSERT INTO events(run_id,table_id,kind,recorded_at,source_seconds,details) VALUES(?,?,?,?,?,?)",
            (run["id"], table_id, kind, timestamp, run["source_seconds"], json.dumps(details)),
        )
        if kind == "alert":
            print(f"ALERT {timestamp} [{table_id}] {details['message']}", flush=True)

    def start(self, mode="video", greeting_seconds=300):
        with self.lock, self.db:
            current = self._load()
            if current and current["status"] == "running":
                raise Conflict("A detector run is already active. Stop it before starting another.")
            now = self.clock()
            run = {
                "id": str(uuid4()), "mode": mode, "status": "running", "started_at": now,
                "source_seconds": 0.0, "last_received_at": None, "last_frame": -1,
                "greeting_seconds": greeting_seconds, "arrival_seconds": 2.0,
                "departure_seconds": 3.0, "stale_seconds": 5.0, "staff_ids": [],
                "latest_people": [], "tables": {}, "mapping": self.mapping,
            }
            for name in self.ids:
                run["tables"][name] = {
                    "state": "free", "state_since": 0.0, "seated_at": None,
                    "greeted_at": None, "last_staff_at": None, "greeting_alerted": False,
                    "customer_count": 0, "staff_count": 0, "present_since": None,
                    "absent_since": None, "observed": False,
                }
            self.db.execute("INSERT INTO runs VALUES(?,?,?)", (run["id"], now, json.dumps(run)))
            self._event(run, None, "source_started", {"mode": mode, "greeting_seconds": greeting_seconds})
            for name in self.ids:
                self._event(run, name, "state_changed", {
                    "from": None, "to": "free", "reason": "initial assumption; not yet observed",
                })
            return self._snapshot(run)

    def _active(self, run_id):
        run = self._load(run_id)
        latest = self._load()
        if run["status"] != "running" or latest["id"] != run_id:
            raise Conflict("This run is no longer active. Use the current run ID.")
        return run

    def _change(self, run, name, state, reason):
        table = run["tables"][name]
        previous = table["state"]
        if previous == state:
            return
        details = {"from": previous, "to": state, "reason": reason}
        if previous == "occupied":
            details["seated_duration_seconds"] = run["source_seconds"] - table["seated_at"]
        table["state"] = state
        table["state_since"] = run["source_seconds"]
        table["present_since"] = table["absent_since"] = None
        if state == "occupied":
            table["seated_at"] = run["source_seconds"]
            table["greeted_at"] = None
            table["greeting_alerted"] = False
        else:
            table["seated_at"] = None
            table["greeted_at"] = None
        self._event(run, name, "state_changed", details)
        if state == "needs_cleaning":
            self._event(run, name, "alert", {"type": "needs_cleaning", "message": "Table became empty; please clean it."})

    def _greet(self, run, name, reason):
        table = run["tables"][name]
        if table["greeted_at"] is None:
            table["greeted_at"] = run["source_seconds"]
            table["last_staff_at"] = run["source_seconds"]
            self._event(run, name, "staff_interaction", {"action": "greeted", "reason": reason})

    def _alerts(self, run):
        for name, table in run["tables"].items():
            if (table["state"] == "occupied" and table["greeted_at"] is None
                    and not table["greeting_alerted"]
                    and run["source_seconds"] - table["seated_at"] >= run["greeting_seconds"]):
                table["greeting_alerted"] = True
                self._event(run, name, "alert", {"type": "ungreeted", "message": "Seated too long without a recorded staff greeting."})

    def observe(self, run_id, frame_number, media_seconds, people):
        with self.lock, self.db:
            run = self._active(run_id)
            if frame_number <= run["last_frame"]:
                raise Conflict("Observation frame numbers must increase; duplicates and old frames are rejected.")
            now = self.clock()
            source_time = media_seconds if run["mode"] == "video" else max(0.0, now - run["started_at"])
            if source_time is None:
                raise ValueError("Video observations require media_seconds.")
            if source_time < run["source_seconds"]:
                raise Conflict("The source clock cannot move backward. Start a new run to replay a video.")
            if any(p["table_id"] is not None and p["table_id"] not in run["tables"] for p in people):
                raise ValueError("Observation refers to a table that is not in this run's map.")
            tracked = [p["track_id"] for p in people if p["track_id"] is not None]
            if len(tracked) != len(set(tracked)):
                raise ValueError("A tracking ID can appear only once in an observation.")
            gap = source_time - run["source_seconds"]
            disconnected = run["last_received_at"] is not None and now - run["last_received_at"] > run["stale_seconds"]
            run.update(source_seconds=source_time, last_received_at=now, last_frame=frame_number, latest_people=people)
            counts = {name: [0, 0] for name in run["tables"]}
            for person in people:
                if person["table_id"] is not None:
                    is_staff = person["track_id"] is not None and person["track_id"] in run["staff_ids"]
                    counts[person["table_id"]][int(is_staff)] += 1
            for name, table in run["tables"].items():
                customers, staff = counts[name]
                previous_staff = table["staff_count"]
                if gap > run["stale_seconds"] or disconnected:
                    table["present_since"] = table["absent_since"] = None
                    previous_staff = staff  # A reconnect is not proof of a new staff entry.
                table.update(customer_count=customers, staff_count=staff, observed=True)
                if customers:
                    table["absent_since"] = None
                    if table["state"] != "occupied":
                        if table["present_since"] is None:
                            table["present_since"] = source_time
                        if source_time - table["present_since"] >= run["arrival_seconds"]:
                            self._change(run, name, "occupied", "sustained person presence")
                else:
                    table["present_since"] = None
                    if table["state"] == "occupied":
                        if table["absent_since"] is None:
                            table["absent_since"] = source_time
                        if source_time - table["absent_since"] >= run["departure_seconds"]:
                            self._change(run, name, "needs_cleaning", "sustained customer absence")
                if staff:
                    table["last_staff_at"] = source_time
                    if table["state"] == "occupied":
                        self._greet(run, name, "recognized staff track in zone")
                    elif table["state"] == "needs_cleaning" and not customers and not previous_staff:
                        self._change(run, name, "free", "recognized staff entered empty dirty zone; cleaning proxy")
            self._alerts(run)
            self._save(run)
            return self._snapshot(run)

    def tick(self):
        """Only live camera clocks advance between observations; videos use media time."""
        with self.lock, self.db:
            run = self._load()
            if run and run["mode"] == "live" and self._fresh(run):
                run["source_seconds"] = max(run["source_seconds"], self.clock() - run["started_at"])
                self._alerts(run)
                self._save(run)

    def _fresh(self, run):
        return (run["status"] == "running" and run["last_received_at"] is not None
                and self.clock() - run["last_received_at"] <= run["stale_seconds"])

    def stop(self, run_id, reason="completed"):
        with self.lock, self.db:
            run = self._load(run_id)
            if run["status"] == "running":
                run["status"] = reason
                self._event(run, None, "source_stopped", {"reason": reason})
                self._save(run)
            return self._snapshot(run)

    def mark_staff(self, run_id, track_id, enabled=True):
        with self.lock, self.db:
            run = self._active(run_id)
            if enabled and (not self._fresh(run) or track_id not in [p["track_id"] for p in run["latest_people"]]):
                raise Conflict("Choose a tracking ID visible in the current, fresh observations.")
            ids = set(run["staff_ids"])
            ids.add(track_id) if enabled else ids.discard(track_id)
            run["staff_ids"] = sorted(ids)
            self._event(run, None, "staff_label", {"track_id": track_id, "enabled": enabled})
            self._save(run)
            return self._snapshot(run)

    def staff_action(self, run_id, table_id, action):
        with self.lock, self.db:
            run = self._load(run_id)
            if self._load()["id"] != run_id:
                raise Conflict("Use the current run ID.")
            if table_id not in run["tables"]:
                raise KeyError("Table not found")
            table = run["tables"][table_id]
            if action == "greet":
                if table["state"] != "occupied":
                    raise Conflict("Only an occupied table can be marked greeted.")
                self._greet(run, table_id, "manual staff confirmation")
            elif action == "clean":
                if table["state"] != "needs_cleaning" or table["customer_count"]:
                    raise Conflict("Cleaning requires a needs-cleaning table with no observed customers.")
                table["last_staff_at"] = run["source_seconds"]
                self._event(run, table_id, "staff_interaction", {"action": "cleaned", "reason": "manual staff confirmation"})
                self._change(run, table_id, "free", "manual cleaning confirmation")
            else:
                raise ValueError("Unknown staff action")
            self._save(run)
            return self._snapshot(run)

    def _snapshot(self, run):
        if run is None:
            return {"source": None, "mapping": self.mapping, "tables": []}
        fresh = self._fresh(run)
        tables = []
        for name, table in run["tables"].items():
            elapsed = max(0, run["source_seconds"] - table["state_since"])
            seated = None if table["seated_at"] is None else max(0, run["source_seconds"] - table["seated_at"])
            tables.append({"id": name, **table, "color": {
                "free": "green", "occupied": "red", "needs_cleaning": "yellow",
            }[table["state"]], "state_elapsed_seconds": round(elapsed, 2),
                "seated_seconds": None if seated is None else round(seated, 2),
                "greeting_due_in_seconds": (max(0, round(run["greeting_seconds"] - seated, 2))
                                            if seated is not None and table["greeted_at"] is None else None),
                "available": fresh and table["observed"] and table["state"] == "free"
                             and table["customer_count"] == 0 and table["present_since"] is None})
        return {
            "source": {key: run[key] for key in (
                "id", "mode", "status", "source_seconds", "last_frame", "greeting_seconds",
                "arrival_seconds", "departure_seconds", "staff_ids", "latest_people",
            )} | {"fresh": fresh, "last_received_at": utc(run["last_received_at"]) if run["last_received_at"] is not None else None},
            "mapping": run["mapping"], "tables": tables,
        }

    def snapshot(self):
        with self.lock:
            return self._snapshot(self._load())

    def events(self, after_id=0, limit=100, run_id=None, alerts_only=False):
        with self.lock:
            query = "SELECT * FROM events WHERE id>?"
            params = [after_id]
            if run_id:
                query += " AND run_id=?"
                params.append(run_id)
            if alerts_only:
                query += " AND kind='alert'"
            rows = self.db.execute(query + " ORDER BY id LIMIT ?", params + [limit]).fetchall()
            return [{**dict(row), "details": json.loads(row["details"])} for row in rows]
