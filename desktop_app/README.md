# Desktop Fluidd Replacement (Skeleton)

This directory contains a minimal prototype for a desktop application that can run on a Raspberry Pi and control Klipper/Moonraker printers. It is **not** a full replacement for Fluidd yet but demonstrates how to start a standalone GUI that communicates with the Moonraker API.

## Requirements

- Python 3.9+
- `requests` library for HTTP communication
- `tkinter` for the user interface (ships with most Python installations)

You can install dependencies on the Raspberry Pi with:

```bash
pip install -r requirements.txt
```

## Running

```bash
python3 main.py
```

The script launches a small desktop window and attempts to connect to Moonraker at `http://localhost:7125`. Adjust the URL in `main.py` if your Moonraker instance runs elsewhere.

## Notes

This is just a skeleton to show how a desktop UI might integrate with the Moonraker API. A full application would need additional panels, printer state handling, file management, and much more.
