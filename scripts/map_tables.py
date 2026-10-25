"""Phase 1: click table seating zones on a frozen video frame and save JSON."""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
WINDOW = "Table mapper"


def read_frame(source, seconds=0):
    """Read one image, then release the video/camera connection."""
    is_stream = source.lower().startswith(("rtsp://", "rtsps://", "http://", "https://"))
    if not is_stream and not Path(source).is_file():
        raise ValueError("Video file not found. Check the path supplied with --source.")
    if is_stream and seconds:
        raise ValueError("--seconds is for saved videos. A live stream starts at its current frame.")
    if is_stream:
        # Supported by OpenCV's FFmpeg backend; bound network connection/read waits.
        capture = cv2.VideoCapture(source, cv2.CAP_FFMPEG, [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000,
        ])
    else:
        capture = cv2.VideoCapture(source)
    try:
        if not capture.isOpened():
            raise ValueError("Could not open the video. Check the file, or camera address, credentials and network.")
        if seconds and not capture.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000):
            raise ValueError("This video cannot seek to that time. Try without --seconds.")
        ok, frame = capture.read()
        if not ok or frame is None:
            raise ValueError("No image received. Try an earlier video time or check that the camera is streaming.")
        return frame
    finally:
        capture.release()


def orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(a, b, c, d):
    def on_segment(p, q, r):
        return (min(p[0], r[0]) <= q[0] <= max(p[0], r[0])
                and min(p[1], r[1]) <= q[1] <= max(p[1], r[1]))

    o1, o2 = orientation(a, b, c), orientation(a, b, d)
    o3, o4 = orientation(c, d, a), orientation(c, d, b)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True
    return ((o1 == 0 and on_segment(a, c, b)) or
            (o2 == 0 and on_segment(a, d, b)) or
            (o3 == 0 and on_segment(c, a, d)) or
            (o4 == 0 and on_segment(c, b, d)))


def validate_polygon(points):
    """Reject incomplete, flat, repeated, or crossing outlines."""
    count = len(points)
    if count < 3:
        raise ValueError("Click at least three corners before pressing N.")
    if len(set(map(tuple, points))) != count:
        raise ValueError("Two corners are identical. Use U to undo the last corner.")
    for i in range(count):
        previous, current, following = points[i - 1], points[i], points[(i + 1) % count]
        if orientation(previous, current, following) == 0:
            raise ValueError("Adjacent edges form a straight line. Undo and choose distinct corners.")
        for j in range(i + 1, count):
            if j == i + 1 or (i == 0 and j == count - 1):
                continue
            if segments_intersect(points[i], points[(i + 1) % count],
                                  points[j], points[(j + 1) % count]):
                raise ValueError("Edges cross. Click around the outside in clockwise or counterclockwise order.")
    if abs(cv2.contourArea(np.array(points, dtype=np.int32))) < 25:
        raise ValueError("This zone is too small. Draw around the whole seating area.")


