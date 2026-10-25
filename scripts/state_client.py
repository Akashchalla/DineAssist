"""Send small detection observations to the local Phase 3 API, never video frames."""

import requests


class StateClient:
    def __init__(self, url):
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.run_id = None
        self.snapshot = None

    def request(self, path, body):
        try:
            response = self.session.post(self.url + path, json=body, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            detail = ""
            if error.response is not None:
                try:
                    detail = error.response.json().get("detail", "")
                except ValueError:
                    pass
            raise RuntimeError(f"State API request failed. Check that the local server is running. {detail}") from error

    def start(self, mode, greeting_seconds, zones):
        self.snapshot = self.request("/api/runs", {"mode": mode, "greeting_seconds": greeting_seconds})
        self.run_id = self.snapshot["source"]["id"]
        mapping = self.snapshot["mapping"]
        if mapping["tables"] != zones.tables or mapping["frame_size"] != {"width": zones.width, "height": zones.height}:
            self.stop("stopped")
            raise ValueError("Detector and API use different table maps. Restart the API with the matching RESTAURANT_ZONES file.")

    def observe(self, frame_number, media_seconds, people):
        self.snapshot = self.request(f"/api/runs/{self.run_id}/observations", {
            "frame_number": frame_number, "media_seconds": media_seconds,
            "people": [{"track_id": p["track_id"], "table_id": p["table_id"]} for p in people],
        })
        return self.snapshot

    def stop(self, reason):
        try:
            if self.run_id:
                self.request(f"/api/runs/{self.run_id}/stop", {"reason": reason})
        finally:
            self.run_id = None
            self.session.close()
