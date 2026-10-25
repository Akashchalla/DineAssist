"""Waitlist and "your table is ready" messages, sent as ntfy push notifications.

ntfy (https://ntfy.sh) delivers a message to every phone subscribed to a topic in
the free ntfy app. Anyone who knows a topic name on the public server can read
it, so the default topic is a random, hard-to-guess name.
"""

from datetime import datetime, timezone
import secrets

import requests

from backend.state import Conflict


class NotifyError(RuntimeError):
    """The push message could not be delivered to the ntfy server."""


def send_ntfy(server, topic, title, message, timeout=6):
    try:
        response = requests.post(f"{server.rstrip('/')}/{topic}", data=message.encode("utf-8"), timeout=timeout,
                                 headers={"Title": title, "Tags": "fork_and_knife", "Priority": "high"})
        response.raise_for_status()
    except requests.RequestException as error:
        raise NotifyError("The message could not be sent. Check this computer's internet connection "
                          "and the ntfy topic, then try again.") from error


def _now():
    return datetime.now(timezone.utc).isoformat()


def _table_number(table_id):
    return table_id[6:] if table_id.startswith("table_") else table_id


class Waitlist:
    def __init__(self, store, server="https://ntfy.sh", topic=None, sender=send_ntfy):
        self.store, self.server, self.sender = store, server, sender
        with store.lock, store.db:
            store.db.executescript("""
                CREATE TABLE IF NOT EXISTS waitlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, party_size INTEGER NOT NULL,
                    topic TEXT, status TEXT NOT NULL, added_at TEXT NOT NULL,
                    notified_at TEXT, table_id TEXT, closed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            if not topic:
                row = store.db.execute("SELECT value FROM settings WHERE key='ntfy_topic'").fetchone()
                topic = row[0] if row else f"tableflow-{secrets.token_hex(5)}"
                store.db.execute("INSERT OR IGNORE INTO settings VALUES ('ntfy_topic', ?)", (topic,))
        self.topic = topic

    def _row(self, entry_id):
        row = self.store.db.execute("SELECT * FROM waitlist WHERE id=?", (entry_id,)).fetchone()
        if row is None:
            raise KeyError("Waitlist entry not found")
        return dict(row)

    def listing(self):
        with self.store.lock:
            rows = self.store.db.execute(
                "SELECT * FROM waitlist WHERE status IN ('waiting', 'notified') ORDER BY id").fetchall()
            return {"topic": self.topic, "server": self.server, "entries": [dict(r) for r in rows]}

    def add(self, name, party_size, topic=None):
        name = " ".join(name.split())
        if not name:
            raise ValueError("Enter the guest's name.")
        with self.store.lock, self.store.db:
            cursor = self.store.db.execute(
                "INSERT INTO waitlist(name, party_size, topic, status, added_at) VALUES (?,?,?,?,?)",
                (name, party_size, topic or None, "waiting", _now()))
            return self._row(cursor.lastrowid)

    def holds(self):
        """{table_id: entry} for tables held for a texted party."""
        return {e["table_id"]: e for e in self.listing()["entries"] if e["status"] == "notified" and e["table_id"]}

    def notify(self, entry_id, table_id):
        with self.store.lock:
            entry = self._row(entry_id)
            if entry["status"] not in ("waiting", "notified"):
                raise Conflict("This party is no longer on the waitlist.")
            snapshot = self.store.snapshot()
            tables = {t["id"]: t for t in snapshot["tables"]}
            if table_id not in [t["id"] for t in self.store.mapping["tables"]]:
                raise KeyError("Table not found")
            table = tables.get(table_id)
            if table is not None and (table["state"] != "free" or table["customer_count"]):
                raise Conflict(f"Table {_table_number(table_id)} isn't free right now.")
            other = self.store.db.execute(
                "SELECT name FROM waitlist WHERE status='notified' AND table_id=? AND id<>?", (table_id, entry_id)).fetchone()
            if other:
                raise Conflict(f"Table {_table_number(table_id)} is already held for {other[0]}.")

            number = _table_number(table_id)
            message = (f"Hi {entry['name']}, table {number} is ready for your party of {entry['party_size']}. "
                       f"Please come to the host stand and we'll seat you.")
            # Send first: the party stays "waiting" if delivery fails.
            self.sender(self.server, entry["topic"] or self.topic, f"Table {number} is ready", message)

            with self.store.db:
                self.store.db.execute("UPDATE waitlist SET status='notified', table_id=?, notified_at=? WHERE id=?",
                                      (table_id, _now(), entry_id))
                run = self.store._load()
                if run is not None:
                    self.store._event(run, table_id, "guest_notified", {
                        "name": entry["name"], "party_size": entry["party_size"], "message": message})
            return self._row(entry_id)

    def close(self, entry_id, status):
        with self.store.lock, self.store.db:
            entry = self._row(entry_id)
            if entry["status"] not in ("waiting", "notified"):
                raise Conflict("This party is no longer on the waitlist.")
            self.store.db.execute("UPDATE waitlist SET status=?, closed_at=? WHERE id=?", (status, _now(), entry_id))
            return self._row(entry_id)
