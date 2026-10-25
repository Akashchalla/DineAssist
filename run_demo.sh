#!/usr/bin/env bash
# One-command demo: starts the API and dashboard, opens the dashboard in your
# browser, then replays the video with the detector window.
#
#   bash run_demo.sh                      # sample video with a 5-second greeting deadline
#   bash run_demo.sh --image-size 640     # any detect_people.py options replace the default
#
# Quit the detector window with Q, then press Ctrl+C here to stop the servers.

cd "$(dirname "$0")" || exit 1
if [ ! -f .venv/bin/activate ]; then
    echo "No .venv found. Follow 'Start here: prepare Python' in README.md first."
    exit 1
fi
source .venv/bin/activate

for port in 8000 8501; do
    if curl -s -o /dev/null "http://127.0.0.1:$port"; then
        echo "Port $port is already in use. Stop the other API/dashboard (Ctrl+C in its terminal) and retry."
        exit 1
    fi
done

cleanup() {
    echo
    echo "Stopping the API and dashboard..."
    kill "$API_PID" "$DASH_PID" 2>/dev/null
    wait 2>/dev/null
}
trap cleanup EXIT
trap 'exit 130' INT TERM

python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log &
API_PID=$!
streamlit run dashboard/app.py &
DASH_PID=$!

echo "Waiting for the API and dashboard to start..."
ready=""
for _ in $(seq 1 60); do
    if curl -fs -o /dev/null http://127.0.0.1:8000/health && curl -fs -o /dev/null http://127.0.0.1:8501; then
        ready=yes
        break
    fi
    sleep 1
done
if [ -z "$ready" ]; then
    echo "The API or dashboard did not start within 60 seconds. See the messages above."
    exit 1
fi

echo "Dashboard: http://127.0.0.1:8501"
if command -v open > /dev/null; then
    open http://127.0.0.1:8501
fi

if [ $# -eq 0 ]; then
    set -- --greet-after 5
fi
python scripts/detect_people.py --api http://127.0.0.1:8000 "$@" \
    || echo "The detector stopped with an error (see above). The dashboard shows the last saved states."

echo
echo "Detector finished. The dashboard stays available at http://127.0.0.1:8501"
echo "Press Ctrl+C to stop the API and dashboard."
wait
