"""Animated top-down floor plan, built as a Streamlit components-v2 element.

The browser keeps one scene and receives fresh data on every refresh, so guests
can walk in and out instead of the picture being redrawn.
"""

from pathlib import Path

import streamlit as st

_HERE = Path(__file__).parent
_HTML = '<div class="tf-root"></div>'
_CSS = (_HERE / "floor.css").read_text(encoding="utf-8")
_JS = (_HERE / "floor.js").read_text(encoding="utf-8")


def floor_plan(scene, *, key="floor_plan", on_select=None):
    """Draw the floor plan. `on_select` runs when someone clicks a table; the
    clicked table ID is then in `st.session_state[key].select`."""
    # Register on every call: Streamlit 1.65 keeps registrations per runtime (a new
    # runtime would otherwise see "not registered"), and an identical
    # re-registration is silent and cheap.
    component = st.components.v2.component("dineassist_floor_plan", html=_HTML, css=_CSS, js=_JS)
    return component(key=key, data=scene, on_select_change=on_select or (lambda: None))
