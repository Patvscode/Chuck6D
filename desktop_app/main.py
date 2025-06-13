#!/usr/bin/env python3
"""Minimal desktop interface for Moonraker printers.

This script demonstrates how to build a Tkinter-based GUI that connects
to the Moonraker API. It is a starting point and not a full-featured
Fluidd replacement.
"""
import tkinter as tk
from tkinter import messagebox
import requests

MOONRAKER_URL = "http://localhost:7125"


def fetch_printer_info():
    """Fetch basic printer info from Moonraker."""
    try:
        response = requests.get(f"{MOONRAKER_URL}/printer/info")
        response.raise_for_status()
        data = response.json()
        return data.get("result", {})
    except Exception as exc:
        messagebox.showerror("Connection Error", str(exc))
        return None


def on_refresh():
    info = fetch_printer_info()
    if info:
        text = "Printer Info:\n" + "\n".join(f"{k}: {v}" for k, v in info.items())
        info_label.config(text=text)
    else:
        info_label.config(text="Failed to fetch printer info")


root = tk.Tk()
root.title("Desktop Fluidd (Prototype)")

refresh_button = tk.Button(root, text="Refresh Printer Info", command=on_refresh)
refresh_button.pack(pady=10)

info_label = tk.Label(root, text="Click refresh to fetch printer info", justify="left")
info_label.pack(padx=10, pady=10)

root.mainloop()
