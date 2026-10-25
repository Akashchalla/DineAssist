"""Phase 2: track people and measure their overlap with saved table zones."""

import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

import cv2
import numpy as np

from map_tables import validate_polygon

ROOT = Path(__file__).resolve().parents[1]
WINDOW = "Restaurant - person detection"


class TableZones:
    """Turn each polygon into a pixel mask, like a filled-in stencil."""

    def __init__(self, path, frame_shape):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.height, self.width = frame_shape[:2]
        if data.get("schema_version") != 1 or data.get("coordinate_system") != "original_frame_pixels":
            raise ValueError("Unsupported zone file. Use a JSON map saved by map_tables.py.")
        if data.get("frame_size") != {"width": self.width, "height": self.height}:
            raise ValueError("Video size differs from the saved map. Use the original video/camera settings or remap it.")
        self.tables = data.get("tables", [])
        if not self.tables:
            raise ValueError("The zone file contains no tables. Save at least one outline in the mapper.")
        self.masks = {}
        for table in self.tables:
            name = table.get("id")
            if not isinstance(name, str) or not name or name in self.masks:
                raise ValueError("Each table must have a unique, nonempty text ID.")
            points = table.get("polygon", [])
            if not isinstance(points, list) or any(
                not isinstance(p, list) or len(p) != 2
                or any(type(v) is not int for v in p) for p in points
            ):
                raise ValueError(f"{name}: corners must be pairs of whole-number pixel coordinates.")
            validate_polygon(points)
            if any(not (0 <= x < self.width and 0 <= y < self.height) for x, y in points):
                raise ValueError(f"{name}: a corner is outside the video image.")
            mask = np.zeros((self.height, self.width), dtype=np.uint8)
            cv2.fillPoly(mask, [np.array(points, dtype=np.int32)], 1)
            self.masks[name] = mask

    def match(self, box, minimum_overlap):
        """Assign at most one table per person, using the strongest box overlap."""
        if len(box) != 4 or not all(math.isfinite(v) for v in box):
            return None, 0.0
        x1, y1 = max(0, math.floor(box[0])), max(0, math.floor(box[1]))
        x2, y2 = min(self.width, math.ceil(box[2])), min(self.height, math.ceil(box[3]))
        area = (x2 - x1) * (y2 - y1)
        if x2 <= x1 or y2 <= y1:
            return None, 0.0
        best_table, best_overlap = None, 0.0
        for name, mask in self.masks.items():
            overlap = cv2.countNonZero(mask[y1:y2, x1:x2]) / area
            if overlap > best_overlap:
                best_table, best_overlap = name, overlap
        return (best_table if best_overlap >= minimum_overlap else None), best_overlap


def open_video(source):
    is_stream = source.lower().startswith(("rtsp://", "rtsps://", "http://", "https://"))
    if not is_stream and not Path(source).is_file():
        raise ValueError("Video file not found. Check --source.")
    if is_stream:
        capture = cv2.VideoCapture(source, cv2.CAP_FFMPEG, [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000,
        ])
    else:
        capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        capture.release()
        raise ValueError("Cannot open video. Check the file or camera connection, address and credentials.")
    return capture, is_stream


def detect_frame(model, frame, zones, args):
    # Class 0 is 'person' in this pretrained COCO model.
    result = model.track(frame, persist=True, tracker="bytetrack.yaml", classes=[0],
                         conf=args.confidence, imgsz=args.image_size,
                         device=args.device, verbose=False)[0]
    people = []
    counts = {name: 0 for name in zones.masks}
    boxes = result.boxes
    if boxes is not None:
        coordinates = boxes.xyxy.cpu().tolist()
        confidences = boxes.conf.cpu().tolist()
        ids = boxes.id.int().cpu().tolist() if boxes.id is not None else [None] * len(coordinates)
        for box, confidence, track_id in zip(coordinates, confidences, ids):
            table_id, overlap = zones.match(box, args.overlap)
            if table_id is not None:
                counts[table_id] += 1
            people.append({"track_id": track_id, "box": box, "confidence": round(confidence, 3),
                           "table_id": table_id, "overlap": round(overlap, 3)})
    return people, counts


