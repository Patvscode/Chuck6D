#!/usr/bin/env python3
"""Desktop commander-style interface for ARA6D robot control.

This UI targets Moonraker/Klipper backends and optional AS5600 encoder feedback.
It provides joint/cart jogging, quick macros, and a configurable G-code bridge.
"""
from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk
from typing import Any

import requests
import serial

CONFIG_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "moonraker_url": "http://localhost:7125",
    "joint_step_deg": 1.0,
    "cart_step_mm": 1.0,
    "rot_step_deg": 1.0,
    "joint_feedrate": 1000,
    "cart_feedrate": 1000,
    "joint_jog_gcode": "JOINT_JOG J={joint} D={delta} F={feedrate}",
    "cart_jog_gcode": "CART_JOG X={x} Y={y} Z={z} RX={rx} RY={ry} RZ={rz} F={feedrate}",
    "enable_gcode": "ROBOT_ENABLE",
    "disable_gcode": "ROBOT_DISABLE",
    "home_gcode": "ROBOT_HOME",
    "estop_gcode": "M112",
    "encoder_port": "",
    "encoder_baud": 115200,
}


def load_config() -> dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    merged = DEFAULT_CONFIG.copy()
    merged.update(data)
    return merged


def save_config(config: dict[str, Any]) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, sort_keys=True)


