"""Phase 4: run with `streamlit run dashboard/app.py`."""

import csv
from datetime import datetime
from html import escape
import io
import json
import os
from pathlib import Path
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard.client import APIClient, APIError
from dashboard.floor_plan import floor_plan
from dashboard.presentation import (
    COLORS, FOCUS, STATES, action_permissions, duration, event_description, floor_layout, floor_scene,
    is_fresh, needs_attention, source_label, summary, table_name, timestamp,
)

API_URL = os.environ.get("RESTAURANT_API_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEZONE = os.environ.get("RESTAURANT_TIMEZONE", "America/New_York")
client = APIClient(API_URL)

st.set_page_config(page_title="Tableflow · Dining room", page_icon="◉", layout="wide", initial_sidebar_state="collapsed")
# Colors and fonts come from .streamlit/config.toml; this block adds layout and motion.
st.markdown("""
<style>
:root {
  --night: #171310; --walnut: #211B16; --walnut-2: #2B241E; --rule: #3A3129;
  --linen: #F1E8DA; --smoke: #A99B8A;
  --sage: #86C08F; --claret: #E0656F; --saffron: #E8B341; --ash: #7A6F64;
  --ease: cubic-bezier(.2, .7, .2, 1);
}
.block-container {max-width: 1480px; padding-top: 2.2rem; padding-bottom: 3rem; position: relative; z-index: 1;}
[data-testid="stHeader"] {background: transparent;}

/* Ambient light: three warm glows drifting slowly behind the page. */
[data-testid="stAppViewContainer"] {background: radial-gradient(120% 80% at 50% -10%, #241A14 0%, var(--night) 55%) fixed;}
[data-testid="stAppViewContainer"]::before, [data-testid="stAppViewContainer"]::after {
  content: ""; position: fixed; z-index: 0; pointer-events: none; border-radius: 50%; filter: blur(90px); opacity: .5;}
[data-testid="stAppViewContainer"]::before {width: 46vw; height: 46vw; left: -12vw; top: -14vw;
  background: radial-gradient(circle, rgba(224,101,111,.35), transparent 65%); animation: drift-a 26s ease-in-out infinite alternate;}
[data-testid="stAppViewContainer"]::after {width: 40vw; height: 40vw; right: -10vw; top: 30vh;
  background: radial-gradient(circle, rgba(232,179,65,.22), rgba(134,192,143,.12) 45%, transparent 70%);
  animation: drift-b 32s ease-in-out infinite alternate;}
@keyframes drift-a {to {transform: translate(18vw, 22vh) scale(1.15);}}
@keyframes drift-b {to {transform: translate(-22vw, -12vh) scale(.9);}}

/* Masthead: the page's one load sequence. It sits outside the auto-refreshing
   section, so a refresh never replays it. */
.masthead > * {animation: rise .7s var(--ease) both;}
.masthead .page-title {animation-delay: .08s;}
.masthead .subtitle {animation-delay: .16s;}
@keyframes rise {from {opacity: 0; transform: translateY(14px);} to {opacity: 1; transform: none;}}

.brand {display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 650;
  font-variation-settings: "wdth" 112; color: var(--smoke); margin-bottom: 14px;}
.brand-mark {width: 12px; height: 12px; border-radius: 50%; border: 2px solid var(--linen); position: relative;}
.brand-mark::after {content: ""; position: absolute; inset: 2px; border-radius: 50%; background: var(--linen);}
.page-title {font-size: clamp(42px, 6vw, 76px); line-height: .95; font-weight: 760;
  font-variation-settings: "wdth" 125; letter-spacing: -.02em; color: var(--linen); margin: 0 0 12px;}
.subtitle {color: var(--smoke); font-size: 16px; margin: 0 0 6px; max-width: 60ch;}

/* Source status: a breathing dot while data is live. */
.status-bar {display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 14px; border: 1px solid var(--rule);
  background: var(--walnut); border-radius: 12px; padding: 13px 18px; margin: 14px 0 22px; font-size: 14px;}
.status-bar b {color: var(--linen); font-weight: 650; display: inline-flex; align-items: center; gap: 10px;}
.status-bar span {color: var(--smoke);}
.status-dot {width: 9px; height: 9px; border-radius: 50%; background: var(--ash); flex: none;}
.status-bar.live .status-dot {background: var(--sage); animation: breathe 2.4s ease-in-out infinite;}
.status-bar.stale .status-dot {background: var(--saffron);}
.status-bar.offline .status-dot {background: var(--claret);}
@keyframes breathe {0%, 100% {box-shadow: 0 0 0 0 rgba(134,192,143,.55);} 50% {box-shadow: 0 0 0 7px rgba(134,192,143,0);}}

/* Pass board: four glass cards, each lit by its state color. */
.st-key-pass_board [data-testid="stMetric"] {position: relative; overflow: hidden; border-radius: 18px;
  padding: 18px 22px 14px; background: linear-gradient(160deg, rgba(43,36,30,.82), rgba(28,23,19,.72));
  border: 1px solid rgba(241,232,218,.09); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  box-shadow: 0 20px 40px -26px rgba(0,0,0,.9), inset 0 1px 0 rgba(255,255,255,.05);
  transition: transform .35s var(--ease), border-color .35s;}
.st-key-pass_board [data-testid="stMetric"]::before {content: ""; position: absolute; inset: 0 0 auto 0; height: 3px;
  background: var(--metric-color);}
.st-key-pass_board [data-testid="stMetric"]::after {content: ""; position: absolute; width: 160px; height: 160px; right: -60px; top: -70px;
  border-radius: 50%; background: radial-gradient(circle, var(--metric-color), transparent 70%); opacity: .22;}
.st-key-pass_board [data-testid="stMetric"]:hover {transform: translateY(-3px); border-color: rgba(241,232,218,.2);}
.st-key-pass_board [data-testid="stColumn"]:nth-child(1) {--metric-color: var(--sage);}
.st-key-pass_board [data-testid="stColumn"]:nth-child(2) {--metric-color: var(--claret);}
.st-key-pass_board [data-testid="stColumn"]:nth-child(3) {--metric-color: var(--saffron);}
.st-key-pass_board [data-testid="stColumn"]:nth-child(4) {--metric-color: var(--linen);}
.st-key-pass_board [data-testid="stMetricLabel"] p {color: var(--smoke); font-size: 14px;}
.st-key-pass_board [data-testid="stMetricValue"] {font-size: 56px; line-height: 1.05; font-weight: 620;
  font-variation-settings: "wdth" 72; font-variant-numeric: tabular-nums; color: var(--linen);}
@keyframes alarm {0%, 100% {border-color: rgba(224,101,111,.35); box-shadow: 0 0 0 0 rgba(224,101,111,0);}
  50% {border-color: rgba(224,101,111,.9); box-shadow: 0 0 34px -6px rgba(224,101,111,.55);}}

/* Panels: frosted glass over the ambient light. */
.st-key-map_panel, .st-key-details_panel, .st-key-queue_panel {
  background: linear-gradient(165deg, rgba(43,36,30,.78), rgba(26,21,17,.7));
  border: 1px solid rgba(241,232,218,.09) !important; border-radius: 22px; padding: 20px 22px !important;
  backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 30px 60px -36px rgba(0,0,0,.95), inset 0 1px 0 rgba(255,255,255,.05);}

/* Table details */
.table-state {display: inline-flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 650; margin: 2px 0 14px;}
.table-state i {width: 9px; height: 9px; border-radius: 50%; background: currentColor;}
.timer-label {color: var(--smoke); font-size: 14px;}
.timer {font-size: 84px; line-height: 1; margin: 4px 0 6px; font-weight: 640; color: var(--linen);
  font-variation-settings: "wdth" 66; font-variant-numeric: tabular-nums; letter-spacing: -.01em;}

/* Buttons answer the press. */
[data-testid^="stBaseButton"] {transition: transform .12s var(--ease), background-color .2s, border-color .2s;}
[data-testid^="stBaseButton"]:active:not(:disabled) {transform: scale(.97);}
[data-testid="stBaseButton-primary"] {color: var(--night) !important; font-weight: 650;}
[data-testid^="stBaseButton"]:focus-visible {outline: 2px solid var(--linen); outline-offset: 2px;}

/* Service queue rows carry their state color; overdue greetings glow. */
[class*="st-key-queue_greet_"] button, [class*="st-key-queue_clean_"] button {
  border-left: 4px solid var(--q) !important; background: var(--walnut-2); padding: 10px 16px;}
[class*="st-key-queue_"] button > div {justify-content: flex-start; width: 100%;}
[class*="st-key-queue_greet_"] {--q: var(--claret);}
[class*="st-key-queue_clean_"] {--q: var(--saffron);}
[class*="st-key-queue_greet_"] button {animation: glow 2.2s ease-in-out infinite;}
@keyframes glow {0%, 100% {box-shadow: 0 0 0 0 rgba(224,101,111,0);} 50% {box-shadow: 0 0 18px -4px rgba(224,101,111,.55);}}

/* Messages use the palette: claret for overdue/errors, saffron for cleaning. */
[data-testid="stAlertContainer"] {border-left: 3px solid var(--a, var(--rule)); border-radius: 10px;}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) {--a: var(--claret); background: rgba(224,101,111,.13) !important;}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) {--a: var(--saffron); background: rgba(232,179,65,.11) !important;}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) {--a: var(--sage); background: rgba(134,192,143,.12) !important;}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {--a: var(--smoke); background: var(--walnut-2) !important;}
[data-testid="stAlertContainer"] p {color: var(--linen);}

/* Waitlist */
.ready-banner {display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: 14px; font-size: 14px;
  background: rgba(134,192,143,.12); border: 1px solid rgba(134,192,143,.4); animation: ready 2.6s ease-in-out infinite;}
.ready-banner.empty {display: none;}
.ready-banner i {width: 10px; height: 10px; border-radius: 50%; background: var(--sage); flex: none;}
.ready-banner b {color: var(--sage);}
@keyframes ready {50% {box-shadow: 0 0 26px -6px rgba(134,192,143,.6);}}
[class*="st-key-party_"] {border-top: 1px solid rgba(241,232,218,.08); padding-top: 12px;}
.party {display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 10px;}
.party b {font-size: 17px; font-variation-settings: "wdth" 108;}
.party span {color: var(--smoke); font-size: 13px;}
.party em {font-style: normal; width: 100%; font-size: 13px; color: var(--smoke);}
.party em.notified {color: var(--sage);}

[data-baseweb="tab-highlight"] {background-color: var(--linen) !important;}
[data-testid="stToast"] {background: var(--walnut-2); border: 1px solid var(--rule);}

@media (max-width: 900px) {
 [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .st-key-map_panel) {flex-wrap: wrap;}
 [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .st-key-map_panel) > [data-testid="stColumn"] {width: 100%; flex: 1 1 100%; min-width: 100%;}
 .st-key-pass_board [data-testid="stHorizontalBlock"] {flex-wrap: wrap;}
 .st-key-pass_board [data-testid="stColumn"] {flex: 1 1 40%; min-width: 40%;}
}
@media (max-width: 700px) {.block-container {padding: 1rem;} .st-key-pass_board [data-testid="stMetricValue"] {font-size: 42px;}}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {animation: none !important; transition: none !important;}
}
</style>
""", unsafe_allow_html=True)

heading, settings = st.columns([4, 1], vertical_alignment="bottom")
with heading:
    st.markdown('<div class="masthead"><div class="brand"><span class="brand-mark"></span>Tableflow</div>'
                '<div class="page-title">Dining room</div>'
                '<p class="subtitle">Every table. Every greeting. A little less waiting.</p></div>',
                unsafe_allow_html=True)
with settings:
    auto_refresh = st.toggle("Live updates", value=True, help="Fetch the latest table data every two seconds.")


def choose_table(table_id):
    st.session_state.selected_table = table_id


def floor_selection():
    result = st.session_state.get("floor_plan")
    picked = getattr(result, "select", None) if result is not None else None
    if isinstance(picked, str):
        st.session_state.selected_table = picked


@st.cache_data(show_spinner=False)
def cached_layout(mapping_json):
    return floor_layout(json.loads(mapping_json))


def do_action(run_id, table_id, action):
    try:
        client.confirm(run_id, table_id, action)
        st.session_state.last_action = (run_id, "success", f"{table_name(table_id)}: " + ("greeting recorded." if action == "greet" else "cleaning confirmed."))
    except APIError as error:
        st.session_state.last_action = (run_id, "error", str(error))


def staff_action(run_id, track_id, enabled):
    try:
        client.staff(run_id, track_id, enabled)
        st.session_state.last_action = (run_id, "success", f"P{track_id}: " + ("marked as staff. Applies to the next observation." if enabled else "staff label removed."))
    except APIError as error:
        st.session_state.last_action = (run_id, "error", str(error))


def add_party_cb():
    name = (st.session_state.get("wl_name") or "").strip()
    if not name:
        st.session_state.wl_msg = ("error", "Enter the guest's name.")
        return
    try:
        client.add_party(name, st.session_state.get("wl_size", 2))
        st.session_state.wl_msg = ("success", f"{name} added to the waitlist.")
    except APIError as error:
        st.session_state.wl_msg = ("error", str(error))


def notify_cb(entry_id, name, select_key):
    table_id = st.session_state.get(select_key)
    if not table_id:
        return
    try:
        client.notify_party(entry_id, table_id)
        st.session_state.wl_msg = ("success", f"Texted {name}: {table_name(table_id)} is ready.")
        # Shown by the page on its next run; callbacks inside a fragment shouldn't draw elements.
        st.session_state.wl_toast = f"Sent to {name}: {table_name(table_id)} is ready"
    except APIError as error:
        st.session_state.wl_msg = ("error", str(error))


def close_cb(entry_id, name, status):
    try:
        client.close_party(entry_id, status)
        st.session_state.wl_msg = ("success", f"{name} " + ("seated." if status == "seated" else "removed from the waitlist."))
    except APIError as error:
        st.session_state.wl_msg = ("error", str(error))


def waited(added_at):
    try:
        return duration((datetime.now().astimezone() - datetime.fromisoformat(added_at)).total_seconds())
    except (TypeError, ValueError):
        return "—"


def fetch_events(run_id):
    if st.session_state.get("history_run") != run_id:
        st.session_state.update(history_run=run_id, history=[], history_cursor=0)
    # Incremental pagination avoids repeatedly downloading all history.
    for _ in range(5):
        page = client.events(run_id, st.session_state.history_cursor)
        if page:
            st.session_state.history_cursor = page[-1]["id"]
            st.session_state.history = (st.session_state.history + page)[-200:]
        if len(page) < 1000:
            return False
    return True


def announce_new_alerts(run_id):
    """Pop up alerts that arrived since the last refresh; never replay old ones."""
    cursor = st.session_state.get("history_cursor", 0)
    if st.session_state.get("toast_run") != run_id:
        st.session_state.update(toast_run=run_id, toast_cursor=cursor)
        return
    new = [e for e in st.session_state.get("history", [])
           if e["kind"] == "alert" and e["id"] > st.session_state.toast_cursor]
    st.session_state.toast_cursor = cursor
    for event in new[-3:]:
        cleaning = event["details"].get("type") == "needs_cleaning"
        st.toast(f'{table_name(event["table_id"] or "")}: ' + ("needs cleaning" if cleaning else "greeting overdue"),
                 icon=":material/cleaning_services:" if cleaning else ":material/room_service:")
    if len(new) > 3:
        st.toast(f"{len(new) - 3} more alerts are in the activity log.", icon=":material/notifications:")


@st.fragment(run_every=2 if auto_refresh else None)
def live_dashboard():
    connected = True
    try:
        snapshot = client.snapshot()
        st.session_state.last_snapshot = snapshot
        st.session_state.last_success = datetime.now().astimezone().isoformat()
    except APIError as error:
        connected = False
        st.error(str(error))
        with st.expander("How to reconnect"):
            st.write("Keep the API server running in a terminal, then select Refresh now.")
            st.code(".venv/bin/python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000 --workers 1", language="bash")
        snapshot = st.session_state.get("last_snapshot")
        if snapshot is None:
            st.info("No table data has been received yet. The map will appear when the service connects.")
            st.button("Refresh now", key="refresh_empty")
            return

    source = snapshot.get("source") or {}
    run_id = source.get("id")
    fresh = is_fresh(snapshot, connected)
    counts = summary(snapshot, connected)
    label, explanation = source_label(snapshot, connected)
    status_class = "live" if fresh else ("offline" if not connected else "stale")
    # The attention count pulses only while something needs attention.
    alarm = ('<style>.st-key-pass_board [data-testid="stColumn"]:nth-child(4) [data-testid="stMetric"]'
             '{animation: alarm 1.6s ease-in-out infinite;}'
             '.st-key-pass_board [data-testid="stColumn"]:nth-child(4) [data-testid="stMetricValue"]{color: var(--claret);}</style>'
             if counts["attention"] else "")
    st.markdown(f'<div class="status-bar {status_class}"><b><i class="status-dot"></i>{escape(label)}</b>'
                f'<span>{escape(explanation)}</span></div>{alarm}', unsafe_allow_html=True)

    with st.container(key="pass_board"):
        metrics = st.columns(4)
        for column, title, value in zip(metrics, ["Available now", "Occupied", "Needs cleaning", "Needs attention"],
                                        [counts["available"], counts["occupied"], counts["cleaning"], counts["attention"]]):
            column.metric(title, "—" if value is None else value)
    # Always render this caption: adding or removing an element here would shift
    # everything below it, and Streamlit would rebuild the animated floor plan.
    st.caption("Live counts, refreshed every two seconds." if fresh
               else "Last recorded counts. Live availability can't be confirmed.")

    tables = snapshot.get("tables", [])
    table_ids = [zone["id"] for zone in snapshot["mapping"]["tables"]]
    table_by_id = {table["id"]: table for table in tables}
    if st.session_state.get("selected_table") not in table_ids:
        st.session_state.selected_table = table_ids[0] if table_ids else None
    selected = st.session_state.get("selected_table")
    history_error = None
    catching_up = False
    if run_id and connected:
        try:
            catching_up = fetch_events(run_id)
            announce_new_alerts(run_id)
        except APIError as error:
            history_error = str(error)

    waitlist, waitlist_error = {"entries": [], "topic": None, "server": None}, None
    if connected:
        try:
            waitlist = client.waitlist()
        except APIError as error:
            waitlist_error = str(error)
    entries = waitlist.get("entries", [])
    holds = {e["table_id"]: f'{e["name"]} ({e["party_size"]})' for e in entries if e["status"] == "notified" and e["table_id"]}
    layout = cached_layout(json.dumps(snapshot["mapping"], sort_keys=True))

    overview_tab, activity_tab = st.tabs(["Floor overview", "Activity log"])
    with overview_tab, st.container(key="overview"):
        map_column, detail_column = st.columns([2.4, 1], gap="large")
        with map_column, st.container(key="map_panel"):
            title_column, refresh_column = st.columns([3, 1], vertical_alignment="center")
            title_column.subheader("Floor map")
            refresh_column.button("Refresh now", key="refresh", width="stretch")
            focus = st.segmented_control("Show", list(FOCUS), default="All tables", key="map_focus",
                                         help="Dim every table outside this group.") or "All tables"
            floor_plan(floor_scene(snapshot, selected, connected, focus, layout, holds), key="floor_plan",
                       on_select=floor_selection)
            st.caption("Click a table to open its details. Guests are drawn from live person detections; "
                       "servers appear only for people you've marked as staff.")

        with detail_column, st.container(key="details_panel"):
            st.subheader("Table details")
            if not table_ids:
                st.info("No tables are mapped yet.")
            else:
                selected = st.selectbox("Select a table", table_ids, format_func=table_name, key="selected_table")
                table = table_by_id.get(selected)
                if not table or not table.get("observed"):
                    st.info("Waiting for this table's first observation.")
                else:
                    state = table["state"]
                    st.markdown(f'<div class="table-state" style="color:{COLORS[state]}"><i></i>{escape(STATES[state])}'
                                f'{" (recorded)" if not fresh else ""}</div>', unsafe_allow_html=True)
                    timer_label = "Time seated" if state == "occupied" else ("Waiting for cleaning" if state == "needs_cleaning" else "Free for")
                    timer_value = table["seated_seconds"] if state == "occupied" else table["state_elapsed_seconds"]
                    st.markdown(f'<div class="timer-label">{timer_label}</div><div class="timer">{duration(timer_value)}</div>', unsafe_allow_html=True)
                    st.caption(f'{table["customer_count"]} customer matches, {table["staff_count"]} staff matches')
                    if state == "occupied":
                        if table.get("greeted_at") is not None:
                            st.success("Greeting recorded")
                        elif table.get("greeting_alerted"):
                            st.error("Greeting overdue" + (" in this recording." if not fresh else "."),
                                     icon=":material/room_service:")
                        else:
                            deadline = source.get("greeting_seconds") or 300
                            st.progress(min(1.0, (table.get("seated_seconds") or 0) / deadline),
                                        text=f'Greeting due in {duration(table.get("greeting_due_in_seconds"))}')
                    elif state == "needs_cleaning":
                        st.warning("Confirm cleaning after the table has been prepared.",
                                   icon=":material/cleaning_services:")
                    elif table.get("present_since") is not None:
                        st.info("Possible arrival. Waiting for a steady detection.")
                    permissions = action_permissions(snapshot, table, connected)
                    st.button("Record greeting", key="greet", type="primary", width="stretch",
                              disabled=not permissions["greet"], on_click=do_action, args=(run_id, selected, "greet"))
                    st.button("Confirm cleaned", key="clean", width="stretch",
                              disabled=not permissions["clean"], on_click=do_action, args=(run_id, selected, "clean"))
                    if source.get("status") != "running":
                        st.caption("Confirmations update the saved run. They don't resume the video.")
                    action = st.session_state.get("last_action")
                    if action and action[0] == run_id:
                        getattr(st, action[1])(action[2])

        with detail_column, st.container(key="waitlist_panel"):
            st.subheader("Waitlist")
            # Tables a party could take now: free, empty and not already held for someone.
            ready = [t for t in tables if t.get("observed") and t["state"] == "free"
                     and not t.get("customer_count") and t["id"] not in holds]
            if not run_id:
                ready = [{"id": i} for i in table_ids if i not in holds]
            waiting = [e for e in entries if e["status"] == "waiting"]
            # Always render the banner (empty when there's nothing to say): adding or removing
            # it would rebuild the form below and wipe what the host is typing.
            banner = '<div class="ready-banner empty"></div>'
            if ready and waiting:
                first = waiting[0]
                fits = [t for t in ready if layout[t["id"]][2] >= first["party_size"]] or ready
                banner = (f'<div class="ready-banner"><i></i><span><b>{escape(table_name(fits[0]["id"]))} is ready.</b> '
                          f'Next up: {escape(first["name"])}, party of {first["party_size"]}.</span></div>')
            st.markdown(banner, unsafe_allow_html=True)
            with st.form("add_party", clear_on_submit=True, border=False):
                name_column, size_column = st.columns([2, 1], vertical_alignment="bottom")
                name_column.text_input("Guest name", key="wl_name", max_chars=40, placeholder="e.g. Akash")
                size_column.number_input("Party size", min_value=1, max_value=20, value=2, key="wl_size")
                st.form_submit_button("Add to waitlist", on_click=add_party_cb, width="stretch",
                                      icon=":material/person_add:", disabled=not connected)
            toast = st.session_state.pop("wl_toast", None)
            if toast:
                st.toast(toast, icon=":material/sms:")
            message = st.session_state.get("wl_msg")
            if message:
                getattr(st, message[0])(message[1])
            if waitlist_error:
                st.warning("The waitlist could not be loaded. " + waitlist_error)
            if not entries:
                st.caption("No one is waiting. Add a party when the room is full.")
            for entry in entries:
                with st.container(key=f"party_{entry['id']}"):
                    status_line = (f'Waiting {waited(entry["added_at"])}' if entry["status"] == "waiting" else
                                   f'Texted for {table_name(entry["table_id"])} at {timestamp(entry["notified_at"], TIMEZONE)[-11:]}')
                    st.markdown(f'<div class="party"><b>{escape(entry["name"])}</b><span>Party of {entry["party_size"]}</span>'
                                f'<em class="{entry["status"]}">{escape(status_line)}</em></div>', unsafe_allow_html=True)
                    if entry["status"] == "waiting":
                        options = sorted(ready, key=lambda t: (layout[t["id"]][2] < entry["party_size"],
                                                               layout[t["id"]][2], t["id"]))
                        if options:
                            select_key = f"wl_table_{entry['id']}"
                            pick_column, send_column = st.columns([1.2, 1], vertical_alignment="bottom")
                            pick_column.selectbox("Table", [t["id"] for t in options], key=select_key,
                                                  format_func=lambda i: f"{table_name(i)} ({layout[i][2]} seats)",
                                                  label_visibility="collapsed")
                            send_column.button("Text guest", key=f"wl_notify_{entry['id']}", type="primary",
                                               icon=":material/sms:", width="stretch", disabled=not connected,
                                               on_click=notify_cb, args=(entry["id"], entry["name"], select_key))
                        else:
                            st.caption("No free table yet.")
                        st.button("Remove", key=f"wl_remove_{entry['id']}", disabled=not connected,
                                  on_click=close_cb, args=(entry["id"], entry["name"], "removed"))
                    else:
                        seat_column, remove_column = st.columns(2)
                        seat_column.button("Seated", key=f"wl_seat_{entry['id']}", type="primary", width="stretch",
                                           icon=":material/check:", disabled=not connected,
                                           on_click=close_cb, args=(entry["id"], entry["name"], "seated"))
                        remove_column.button("Remove", key=f"wl_remove_{entry['id']}", width="stretch",
                                             disabled=not connected,
                                             on_click=close_cb, args=(entry["id"], entry["name"], "removed"))
            if waitlist.get("topic"):
                with st.expander("Get these messages on your phone"):
                    st.markdown("1. Install the free **ntfy** app (App Store or Google Play).\n"
                                "2. Tap **+**, then subscribe to this topic:")
                    st.code(waitlist["topic"], language=None)
                    st.caption("Anyone who knows the topic name can read its messages, so keep it private. "
                               "Each message is sent to the restaurant topic unless the party has its own.")

        with st.expander("Identify staff"):
            st.caption("Use a person's P-number from the detector preview. Labels last for this run only; tracking IDs can change.")
            known = source.get("staff_ids", [])
            visible = sorted({p["track_id"] for p in source.get("latest_people", []) if p["track_id"] is not None} - set(known))
            add_column, remove_column = st.columns(2)
            with add_column:
                track = st.selectbox("Visible person", visible, index=0 if visible else None, format_func=lambda x: f"P{x}", key="staff_pick", disabled=not fresh)
                st.button("Mark as staff", key="staff_add", disabled=not fresh or track is None,
                          on_click=staff_action, args=(run_id, track, True))
            with remove_column:
                staff = st.selectbox("Staff labels", known, index=0 if known else None, format_func=lambda x: f"P{x}", key="staff_remove_pick", disabled=not fresh)
                st.button("Remove staff label", key="staff_remove", disabled=not fresh or staff is None,
                          on_click=staff_action, args=(run_id, staff, False))
            if not fresh:
                st.info("Staff labeling is available while the detector is sending fresh observations.")

        attention = sorted((t for t in tables if needs_attention(t)),
                           key=lambda t: t.get("state_elapsed_seconds", 0), reverse=True)
        with st.container(key="queue_panel"):
            st.subheader("Service queue" if fresh else "Recorded service queue")
            if not attention:
                st.caption("Nothing needs attention right now." if run_id else "Alerts will appear once a run starts.")
            for table in attention:
                cleaning = table["state"] == "needs_cleaning"
                message = "needs cleaning" if cleaning else "greeting overdue"
                st.button(f'{table_name(table["id"])}: {message} for {duration(table["state_elapsed_seconds"])}',
                          key=f'queue_{"clean" if cleaning else "greet"}_{table["id"]}', width="stretch",
                          icon=":material/cleaning_services:" if cleaning else ":material/room_service:",
                          on_click=choose_table, args=(table["id"],))

        st.subheader("All tables")
        sort_order = st.selectbox("Order tables by", ["Table number", "Longest seated", "Needs attention first"], key="sort_order")
        ordered = list(tables)
        if sort_order == "Longest seated":
            ordered.sort(key=lambda t: t.get("seated_seconds") if t.get("seated_seconds") is not None else -1, reverse=True)
        elif sort_order == "Needs attention first":
            ordered.sort(key=lambda t: (needs_attention(t), t.get("state_elapsed_seconds", 0)), reverse=True)
        rows = [{"Table": table_name(t["id"]), "State": STATES[t["state"]] if t["observed"] else "Not observed",
                 "Time seated": duration(t.get("seated_seconds")), "Time in state": duration(t.get("state_elapsed_seconds")),
                 "Customer matches": t["customer_count"],
                 "Greeting": "Recorded" if t.get("greeted_at") is not None else ("Overdue" if t["state"] == "occupied" and t.get("greeting_alerted") else "—")}
                for t in ordered]
        if rows:
            st.dataframe(rows, hide_index=True, width="stretch")
        else:
            st.info("Start the detector to populate table states.")
        st.caption("Time seated helps prioritize service. It does not predict when a party will leave.")

    with activity_tab:
        st.subheader("Activity log")
        st.caption(f"Latest 100 loaded events from this run. Times are in {TIMEZONE.replace('_', ' ')}.")
        if history_error:
            st.warning("Activity could not be refreshed. Previously loaded events are shown.")
        if catching_up:
            st.info("Loading event history. More recent events will appear on the next refresh.")
        events = st.session_state.get("history", []) if st.session_state.get("history_run") == run_id else []
        category = st.selectbox("Show events", ["All events", "Alerts", "State changes", "Staff actions"], key="event_category")
        kinds = {"Alerts": {"alert"}, "State changes": {"state_changed"}, "Staff actions": {"staff_label", "staff_interaction"}}
        filtered = [e for e in events if category == "All events" or e["kind"] in kinds[category]]
        event_rows = [{"Time": timestamp(e["recorded_at"], TIMEZONE), "Table": table_name(e["table_id"]) if e["table_id"] else "All tables",
                       "Event": event_description(e), "Source time": duration(e["source_seconds"])}
                      for e in list(reversed(filtered))[:100]]
        if event_rows:
            st.dataframe(event_rows, hide_index=True, width="stretch", height=480)
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=list(event_rows[0]))
            writer.writeheader()
            for row in event_rows:
                writer.writerow({key: "'" + value if value.startswith(("=", "+", "-", "@")) else value for key, value in row.items()})
            st.download_button("Download displayed events", output.getvalue(), file_name="tableflow-events.csv", mime="text/csv", key="export_events")
        else:
            st.info("No events in this category yet.")
        st.caption("This is an event log, not a historical peak-hour report. Video replay timestamps must not be treated as restaurant operating hours.")

    footer = f'{len(table_ids)} mapped tables'
    if run_id:
        footer += f' · {"Recording" if source["mode"] == "video" else "Camera"} clock {duration(source["source_seconds"])} · Greeting deadline {duration(source["greeting_seconds"])}'
        if source["greeting_seconds"] != 300:
            footer += " (custom test deadline)"
    if st.session_state.get("last_success"):
        footer += " · Last fetched " + timestamp(st.session_state.last_success, TIMEZONE)
    st.caption(footer)
    with st.expander("Run and connection details"):
        st.write("API:", API_URL)
        st.write("Run:", run_id or "Not started")
        st.link_button("Open API documentation", API_URL + "/docs")
        st.caption("To replay the existing video, run this in the activated project terminal:")
        st.code("python scripts/detect_people.py --api http://127.0.0.1:8000", language="bash")


live_dashboard()
