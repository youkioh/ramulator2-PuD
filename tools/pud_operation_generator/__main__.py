"""Generate and exhaustively verify standalone PuD arithmetic traces."""

import argparse
import json
from pathlib import Path
import sys

from .artifacts import PROFILES, write_program
from .fp8 import build_e4m3_add, build_e4m3_mul, build_e5m2_add, build_e5m2_mul
from .integer import build_int8_add, build_int8_mul, build_uint8_add, build_uint8_mul
from .validation import verify


BUILDERS = {
    "uint8-add": build_uint8_add,
    "uint8-mul": build_uint8_mul,
    "int8-add": build_int8_add,
    "int8-mul": build_int8_mul,
    "fp8-e5m2-add": build_e5m2_add,
    "fp8-e5m2-mul": build_e5m2_mul,
    "fp8-e4m3-add": build_e4m3_add,
    "fp8-e4m3-mul": build_e4m3_mul,
}


def build(name):
    """Build one of the eight supported operation profiles."""
    return BUILDERS[name]()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=Path("build/pud-operation-generator")
    )
    parser.add_argument(
        "--only",
        nargs="+",
        choices=list(PROFILES),
        help="generate only the selected profiles",
    )
    parser.add_argument(
        "--library-check",
        action="store_true",
        help="also compare with NumPy and ml_dtypes",
    )
    args = parser.parse_args()

    if not __debug__:
        parser.error("validation requires assertions; do not run with -O")

    versions = {"python": sys.version.split()[0]}
    if args.library_check:
        try:
            import ml_dtypes
            import numpy
        except ImportError:
            parser.error(
                "--library-check requires numpy and ml_dtypes; "
                "see requirements-check.txt"
            )
        versions.update(numpy=numpy.__version__, ml_dtypes=ml_dtypes.__version__)

    report = {
        "schema_version": 1,
        "versions": versions,
        "library_check": args.library_check,
        "scope": "Symbolic functional validation; FP8 profile contracts apply.",
        "variants": {},
    }
    for name in dict.fromkeys(args.only or PROFILES):
        program = build(name)
        path, info = write_program(name, program, args.out)
        validation = verify(name, program, path, info, args.library_check)
        report["variants"][name] = {
            "contract": info["contract"],
            "cost": info["cost"],
            "validation": validation,
        }
        print(
            f"{name}: {len(program.trace)} primitives, "
            f"{validation['pairs']:,} pairs, reference/replay PASS",
            flush=True,
        )

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "validation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
