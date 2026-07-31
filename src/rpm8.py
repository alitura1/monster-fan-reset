#!/usr/bin/env python3
"""Read-only EC temperature helper for Monster Fan Reset.

Requires PawnIO and the separately downloaded LpcACPIEC.bin module.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ec as ECMOD


def main() -> None:
    ec = ECMOD.EC()
    try:
        temperature = ec.ec_read8(0x07)
        print(f"TEMP={temperature}")
    finally:
        ec.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"TEMP=ERR ({exc})")