@dataclass
class MoonrakerClient:
    base_url: str
    timeout_s: float = 3.0

    def get_printer_info(self) -> dict[str, Any]:
        response = requests.get(
            f"{self.base_url}/printer/info",
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        return response.json().get("result", {})

    def send_gcode(self, script: str) -> None:
        response = requests.post(
            f"{self.base_url}/printer/gcode/script",
            json={"script": script},
            timeout=self.timeout_s,
        )
        response.raise_for_status()


class EncoderReader(threading.Thread):
    def __init__(self, port: str, baud: int, output_queue: queue.Queue[dict[str, float]]):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.output_queue = output_queue
        self.stop_event = threading.Event()

    def run(self) -> None:
        try:
            with serial.Serial(self.port, self.baud, timeout=1) as serial_port:
                while not self.stop_event.is_set():
                    line = serial_port.readline().decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue
                    parsed = self.parse_line(line)
                    if parsed:
                        self.output_queue.put(parsed)
        except Exception:
            return

    def stop(self) -> None:
        self.stop_event.set()

    @staticmethod
    def parse_line(line: str) -> dict[str, float]:
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                return {str(key).upper(): float(value) for key, value in data.items()}
            except Exception:
                return {}
        matches = re.findall(r"([A-Za-z]\d+)\s*[:=]\s*([-+]?\d*\.?\d+)", line)
        parsed: dict[str, float] = {}
        for key, value in matches:
            try:
                parsed[key.upper()] = float(value)
            except ValueError:
                continue
        return parsed


class CommanderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ARA6D Commander UI")
        self.geometry("1200x800")
        self.config_data = load_config()
        self.client = MoonrakerClient(self.config_data["moonraker_url"])
        self.last_status = tk.StringVar(value="Disconnected")
        self.last_command = tk.StringVar(value="No command sent yet")
        self.encoder_values = {f"J{i}": tk.StringVar(value="--") for i in range(1, 7)}
        self.encoder_queue: queue.Queue[dict[str, float]] = queue.Queue()
        self.encoder_reader: EncoderReader | None = None
        self._build_ui()
        self._poll_status()
        self._poll_encoders()

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=10)
        header.pack(fill="x")

        ttk.Label(header, text="Moonraker URL:").pack(side="left")
        self.moonraker_entry = ttk.Entry(header, width=40)
        self.moonraker_entry.insert(0, self.config_data["moonraker_url"])
        self.moonraker_entry.pack(side="left", padx=5)
        ttk.Button(header, text="Connect", command=self._connect).pack(side="left")
        ttk.Label(header, textvariable=self.last_status).pack(side="left", padx=10)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        move_tab = ttk.Frame(notebook, padding=10)
        io_tab = ttk.Frame(notebook, padding=10)
        settings_tab = ttk.Frame(notebook, padding=10)
        notebook.add(move_tab, text="Move")
        notebook.add(io_tab, text="I/O & Macros")
        notebook.add(settings_tab, text="Settings")

        self._build_move_tab(move_tab)
        self._build_io_tab(io_tab)
        self._build_settings_tab(settings_tab)

        footer = ttk.Frame(self, padding=10)
        footer.pack(fill="x")
        ttk.Label(footer, text="Last command:").pack(side="left")
        ttk.Label(footer, textvariable=self.last_command).pack(side="left", padx=8)

    def _build_move_tab(self, parent: ttk.Frame) -> None:
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill="x")

        step_frame = ttk.LabelFrame(control_frame, text="Jog Steps", padding=10)
        step_frame.pack(side="left", padx=10, fill="y")

        self.joint_step_var = tk.DoubleVar(value=self.config_data["joint_step_deg"])
        self.cart_step_var = tk.DoubleVar(value=self.config_data["cart_step_mm"])
        self.rot_step_var = tk.DoubleVar(value=self.config_data["rot_step_deg"])
        self.joint_feed_var = tk.DoubleVar(value=self.config_data["joint_feedrate"])
        self.cart_feed_var = tk.DoubleVar(value=self.config_data["cart_feedrate"])

        self._labeled_entry(step_frame, "Joint step (deg)", self.joint_step_var)
        self._labeled_entry(step_frame, "Cart step (mm)", self.cart_step_var)
        self._labeled_entry(step_frame, "Rot step (deg)", self.rot_step_var)
        self._labeled_entry(step_frame, "Joint feedrate", self.joint_feed_var)
        self._labeled_entry(step_frame, "Cart feedrate", self.cart_feed_var)

        jog_frame = ttk.Frame(control_frame)
        jog_frame.pack(side="left", fill="both", expand=True)

        joint_frame = ttk.LabelFrame(jog_frame, text="Joint Jog", padding=10)
        joint_frame.pack(fill="x", pady=5)

        for idx in range(1, 7):
            row = ttk.Frame(joint_frame)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=f"Joint {idx}").pack(side="left", padx=5)
            ttk.Button(row, text="-", command=lambda j=idx: self._jog_joint(j, -1)).pack(
                side="left"
            )
            ttk.Button(row, text="+", command=lambda j=idx: self._jog_joint(j, 1)).pack(
                side="left", padx=5
            )

        cart_frame = ttk.LabelFrame(jog_frame, text="Cartesian Jog", padding=10)
        cart_frame.pack(fill="x", pady=5)

        for axis in ("X", "Y", "Z"):
            self._cart_button_row(cart_frame, axis, "mm")
        for axis in ("RX", "RY", "RZ"):
            self._cart_button_row(cart_frame, axis, "deg")

        sensor_frame = ttk.LabelFrame(parent, text="Encoder Feedback", padding=10)
        sensor_frame.pack(fill="x", pady=10)
        for idx in range(1, 7):
            label = ttk.Label(sensor_frame, text=f"J{idx}:")
            value = ttk.Label(sensor_frame, textvariable=self.encoder_values[f"J{idx}"])
            label.grid(row=0, column=(idx - 1) * 2, padx=5)
            value.grid(row=0, column=(idx - 1) * 2 + 1, padx=5)

    def _build_io_tab(self, parent: ttk.Frame) -> None:
        macro_frame = ttk.LabelFrame(parent, text="Quick Macros", padding=10)
        macro_frame.pack(fill="x", pady=5)

        ttk.Button(macro_frame, text="Enable", command=lambda: self._send_macro("enable_gcode")).pack(
            side="left", padx=5
        )
        ttk.Button(macro_frame, text="Disable", command=lambda: self._send_macro("disable_gcode")).pack(
            side="left", padx=5
        )
        ttk.Button(macro_frame, text="Home", command=lambda: self._send_macro("home_gcode")).pack(
            side="left", padx=5
        )
        ttk.Button(macro_frame, text="E-Stop", command=lambda: self._send_macro("estop_gcode")).pack(
            side="left", padx=5
        )

        custom_frame = ttk.LabelFrame(parent, text="Custom G-code", padding=10)
        custom_frame.pack(fill="x", pady=10)

        self.custom_gcode_entry = ttk.Entry(custom_frame, width=80)
        self.custom_gcode_entry.pack(side="left", padx=5)
        ttk.Button(custom_frame, text="Send", command=self._send_custom).pack(side="left")

    def _build_settings_tab(self, parent: ttk.Frame) -> None:
        settings_frame = ttk.Frame(parent)
        settings_frame.pack(fill="both", expand=True)

        self.joint_template_var = tk.StringVar(value=self.config_data["joint_jog_gcode"])
        self.cart_template_var = tk.StringVar(value=self.config_data["cart_jog_gcode"])
        self.enable_macro_var = tk.StringVar(value=self.config_data["enable_gcode"])
        self.disable_macro_var = tk.StringVar(value=self.config_data["disable_gcode"])
        self.home_macro_var = tk.StringVar(value=self.config_data["home_gcode"])
        self.estop_macro_var = tk.StringVar(value=self.config_data["estop_gcode"])
        self.encoder_port_var = tk.StringVar(value=self.config_data["encoder_port"])
        self.encoder_baud_var = tk.IntVar(value=self.config_data["encoder_baud"])

        self._labeled_entry(settings_frame, "Joint jog template", self.joint_template_var, width=80)
        self._labeled_entry(settings_frame, "Cartesian jog template", self.cart_template_var, width=80)
        self._labeled_entry(settings_frame, "Enable macro", self.enable_macro_var, width=80)
        self._labeled_entry(settings_frame, "Disable macro", self.disable_macro_var, width=80)
        self._labeled_entry(settings_frame, "Home macro", self.home_macro_var, width=80)
        self._labeled_entry(settings_frame, "E-Stop macro", self.estop_macro_var, width=80)
        self._labeled_entry(settings_frame, "Encoder serial port", self.encoder_port_var, width=40)
        self._labeled_entry(settings_frame, "Encoder baud", self.encoder_baud_var, width=20)

        button_frame = ttk.Frame(settings_frame)
        button_frame.pack(fill="x", pady=10)
        ttk.Button(button_frame, text="Save Settings", command=self._save_settings).pack(
            side="left", padx=5
        )
        ttk.Button(button_frame, text="Reconnect Encoders", command=self._restart_encoders).pack(
            side="left", padx=5
        )

    @staticmethod
    def _labeled_entry(parent: ttk.Frame, label: str, variable: tk.Variable, width: int = 20) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        ttk.Entry(row, textvariable=variable, width=width).pack(side="left", padx=5)

    def _cart_button_row(self, parent: ttk.Frame, axis: str, unit: str) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=f"{axis} ({unit})").pack(side="left", padx=5)
        ttk.Button(row, text="-", command=lambda a=axis: self._jog_cart(a, -1)).pack(side="left")
        ttk.Button(row, text="+", command=lambda a=axis: self._jog_cart(a, 1)).pack(
            side="left", padx=5
        )

    def _connect(self) -> None:
        self.config_data["moonraker_url"] = self.moonraker_entry.get().strip()
        self.client = MoonrakerClient(self.config_data["moonraker_url"])
        self._poll_status(force=True)

    def _send_macro(self, key: str) -> None:
        script = self.config_data.get(key, "")
        if not script:
            messagebox.showwarning("Missing Macro", f"No macro configured for {key}.")
            return
        self._send_gcode(script)

    def _send_custom(self) -> None:
        script = self.custom_gcode_entry.get().strip()
        if not script:
            return
        self._send_gcode(script)

    def _send_gcode(self, script: str) -> None:
        try:
            self.client.send_gcode(script)
            self.last_command.set(script)
        except Exception as exc:
            messagebox.showerror("G-code Error", str(exc))

    def _jog_joint(self, joint: int, direction: int) -> None:
        step = self.joint_step_var.get() * direction
        feedrate = self.joint_feed_var.get()
        template = self.joint_template_var.get()
        try:
            script = template.format(joint=joint, delta=step, feedrate=feedrate)
        except KeyError as exc:
            messagebox.showerror("Template Error", f"Missing placeholder {exc} in joint template.")
            return
        self._send_gcode(script)

    def _jog_cart(self, axis: str, direction: int) -> None:
        axis = axis.upper()
        step_mm = self.cart_step_var.get() * direction
        step_deg = self.rot_step_var.get() * direction
        feedrate = self.cart_feed_var.get()
        data = {"x": 0, "y": 0, "z": 0, "rx": 0, "ry": 0, "rz": 0, "feedrate": feedrate}
        if axis in ("X", "Y", "Z"):
            data[axis.lower()] = step_mm
        else:
            data[axis.lower()] = step_deg
        template = self.cart_template_var.get()
        try:
            script = template.format(**data)
        except KeyError as exc:
            messagebox.showerror("Template Error", f"Missing placeholder {exc} in cart template.")
            return
        self._send_gcode(script)

    def _poll_status(self, force: bool = False) -> None:
        try:
            info = self.client.get_printer_info()
            state = info.get("state", "unknown")
            self.last_status.set(f"Connected ({state})")
        except Exception:
            if force:
                messagebox.showwarning("Connection", "Unable to connect to Moonraker.")
            self.last_status.set("Disconnected")
        self.after(2000, self._poll_status)

    def _poll_encoders(self) -> None:
        updated = False
        while not self.encoder_queue.empty():
            payload = self.encoder_queue.get()
            for key, value in payload.items():
                key_upper = key.upper()
                if key_upper in self.encoder_values:
                    self.encoder_values[key_upper].set(f"{value:.2f}")
                    updated = True
        if updated:
            self.last_command.set("Encoder update received")
        self.after(200, self._poll_encoders)

    def _restart_encoders(self) -> None:
        if self.encoder_reader:
            self.encoder_reader.stop()
            self.encoder_reader = None
        port = self.encoder_port_var.get().strip()
        if not port:
            return
        baud = self.encoder_baud_var.get()
        self.encoder_reader = EncoderReader(port, baud, self.encoder_queue)
        self.encoder_reader.start()

    def _save_settings(self) -> None:
        self.config_data.update(
            {
                "moonraker_url": self.moonraker_entry.get().strip(),
                "joint_step_deg": self.joint_step_var.get(),
                "cart_step_mm": self.cart_step_var.get(),
                "rot_step_deg": self.rot_step_var.get(),
                "joint_feedrate": self.joint_feed_var.get(),
                "cart_feedrate": self.cart_feed_var.get(),
                "joint_jog_gcode": self.joint_template_var.get(),
                "cart_jog_gcode": self.cart_template_var.get(),
                "enable_gcode": self.enable_macro_var.get(),
                "disable_gcode": self.disable_macro_var.get(),
                "home_gcode": self.home_macro_var.get(),
                "estop_gcode": self.estop_macro_var.get(),
                "encoder_port": self.encoder_port_var.get(),
                "encoder_baud": self.encoder_baud_var.get(),
            }
        )
        save_config(self.config_data)
        self._restart_encoders()
        messagebox.showinfo("Settings", "Settings saved.")


if __name__ == "__main__":
    app = CommanderApp()
    app.mainloop()
