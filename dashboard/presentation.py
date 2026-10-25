"""Display helpers: keep data interpretation separate from the page layout."""

from datetime import datetime
import math
from zoneinfo import ZoneInfo

STATES = {"free": "Available", "occupied": "Occupied", "needs_cleaning": "Needs cleaning"}
# "After hours" palette: warm espresso surfaces, linen text, three state colors.
COLORS = {"free": "#86C08F", "occupied": "#E0656F", "needs_cleaning": "#E8B341", "unknown": "#7A6F64"}
# Map filter choices -> which tables stay bright.
FOCUS = {
    "All tables": None,
    "Needs attention": lambda t: needs_attention(t),
    "Occupied": lambda t: t["state"] == "occupied",
    "Needs cleaning": lambda t: t["state"] == "needs_cleaning",
    "Available": lambda t: t["state"] == "free",
}

# Floor-plan scene, in scene units. Tables are placed inside the dining area,
# below the bar along the top wall.
SCENE_W, SCENE_H = 1000, 660
AREA = (70, 110, 960, 630)  # left, top, right, bottom
# Table footprint including chairs, by seat count: (width, height).
FOOTPRINT = {2: (120, 70), 4: (138, 138), 6: (196, 140)}


def duration(seconds):
    if seconds is None or not math.isfinite(float(seconds)):
        return "—"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def table_name(table_id):
    return "Table " + table_id[6:] if table_id.startswith("table_") else table_id


def is_fresh(snapshot, connected=True):
    source = snapshot.get("source") or {}
    return connected and source.get("status") == "running" and source.get("fresh", False)


def source_label(snapshot, connected=True):
    source = snapshot.get("source")
    if not connected:
        return "Service offline", "Showing cached results. Availability is unknown and actions are disabled."
    if not source:
        return "Waiting for video", "Start the detector to see table observations here."
    status = source["status"]
    if is_fresh(snapshot):
        if source["mode"] == "video":
            return "Replaying video", "Timers follow the recording. Table states are estimates from person detections."
        return "Camera connected", "Table states are estimates from the latest person detections."
    if status == "running":
        return "Waiting for camera data", "Observations are missing or delayed. Availability is unknown; last known states are shown."
    if status == "completed":
        return "Video finished", "Playback has ended. Timers are frozen and these are the last recorded states."
    return "Source " + status, "The source is no longer updating. Timers are frozen; availability is unknown."


def needs_attention(table):
    return (table["state"] == "needs_cleaning" or
            (table["state"] == "occupied" and table.get("greeted_at") is None and table.get("greeting_alerted", False)))


def summary(snapshot, connected=True):
    tables = snapshot.get("tables", [])
    return {
        "available": sum(bool(t.get("available")) for t in tables) if is_fresh(snapshot, connected) else None,
        "recorded_free": sum(t.get("observed", False) and t["state"] == "free"
                             and not t.get("customer_count") and t.get("present_since") is None
                             for t in tables),
        "occupied": sum(t["state"] == "occupied" for t in tables),
        "cleaning": sum(t["state"] == "needs_cleaning" for t in tables),
        "attention": sum(needs_attention(t) for t in tables),
    }


def action_permissions(snapshot, table, connected=True):
    source = snapshot.get("source") or {}
    # Completed recordings support explicit corrections, as allowed by the API.
    usable = connected and bool(source) and (source["status"] != "running" or is_fresh(snapshot))
    return {
        "greet": usable and table["state"] == "occupied" and table.get("greeted_at") is None,
        "clean": usable and table["state"] == "needs_cleaning" and table.get("customer_count", 0) == 0,
        "label_staff": is_fresh(snapshot, connected),
    }


def timestamp(value, timezone="America/New_York"):
    if not value:
        return "—"
    return datetime.fromisoformat(value).astimezone(ZoneInfo(timezone)).strftime("%b %d, %I:%M:%S %p")


def event_description(event):
    details = event["details"]
    kind = event["kind"]
    if kind == "state_changed":
        if details.get("from") is None:
            return "Initialized · waiting for first observation"
        return f'{STATES.get(details["from"], details["from"])} → {STATES.get(details["to"], details["to"])}'
    if kind == "alert":
        return details.get("message", "Alert")
    if kind == "staff_interaction":
        return "Greeting recorded" if details.get("action") == "greeted" else "Cleaning confirmed"
    if kind == "staff_label":
        return f'P{details["track_id"]} ' + ("marked as staff" if details["enabled"] else "staff label removed")
    if kind == "source_started":
        return f'Run started · greeting deadline {duration(details["greeting_seconds"])}'
    if kind == "guest_notified":
        return f'Texted {details.get("name", "guest")} (party of {details.get("party_size", "?")}): table ready'
    if kind == "source_stopped":
        return f'Source stopped · {details.get("reason", "stopped")}'
    return kind.replace("_", " ").capitalize()


