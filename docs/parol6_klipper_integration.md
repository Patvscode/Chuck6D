# PAROL6 + Klipper Integration Plan

## 1. What the stock PAROL6 control stack looks like
- The upstream controller firmware targets a custom STM32F4 mainboard and directly drives six TMC5160 stepper drivers with SPI configuration and step/dir outputs for each joint, as shown by the firmware arrays below:
  ```cpp
  TMC5160Stepper driver[] = {TMC5160Stepper(SELECT1, R_SENSE), ...};
  AccelStepper stepper[] = {AccelStepper(stepper[0].DRIVER, PUL1, DIR1), ...};
  ```
  These arrays initialize six driver objects (`NUM` = 6) together with motion-planning state for joint homing, timing and gripper handling inside `setup()`. The boot sequence configures GPIO, SPI, ADC and then iterates through each joint to initialise the driver chips before enabling motion.  
- Motion commands are exchanged over a binary serial/CAN protocol: the firmware waits for three `0xFF` start bytes, a length byte and payload, then unpacks joint targets and gripper commands before executing staged homing and movement logic.  
- Homing is implemented as a multi-stage state machine (`joint123_stage*`, `J4_stage*`, etc.) that sequences joints in groups until all encoders or limit switches report success.

## 2. Target hardware topology with Raspberry Pi 5 + Ender-3 v1.1.4 board
- The Raspberry Pi 5 (8 GB) will host Klipper, Moonraker and a dashboard (Fluidd or Mainsail). The existing repository already carries a minimal Klipper configuration for the Creality Ender-3 v1.1.4 (ATmega1284P) board that trims out heaters and exposes simple jog macros via Fluidd.【F:final_ender3_robotic_arm/README.md†L1-L13】
- The reference `printer.cfg` keeps four built-in drivers (X/Y/Z/E), enables `force_move`, includes the Fluidd macro library, and defines convenience macros (`MOVE_X_POS`, etc.) that map to `_CLIENT_LINEAR_MOVE` so the dashboard can jog each axis.【F:final_ender3_robotic_arm/printer.cfg†L1-L72】【F:final_ender3_robotic_arm/printer.cfg†L74-L116】
- PAROL6 needs six joints, so two additional step/dir channels must be broken out. Options include:
  - Re-using the EXP1/EXP2 headers on the Ender board to expose spare MCU pins, then wiring them to external stepper drivers (e.g., TMC5160/TMC2209 breakout modules) with Klipper `stepper_*` sections configured for `virtual_sdcard`-style pins.
  - Using an off-the-shelf stepper expander (e.g., BigTreeTech Easy Driver, StepStick clones) fed by 5V/12V from the Ender board, while keeping signal ground shared. Each additional joint gets its own `[stepper_]` section in `printer.cfg` with dedicated `step_pin`, `dir_pin`, `enable_pin`, current limit and gear reduction values.
  - If higher-current drivers are desired, the Ender board can act purely as a USB step-generator by routing step/dir to external closed-loop drivers mounted near the arm.
- For power distribution, repurpose the Ender board’s 24V input for the arm’s PSU. Ensure the board’s onboard regulators can handle the Pi’s UART/USB interface and that emergency-stop circuitry cuts both motor power and the board’s `GLOBAL_ENABLE` equivalent.

## 3. Joint-to-driver mapping and feedback strategy
- Map joints logically so the heaviest axes use the quietest drivers. A recommended baseline is:
  | PAROL6 joint | Motor spec | Driver channel | Notes |
  | --- | --- | --- | --- |
  | J1 (base) | NEMA 17 high torque | `[stepper_x]` | Replace rotation distance with gear ratio from PAROL6 BOM.
  | J2 (shoulder) | NEMA 17 | `[stepper_y]` | Add external endstop if using mechanical limit switch.
  | J3 (elbow) | NEMA 17 | `[stepper_z]` | Configure soft limits to protect cable harness.
  | J4 (wrist roll) | NEMA 17 | `[extruder]` channel repurposed; disable extruder temperature checks.
  | J5 (wrist pitch) | External driver A | New `[stepper_a]` with custom pins on EXP header.
  | J6 (wrist yaw) | External driver B | New `[stepper_b]` with custom pins; share enable with J5 for simplicity.
