# Ender-3 v1.1.4 Robotic Arm Configuration

This folder contains a trimmed configuration for using a Creality Ender-3
controller board (v1.1.4 / ATmega1284P) to drive the stepper motors of a
robotic arm via Klipper, Moonraker and Fluidd.

Files included:

- `printer.cfg` – base configuration with steppers, force-move enabled,
  Fluidd macros, and jog macros for each motor.
- `fluidd.cfg` – Fluidd's macro set referenced by `printer.cfg`.

The configuration omits heaters, bed screws and display sections but retains
all four stepper drivers. Fluidd exposes the `MOVE_*` macros as buttons so
each joint can be jogged forward or backward at adjustable speed.