def _polygon_stats(points):
    """Centroid and area of a camera-map polygon (the last point may repeat the first)."""
    if len(points) > 3 and points[0] == points[-1]:
        points = points[:-1]
    n = len(points)
    area = 0.5 * abs(sum(points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1] for i in range(n)))
    return sum(p[0] for p in points) / n, sum(p[1] for p in points) / n, area


def floor_layout(mapping):
    """Turn the camera map into a top-down floor plan: {table_id: (x, y, seats)}.

    The camera looks down the room at an angle, so far tables (top of the image)
    look small and bunched together. The layout spreads the far rows apart, sizes
    each table from its depth-corrected area, then nudges overlapping tables apart
    while keeping their left/right and front/back order.
    """
    width, height = mapping["frame_size"]["width"], mapping["frame_size"]["height"]
    left, top, right, bottom = AREA
    placed = {}
    for zone in mapping["tables"]:
        cx, cy, area = _polygon_stats(zone["polygon"])
        depth = 0.35 + 0.65 * (cy / height)          # 1.0 = nearest the camera
        corrected = area / (depth * depth) * (1280 * 720) / (width * height)
        seats = 6 if corrected > 60000 else 4 if corrected > 25000 else 2
        x = left + (cx / width) * (right - left)
        y = top + (cy / height) ** 0.75 * (bottom - top)
        placed[zone["id"]] = [x, y, seats]

    gap = 16
    ids = list(placed)
    for _ in range(300):
        moved = False
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                ax, ay, sa = placed[a]
                bx, by, sb = placed[b]
                (aw, ah), (bw, bh) = FOOTPRINT[sa], FOOTPRINT[sb]
                ox = (aw + bw) / 2 + gap - abs(ax - bx)
                oy = (ah + bh) / 2 + gap - abs(ay - by)
                if ox > 0 and oy > 0:
                    moved = True
                    # Separate along the axis that needs the smaller push.
                    if ox < oy:
                        push = ox / 2 * (1 if ax >= bx else -1)
                        placed[a][0] += push
                        placed[b][0] -= push
                    else:
                        push = oy / 2 * (1 if ay >= by else -1)
                        placed[a][1] += push
                        placed[b][1] -= push
        for table_id in ids:
            x, y, seats = placed[table_id]
            w, h = FOOTPRINT[seats]
            placed[table_id][0] = min(max(x, left + w / 2), right - w / 2)
            placed[table_id][1] = min(max(y, top + h / 2), bottom - h / 2)
        if not moved:
            break
    return {k: (round(v[0], 1), round(v[1], 1), v[2]) for k, v in placed.items()}


def floor_scene(snapshot, selected=None, connected=True, focus="All tables", layout=None, holds=None):
    """Everything the animated floor plan needs, as plain JSON-ready data.

    Every person drawn comes from the detector: seated guests are the table's
    customer matches, and servers are tracks someone labelled as staff.
    """
    mapping = snapshot["mapping"]
    layout = layout or floor_layout(mapping)
    source = snapshot.get("source") or {}
    fresh = is_fresh(snapshot, connected)
    keep = FOCUS.get(focus)
    tables = {t["id"]: t for t in snapshot.get("tables", [])}
    items = []
    for zone in mapping["tables"]:
        table_id = zone["id"]
        table = tables.get(table_id, {})
        observed = bool(table.get("observed"))
        state = table.get("state", "free") if observed else "unknown"
        x, y, seats = layout[table_id]
        if state == "occupied":
            timer, timer_label = table.get("seated_seconds"), "seated"
        elif state == "needs_cleaning":
            timer, timer_label = table.get("state_elapsed_seconds"), "waiting"
        else:
            timer, timer_label = None, ""
        greeting = None
        if state == "occupied":
            greeting = ("greeted" if table.get("greeted_at") is not None
                        else "overdue" if table.get("greeting_alerted") else "due")
        items.append({
            "id": table_id, "label": table_id.replace("table_", "T"), "name": table_name(table_id),
            "x": x, "y": y, "seats": seats, "state": state, "stateName": STATES.get(state, "Not observed yet"),
            "customers": min(int(table.get("customer_count") or 0), seats),
            "staff": min(int(table.get("staff_count") or 0), 2),
            "pending": state == "free" and table.get("present_since") is not None,
            "attention": observed and needs_attention(table),
            "greeting": greeting,
            "dueIn": duration(table.get("greeting_due_in_seconds")) if greeting == "due" else None,
            "timer": duration(timer) if timer is not None else None, "timerLabel": timer_label,
            "selected": table_id == selected,
            "dim": keep is not None and not (observed and keep(table)),
            # A waitlist party was texted for this table and is on the way.
            "heldFor": (holds or {}).get(table_id),
        })
    status = "live" if fresh else ("offline" if not connected else
                                   "finished" if source.get("status") == "completed" else
                                   "waiting" if not source else "stale")
    return {"w": SCENE_W, "h": SCENE_H, "status": status, "runId": source.get("id"),
            "clock": duration(source.get("source_seconds")) if source else None, "tables": items}
