"""Small HTTP client: the dashboard talks to the API, not directly to SQLite."""

from urllib.parse import quote

import requests


class APIError(RuntimeError):
    pass


class APIClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")

    def _request(self, method, path, **kwargs):
        try:
            kwargs.setdefault("timeout", 3)
            response = requests.request(method, self.base_url + path, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as error:
            try:
                detail = error.response.json().get("detail", "The action could not be completed.")
            except ValueError:
                detail = "The action could not be completed. Refresh and try again."
            raise APIError(str(detail)) from error
        except (requests.RequestException, ValueError) as error:
            raise APIError("Cannot reach the restaurant service. Check that the API server is running.") from error

    def snapshot(self):
        result = self._request("GET", "/api/tables")
        if not isinstance(result, dict) or not {"source", "tables", "mapping"} <= result.keys():
            raise APIError("The service returned an unexpected response. Check the API address.")
        return result

    def events(self, run_id, after_id=0):
        return self._request("GET", "/api/events", params={"run_id": run_id, "after_id": after_id, "limit": 1000})

    def confirm(self, run_id, table_id, action):
        if action not in ("greet", "clean"):
            raise ValueError("Unknown table action")
        return self._request("POST", f"/api/tables/{quote(table_id, safe='')}/{action}", json={"run_id": run_id})

    def waitlist(self):
        return self._request("GET", "/api/waitlist")

    def add_party(self, name, party_size, topic=None):
        body = {"name": name, "party_size": int(party_size)}
        if topic:
            body["topic"] = topic
        return self._request("POST", "/api/waitlist", json=body)

    def notify_party(self, entry_id, table_id):
        # Sending can wait on the ntfy server, so allow longer than other calls.
        return self._request("POST", f"/api/waitlist/{int(entry_id)}/notify", json={"table_id": table_id}, timeout=12)

    def close_party(self, entry_id, status):
        return self._request("POST", f"/api/waitlist/{int(entry_id)}/close", json={"status": status})

    def staff(self, run_id, track_id, enabled):
        return self._request("POST" if enabled else "DELETE", f"/api/staff/{int(track_id)}", json={"run_id": run_id})
