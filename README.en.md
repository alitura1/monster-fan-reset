<p align="right"><a href="./README.md">Türkçe</a> | <strong>English</strong></p>

# Monster Fan Reset

An experimental, open-source Windows utility for briefly resetting fans on compatible Monster / Tongfang laptops without entering sleep mode.

It was created to clear an intermittent mechanical fan squeak by stopping and restarting the fan. The utility calls the laptop firmware's own WMI fan methods, then **always returns all fans to firmware automatic control**.

> [!WARNING]
> This software is hardware-specific and experimental. It is validated only on **Monster Abra A5 V21.1 (Tongfang GM5MU)**. Use it only while watching temperatures, on a cool and idle machine. It can temporarily stop a fan and may cause a short fan ramp-up. Do not use it while gaming, rendering, charging under load, or with an already hot CPU/GPU.

## What it does

- `CPU`: briefly stops the CPU fan while holding the GPU fan at full speed.
- `GPU`: briefly stops the GPU fan while holding the CPU fan at full speed.
- `Both`: briefly stops both primary fans.
- Reads EC temperature before and during the operation.
- Stops early when the configured temperature limit is reached.
- Returns every fan to automatic firmware control even if the script errors.

## Requirements

1. Windows 10/11, PowerShell, and Administrator access.
2. Python 3 available as `python` on `PATH`.
3. [PawnIO 2.2.0](https://github.com/namazso/PawnIO.Setup/releases/tag/2.2.0) installed.
4. `LpcACPIEC.bin` from [PawnIO.Modules](https://github.com/namazso/PawnIO.Modules/releases), placed next to `src/ec.py`. This binary is **not included**; follow its upstream licence.

## Installation

```powershell
git clone https://github.com/alitura1/monster-fan-reset.git
cd monster-fan-reset\src
Copy-Item FanReset.ini.example FanReset.ini
```

Then run one of these from an elevated PowerShell window:

```powershell
.\FanReset.ps1 -TargetFan CPU
.\FanReset.ps1 -TargetFan GPU
.\FanReset.ps1 -TargetFan Both
```

For a clickable launcher, install AutoHotkey v2 and run `FanReset.ahk` with `CPU`, `GPU`, or `Both` as its argument. A compiled executable is intentionally not distributed.

## Configuration

Edit `src/FanReset.ini` after copying the example:

- `HoldSeconds`: 1–10 seconds. Default: `4`.
- `TempAbort`: 60–95 °C. Default: `85`.
- `TargetFan`: `CPU`, `GPU`, or `Both` when no command-line target is passed.

The public version deliberately has no indefinite “fan off” mode and no setting above the fixed 10-second maximum.

## Exclusive manual-off mode

`FanManual.ps1` provides a separate, guarded manual mode for troubleshooting a single fan. It deliberately allows **only one primary fan** to be off at a time:

```powershell
.\FanManual.ps1 -Action CPUOff  # CPU off; GPU held at 100%
.\FanManual.ps1 -Action GPUOff  # switches CPU back on, then turns GPU off
.\FanManual.ps1 -Action Auto    # immediately returns all fans to firmware auto
```

The background monitor checks EC temperature twice per second. It returns all fans to automatic control if temperature cannot be read or reaches `TempAbort`. Switching from `CPUOff` to `GPUOff` first restores all fans to automatic control and only then applies the new state, so it will never intentionally keep both primary fans off.

The monitor is a safety component, not a replacement for normal cooling. Do not use manual-off mode while the laptop is under load.

## Fan mapping

On the validated device, the firmware maps duty byte 0 to the CPU fan and byte 1 to the GPU fan. The exact mapping may differ on other Tongfang models. If a target controls the wrong fan, stop testing and open an issue.

## Development notes

The `CLEVO_GET` WMI projection in `clevo_fan.mof` maps the firmware `WMBB` interface (GUID `ABBC0F6D-8EA1-11D1-00A0-C90629100000`) to three methods:

- `GetFan12RPM` — firmware method 112
- `SetFanDuty` — firmware method 104
- `SetFanAutoDuty` — firmware method 105

## Contributing

Bug reports, model compatibility reports, documentation fixes, and safer sensor backends are welcome. Do not submit logs containing usernames, serial numbers, or full local file paths.

## License

MIT. Third-party dependencies retain their own licences.
