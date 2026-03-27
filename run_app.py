from __future__ import annotations

import sys

from streamlit.web import cli as stcli


if __name__ == "__main__":
    # Launch Streamlit app with sensible defaults for local desktop use.
    sys.argv = [
        "streamlit",
        "run",
        "app.py",
        "--server.headless=false",
        "--server.port=8501",
        "--browser.gatherUsageStats=false",
    ]
    raise SystemExit(stcli.main())
