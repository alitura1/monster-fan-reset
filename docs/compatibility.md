# Compatibility

| Device | Status | Notes |
| --- | --- | --- |
| Monster Abra A5 V21.1 | Validated | Tongfang GM5MU, Insyde BIOS, i5-12450H + RTX 3050 Laptop GPU |
| Other Monster / Abra / Tulpar models | Unknown | Do not assume compatibility solely from the brand. Test read-only temperature access first. |
| Clevo / Tongfang barebones | Possible | Only if the firmware exposes the same `ABBC0F6D` WMI/WMBB interface. |

Please open an issue with the Windows model name, BIOS vendor/version, fan behavior, and whether `GetFan12RPM` works. Never post serial numbers, Windows usernames, or log files containing personal paths.