- Each joint requires homing sensors. The stock firmware expects digital inputs similar to `Init_Digital_Inputs();` so define `[endstop]` or `virtual_endstop` macros in Klipper. Mechanical microswitches can be read through the Ender board’s endstop headers or additional MCU pins, using `pullup` and `invert` flags to match wiring.
- Torque control from the original firmware (via TMC5160 diagnostics) is unavailable on A4988-based Ender boards. To regain current sensing and stallguard features, prefer external smart drivers connected through UART/SPI and use Klipper’s `tmc5160` or `tmc2209` sections.

## 4. Klipper configuration roadmap
1. **Flash Klipper to the Ender board** using the ATmega1284P instructions and connect it to the Raspberry Pi over USB.
2. **Duplicate and extend** `final_ender3_robotic_arm/printer.cfg`:
   - Update `rotation_distance`, `gear_ratio`, `microsteps`, and `max_velocity` for each joint based on PAROL6 mechanical data.
   - Add `[stepper_a]` / `[stepper_b]` sections for the external drivers and wire `enable_pin` to a shared GPIO so both joints can be disabled quickly.
   - Define `[gcode_macro HOME_ALL_JOINTS]` that sequences homing similar to the firmware state machine: home J1-J3 together, then J4-J6, inserting `G4` delays where required.
   - Implement macros mirroring the upstream binary protocol commands (`SET_JOINT_POS`, `SET_GRIPPER`, etc.) so higher-level software only needs to send human-readable commands.
3. **Expose per-joint jog macros** similar to the existing `MOVE_*` helpers but using joint names (e.g., `MOVE_J1_POS`) and optionally wrapping `MANUAL_STEPPER` for fine increments.
4. **Configure safety**: add `idle_timeout`, `max_velocity`, `max_accel`, and joint-specific soft limits; wire an emergency-stop input to a Klipper `[input_shaper]` or `[gcode_button]` that triggers `M112`.
5. **Validate kinematics** by scripting a Python calibration routine that calls the macros through Moonraker’s HTTP API, logging encoder or limit switch feedback.

## 5. Python or C++ control layer around Klipper macros
- **Python path**: use the Moonraker HTTP or WebSocket API to issue macro commands from a control script. The existing Fluidd macros accept parameters (`AMOUNT`, `SPEED`), so design wrapper functions such as `move_joint(joint_id, angle_deg)` that translate to `printer.gcode.script` calls with the matching macro name and step size. Libraries like `python-socketio` or the official PAROL6 Python API can be adapted to talk to Moonraker instead of the custom serial protocol.
- **C++ path**: run a lightweight client on the Pi (or another machine) that opens the Klipper UNIX socket (`/tmp/printer`) and sends `SET_GCODE_VARIABLE` / `RUN_MACRO` commands. Reuse the upstream command scheduler, but replace the CAN/serial layer with socket messages. Wrap macro invocations in classes that mirror the original firmware commands (e.g., `HomeAll`, `PlanTrajectory`, `ControlGripper`).
- **Trajectory execution**: for smooth motion, precompute joint trajectories using the PAROL6 Python API or ROS MoveIt and stream them as timed Klipper macros (`SET_SERVO`, `MANUAL_STEPPER STEPPER=...` with `SET_SPEED`). Because Klipper is optimised for queued G-code, batch commands using `gcode_macro` loops or `respond` macros to keep buffers full.
- **Synchronization**: reuse the firmware’s tick-based watchdog concept by polling `printer.objects.query` for `motion_report` and implementing a keepalive macro (e.g., `_PING`) that the client must call periodically to keep motors enabled.

## 6. Next steps
1. Prototype the electrical breakout for joints 5 and 6, document the chosen pins and driver modules.
2. Extend `printer.cfg` with the new stepper sections and homing macros; validate motion manually via Fluidd buttons.
3. Port homing stages into Klipper macros or a Python state machine that sequences the macros.
4. Wrap the macros in a Python control layer, gradually replacing the original binary command set, and test with simulated trajectories before connecting the real arm.
5. Evaluate whether additional sensors (encoders, current sensing) are required for parity with the original controller; if so, integrate them through Klipper’s `[adc_temperature]`, `[ads1118]`, or secondary MCU support.
