# Directory Visualizer for Creality Ender 3 (Board v1.1.4)

The following map shows the main components of this repository and how they
relate when flashing and configuring Klipper for an Ender 3 running the stock
Creality v1.1.4 controller board.

```
.
├── client.cfg                # Example configuration for Fluidd/Mainsail
├── fluidd/                   # Web UI assets
├── fluidd.cfg                # Base Klipper macro set
├── fluidd-moonraker-update.conf  # Update service
├── kiauh-backups/            # Backup configs from KIAUH helper
├── kiuah/                    # KIAUH helper scripts
├── klipper/                  # Klipper firmware source
│   ├── config/               # Example printer configs
│   ├── docs/                 # Documentation
│   ├── klippy/               # Firmware Python code
│   ├── ...
├── moonraker/                # Moonraker API server
│   ├── docs/
│   ├── moonraker/
│   └── ...
└── README.md
```

## Ender 3 Board Configuration

For the Creality Ender 3 with the 8‑bit v1.1.4 control board, reference the
configuration file located at:

```
klipper/config/printer-creality-ender3-2018.cfg
```

Compile Klipper for the `atmega1284p` MCU and use this configuration as a
starting point for your printer.