def save_zones(output, tables, frame_size, camera_id, overwrite=False):
    """Write original pixel coordinates; never store camera URLs/passwords."""
    if not tables:
        raise ValueError("Finish at least one table with N before saving.")
    document = {
        "schema_version": 1,
        "camera_id": camera_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "frame_size": {"width": frame_size[0], "height": frame_size[1]},
        "coordinate_system": "original_frame_pixels",
        "tables": tables,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental replacement of an existing map.
    with output.open("w" if overwrite else "x", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
        handle.write("\n")


class TableMapper:
    def __init__(self, frame, max_width, max_height):
        self.height, self.width = frame.shape[:2]
        scale = min(max_width / self.width, max_height / self.height, 1.0)
        self.display_width = max(1, round(self.width * scale))
        self.display_height = max(1, round(self.height * scale))
        self.preview = cv2.resize(frame, (self.display_width, self.display_height))
        self.points = []
        self.tables = []
        self.message = "Click corners around the seating area, then press N."
        self.quit_requested = False

    def original_point(self, x, y):
        return [min(self.width - 1, round(x * self.width / self.display_width)),
                min(self.height - 1, round(y * self.height / self.display_height))]

    def display_point(self, point):
        return (round(point[0] * self.display_width / self.width),
                round(point[1] * self.display_height / self.height))

    def on_mouse(self, event, x, y, flags, param):
        if (event == cv2.EVENT_LBUTTONDOWN and
                0 <= x < self.display_width and 0 <= y < self.display_height):
            self.points.append(self.original_point(x, y))
            self.quit_requested = False
            self.message = f"{len(self.points)} corners selected. N finishes this table; U undoes a corner."

    def finish_table(self):
        validate_polygon(self.points)
        table_id = f"table_{len(self.tables) + 1}"
        self.tables.append({"id": table_id, "polygon": self.points.copy()})
        self.points.clear()
        self.message = f"Added {table_id}. Draw another table, or press S to save and exit."

    def render(self):
        canvas = self.preview.copy()
        # Blue is an annotation color, not a live occupancy status.
        for table in self.tables:
            points = np.array([self.display_point(p) for p in table["polygon"]], np.int32)
            cv2.polylines(canvas, [points], True, (255, 180, 40), 2)
            cv2.putText(canvas, table["id"], tuple(points[0]), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (255, 180, 40), 2)
        if self.points:
            points = np.array([self.display_point(p) for p in self.points], np.int32)
            cv2.polylines(canvas, [points], False, (255, 255, 255), 2)
            for point in points:
                cv2.circle(canvas, tuple(point), 4, (255, 255, 255), -1)
        # A separate footer keeps instructions from covering the camera image.
        canvas = cv2.copyMakeBorder(canvas, 0, 90, 0, max(0, 1000 - self.display_width),
                                    cv2.BORDER_CONSTANT, value=(25, 25, 25))
        for index, line in enumerate([
            "Click: corner | N: finish table | U: undo corner | C: clear draft | D: delete last table",
            "S: save and exit | Q/Esc: quit (press twice if unsaved) | Closing the window discards work",
            self.message,
        ]):
            cv2.putText(canvas, line, (10, self.display_height + 23 + index * 27),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (240, 240, 240), 1)
        return canvas

    def run(self, output, camera_id, overwrite):
        cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(WINDOW, self.on_mouse)
        try:
            while True:
                cv2.imshow(WINDOW, self.render())
                key = cv2.waitKey(30) & 0xFF
                if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    print("Window closed. No changes saved.")
                    return
                if key == 255:
                    continue
                if key in (ord("q"), 27):
                    if (self.points or self.tables) and not self.quit_requested:
                        self.message = "Unsaved work! Press Q again to discard, or S to save."
                        self.quit_requested = True
                        continue
                    print("Exited without saving.")
                    return
                self.quit_requested = False
                try:
                    if key == ord("n"):
                        self.finish_table()
                    elif key == ord("u") and self.points:
                        self.points.pop()
                        self.message = "Removed the last corner."
                    elif key == ord("c"):
                        self.points.clear()
                        self.message = "Cleared unfinished outline."
                    elif key == ord("d") and self.tables:
                        self.tables.pop()
                        self.message = "Deleted the last completed table."
                    elif key == ord("s"):
                        if self.points:
                            raise ValueError("Finish the current outline with N, or clear it with C, before saving.")
                        save_zones(output, self.tables, (self.width, self.height), camera_id, overwrite)
                        print(f"Saved {len(self.tables)} table zones to {output}")
                        return
                except (ValueError, OSError) as error:
                    self.message = ("Output already exists. Choose another --output, or restart with --overwrite."
                                    if isinstance(error, FileExistsError) else str(error))
                    print(self.message)
        finally:
            cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=os.environ.get("CAMERA_SOURCE"),
                        help="Video path or RTSP/HTTP stream URL; defaults to CAMERA_SOURCE.")
    parser.add_argument("--seconds", type=float, default=0, help="Time within a saved video (default: 0).")
    parser.add_argument("--output", type=Path, default=ROOT / "data/zones/tables.json")
    parser.add_argument("--camera-id", default="dining-room")
    parser.add_argument("--max-width", type=int, default=1200)
    parser.add_argument("--max-height", type=int, default=650)
    parser.add_argument("--overwrite", action="store_true", help="Explicitly replace an existing output file.")
    args = parser.parse_args()
    if not args.source:
        parser.error("Supply --source or set CAMERA_SOURCE to a video path or camera URL.")
    if not math.isfinite(args.seconds) or args.seconds < 0:
        parser.error("--seconds must be a finite number of zero or greater.")
    if args.max_width < 1 or args.max_height < 1:
        parser.error("Preview width and height must be positive.")
    if args.output.exists() and not args.overwrite:
        parser.error("Output already exists. Choose a new --output, or use --overwrite to replace it.")
    try:
        frame = read_frame(args.source, args.seconds)
        TableMapper(frame, args.max_width, args.max_height).run(args.output, args.camera_id, args.overwrite)
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except cv2.error:
        print("OpenCV could not read the video or open a desktop window. Use a local desktop terminal "
              "and the opencv-python package; see README.md for troubleshooting.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Stopped. No new map saved.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