def draw_frame(frame, zones, people, counts, frame_number, processing_fps, lifecycle=None):
    canvas = frame.copy()
    states = {table["id"]: table for table in lifecycle["tables"]} if lifecycle else {}
    for table in zones.tables:
        name = table["id"]
        color = (60, 60, 240) if counts[name] else (60, 210, 60)
        if name in states:
            color = {"occupied": (60, 60, 240), "free": (60, 210, 60),
                     "needs_cleaning": (0, 220, 255)}[states[name]["state"]]
        polygon = np.array(table["polygon"], np.int32)
        cv2.polylines(canvas, [polygon], True, color, 2)
        center = polygon.mean(axis=0).astype(int)
        label = f'{name.replace("table_", "T")}: {counts[name]}'
        if name in states:
            status = states[name]
            short_state = {"occupied": "OCC", "free": "FREE", "needs_cleaning": "CLEAN?"}[status["state"]]
            label = f'{name.replace("table_", "T")} {short_state} {int(status["state_elapsed_seconds"])}s'
        cv2.putText(canvas, label, tuple(center), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4)
        cv2.putText(canvas, label, tuple(center), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    for person in people:
        x1, y1, x2, y2 = map(int, person["box"])
        color = (255, 210, 40)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        identity = person["track_id"] if person["track_id"] is not None else "?"
        label = f'P{identity} {person["confidence"]:.0%}'
        cv2.putText(canvas, label, (max(0, x1), max(18, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
        cv2.putText(canvas, label, (max(0, x1), max(18, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    scale = min(1200 / canvas.shape[1], 650 / canvas.shape[0], 1.0)
    canvas = cv2.resize(canvas, (round(canvas.shape[1] * scale), round(canvas.shape[0] * scale)))
    height, width = canvas.shape[:2]
    canvas = cv2.copyMakeBorder(canvas, 0, 80, 0, max(0, 960 - width), cv2.BORDER_CONSTANT, value=(25, 25, 25))
    lines = [
        "Red: person overlap | Green: no match this frame | Cyan: detected person",
        f"Frame {frame_number} | People: {len(people)} | Processing: {processing_fps:.1f} fps | Space: pause | Q: quit",
        "Phase 2 observations only: no staff recognition, cleaning state or alerts yet.",
    ]
    if lifecycle:
        lines[0] = "Red: occupied | Green: free estimate | Yellow: needs cleaning | Cyan: detected person"
        lines[2] = "Phase 3: timers + SQLite + API | Staff roles require manual labels/confirmation | Q: quit"
    for i, line in enumerate(lines):
        cv2.putText(canvas, line, (10, height + 20 + i * 25), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (240, 240, 240), 1)
    return canvas


def wait_for_key(delay):
    key = cv2.waitKey(delay) & 0xFF
    if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1 or key in (ord("q"), 27):
        return False
    if key == ord(" "):
        print("Paused. Press Space to resume or Q to quit.", flush=True)
        while True:
            key = cv2.waitKey(50) & 0xFF
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1 or key in (ord("q"), 27):
                return False
            if key == ord(" "):
                break
    return True


def run(args):
    capture, is_stream = open_video(args.source)
    frames = 0
    canvas = None
    user_quit = False
    state_client = None
    stop_reason = "disconnected"
    try:
        ok, frame = capture.read()
        if not ok:
            raise ValueError("The source opened but supplied no video image.")
        zones = TableZones(args.zones, frame.shape)
        # Keep model/config/cache files inside this project.
        runtime = ROOT / ".runtime"
        runtime.mkdir(exist_ok=True)
        for name in ("ultralytics", "matplotlib", "cache"):
            (runtime / name).mkdir(exist_ok=True)
        os.environ.setdefault("YOLO_CONFIG_DIR", str(runtime / "ultralytics"))
        os.environ.setdefault("MPLCONFIGDIR", str(runtime / "matplotlib"))
        os.environ.setdefault("XDG_CACHE_HOME", str(runtime / "cache"))
        os.environ.setdefault("YOLO_AUTOINSTALL", "false")
        from ultralytics import YOLO
        args.model.parent.mkdir(parents=True, exist_ok=True)
        print("Loading YOLO. The first run may download the model weights (the AI's learned parameters).", flush=True)
        model = YOLO(str(args.model))
        if model.names.get(0) != "person":
            raise ValueError("Choose a COCO detection model with person as class 0, such as yolo26n.pt.")
        fps = capture.get(cv2.CAP_PROP_FPS)
        fps = fps if math.isfinite(fps) and fps > 0 else 25.0
        expected_frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        matched_frames = {name: 0 for name in zones.masks}
        peak_people = 0
        print(f"Loaded {len(zones.tables)} zones. Starting person detection on {args.device}.", flush=True)
        if args.api:
            from state_client import StateClient
            state_client = StateClient(args.api)
            state_client.start("live" if is_stream else "video", args.greet_after, zones)
            print(f"Phase 3 connected. Run: {state_client.run_id}; greeting threshold: {args.greet_after}s.", flush=True)
        if not args.headless:
            cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
        while True:
            started = time.perf_counter()
            if frame.shape[:2] != (zones.height, zones.width):
                raise ValueError("Video resolution changed during playback. Remap before continuing.")
            people, counts = detect_frame(model, frame, zones, args)
            frames += 1
            if state_client:
                # Recorded video uses its own timeline, so slow inference cannot stretch timers.
                state_client.observe(frames, (frames - 1) / fps if not is_stream else None, people)
            peak_people = max(peak_people, len(people))
            for name, count in counts.items():
                matched_frames[name] += int(count > 0)
            elapsed = time.perf_counter() - started
            canvas = draw_frame(frame, zones, people, counts, frames, 1 / max(elapsed, 1e-6),
                                state_client.snapshot if state_client else None)
            if frames == 1 or frames % 30 == 0:
                print(f"Frame {frames}: {len(people)} people; {sum(c > 0 for c in counts.values())} zones with matches.", flush=True)
            if not args.headless:
                cv2.imshow(WINDOW, canvas)
                delay = 1 if is_stream else max(1, round(1000 / fps - (time.perf_counter() - started) * 1000))
                if not wait_for_key(delay):
                    user_quit = True
                    stop_reason = "stopped"
                    break
            if args.max_frames and frames >= args.max_frames:
                stop_reason = "stopped"
                break
            ok, frame = capture.read()
            if not ok:
                if is_stream:
                    raise ValueError("Camera feed stopped. Check its connection and restart; an unreadable frame is not an empty table.")
                if math.isfinite(expected_frames) and expected_frames > 0 and frames < expected_frames - 1:
                    raise ValueError("Video decoding stopped before the expected end. Try re-exporting the video as MP4.")
                print("Video finished.", flush=True)
                stop_reason = "completed"
                break
        if state_client:
            # Freeze video timers at EOF, before keeping the preview window open.
            state_client.stop(stop_reason)
        if args.snapshot and canvas is not None:
            args.snapshot.parent.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(args.snapshot), canvas):
                raise ValueError("Could not save the preview image. Use a .jpg or .png filename.")
            print(f"Preview saved: {args.snapshot}", flush=True)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps({
                "frames_processed": frames, "peak_people_in_one_frame": peak_people,
                "frames_with_person_match": matched_frames,
                "last_frame": {"counts": counts, "people": people},
                "note": "Raw overlap observations, not confirmed occupancy or unique visitor counts.",
            }, indent=2) + "\n", encoding="utf-8")
        if not args.headless and not user_quit and canvas is not None and cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) >= 1:
            # Let a beginner inspect the final frame instead of closing immediately.
            print("Preview complete. Press Q or close the window to exit.", flush=True)
            while wait_for_key(50):
                pass
    finally:
        capture.release()
        if state_client and state_client.run_id:
            try:
                state_client.stop(stop_reason)
            except RuntimeError as error:
                print(f"Could not report source stop: {error}", file=sys.stderr)
        if not args.headless:
            cv2.destroyAllWindows()
    print(f"Finished: {frames} frames processed.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=os.environ.get("CAMERA_SOURCE", str(ROOT / "data/videos/restaurant.mp4")))
    parser.add_argument("--zones", type=Path, default=ROOT / "data/zones/tables.json")
    parser.add_argument("--model", type=Path, default=ROOT / "models/yolo26n.pt",
                        help="Detection weights (default: YOLO26 nano, released by Ultralytics in January 2026).")
    parser.add_argument("--confidence", type=float, default=0.25, help="Minimum person confidence (default: 0.25, tuned for YOLO26).")
    parser.add_argument("--overlap", type=float, default=0.15, help="Minimum fraction of a person's box inside a zone.")
    parser.add_argument("--image-size", type=int, default=960,
                        help="YOLO inference size, a multiple of 32 (default: 960; 640 is faster but misses small or distant people).")
    parser.add_argument("--device", default="cpu", help="cpu (default), mps for Apple GPU, or a CUDA device index.")
    parser.add_argument("--headless", action="store_true", help="Process without opening a window.")
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after N frames; 0 means the entire source.")
    parser.add_argument("--snapshot", type=Path, help="Save the last annotated image (replaces existing output).")
    parser.add_argument("--report", type=Path, help="Save a JSON diagnostic summary (replaces existing output).")
    parser.add_argument("--api", help="Enable Phase 3, e.g. http://127.0.0.1:8000.")
    parser.add_argument("--greet-after", type=float, default=300, help="Ungreeted alert threshold in seconds (default: 300).")
    args = parser.parse_args()
    if not 0 < args.confidence <= 1 or not 0 < args.overlap <= 1:
        parser.error("--confidence and --overlap must be greater than zero and at most 1.")
    if args.max_frames < 0 or args.image_size < 32 or args.image_size % 32:
        parser.error("--max-frames must be nonnegative; --image-size must be a positive multiple of 32.")
    if not math.isfinite(args.greet_after) or not 0 < args.greet_after <= 86400:
        parser.error("--greet-after must be greater than zero and at most 86400 seconds.")
    try:
        run(args)
    except KeyboardInterrupt:
        print("Stopped by user.")
        return 130
    except ImportError:
        print("A detection package is missing. Activate .venv and run: python -m pip install -r requirements.txt", file=sys.stderr)
        return 1
    except (ValueError, OSError, RuntimeError, cv2.error) as error:
        print(f"Detection stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
