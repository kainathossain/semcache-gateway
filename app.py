"""Deployable entry point (e.g. Render): seeds the gateway with simulated traffic,
then serves the dashboard on 0.0.0.0:$PORT.  Start command:  python app.py"""
import os

from dashboard import serve
from demo import make_workload
from gateway import Gateway


def main():
    gw = Gateway()
    for q in make_workload(int(os.environ.get("DEMO_REQUESTS", "1500"))):
        gw.ask(q)
    port = int(os.environ.get("PORT", "8765"))  # Render sets PORT
    serve(gw.metrics, port=port, host="0.0.0.0")


if __name__ == "__main__":
    main()