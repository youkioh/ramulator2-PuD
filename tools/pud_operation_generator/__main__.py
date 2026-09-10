"""Generate and exhaustively verify standalone PuD arithmetic traces."""

import argparse
import json
from pathlib import Path
import sys

from .artifacts import (
    PROFILES,
    write_default_physical_layout,
    write_physical_program,
    write_program,
)
from .fp8 import build_e4m3_add, build_e4m3_mul, build_e5m2_add, build_e5m2_mul
from .integer import build_int8_add, build_int8_mul, build_uint8_add, build_uint8_mul
from .lowering import (
    PhysicalLoweringError,
    PhysicalRowLayout,
    lower_to_physical,
    make_default_physical_layout,
)
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


def _load_physical_layouts(path, selected, parser):
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        parser.error(f"--physical-layout {path}: {error}")
    if not isinstance(document, dict):
        parser.error("--physical-layout: top-level JSON value must be an object")
    layouts = {}
    required = {"local_row_count", "inputs", "constants", "outputs"}
    for name in selected:
        if name not in document:
            parser.error(f"--physical-layout: missing layout for profile {name}")
        record = document[name]
        if not isinstance(record, dict):
            parser.error(f"--physical-layout: profile {name} must be an object")
        actual = set(record)
        if actual != required:
            missing = sorted(required - actual)
            extra = sorted(actual - required)
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if extra:
                details.append("unsupported " + ", ".join(extra))
            parser.error(f"--physical-layout: profile {name}: {'; '.join(details)}")
        for category in ("inputs", "constants", "outputs"):
            if not isinstance(record[category], dict):
                parser.error(
                    f"--physical-layout: profile {name}: {category} must be an object"
                )
        try:
            layout = PhysicalRowLayout(
                record["local_row_count"],
                record["inputs"],
                record["constants"],
                record["outputs"],
            )
            layouts[name] = layout
        except (PhysicalLoweringError, TypeError, ValueError) as error:
            parser.error(f"--physical-layout: profile {name}: {error}")
    return layouts


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
    parser.add_argument(
        "--physical-layout",
        type=Path,
        help=(
            "JSON file with exact per-profile local_row_count and "
            "input/constant/output row designations"
        ),
    )
    parser.add_argument(
        "--use-default-physical-layout",
        action="store_true",
        help=(
            "generate deterministic consecutive physical designations using "
            "the current 1024-row DDR4/MIMDRAM model default; takes precedence "
            "over --physical-layout"
        ),
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

    selected = list(dict.fromkeys(args.only or PROFILES))
    programs = {name: build(name) for name in selected}
    if args.use_default_physical_layout:
        layouts = {
            name: make_default_physical_layout(programs[name]) for name in selected
        }
        layout_provenance = "default_generated"
        write_default_physical_layout(layouts, args.out)
    elif args.physical_layout:
        layouts = _load_physical_layouts(args.physical_layout, selected, parser)
        layout_provenance = "caller_provided"
    else:
        layouts = {}
        layout_provenance = None
    lowered_programs = {}
    for name, layout in layouts.items():
        try:
            lowered_programs[name] = lower_to_physical(programs[name], layout)
        except PhysicalLoweringError as error:
            option = (
                "--use-default-physical-layout"
                if args.use_default_physical_layout
                else "--physical-layout"
            )
            parser.error(f"{option}: profile {name}: {error}")

    report = {
        "schema_version": 1,
        "versions": versions,
        "library_check": args.library_check,
        "scope": (
            "Symbolic and physical-lowering functional validation; FP8 profile contracts apply."
            if layouts
            else "Symbolic functional validation; FP8 profile contracts apply."
        ),
        "variants": {},
    }
    for name in selected:
        program = programs[name]
        path, info = write_program(name, program, args.out)
        lowered = lowered_programs.get(name)
        if lowered is not None:
            write_physical_program(
                name, lowered, args.out, layout_provenance=layout_provenance
            )
        validation = verify(
            name, program, path, info, args.library_check, lowered=lowered
        )
        if lowered is not None:
            validation["physical_lowering"]["layout_provenance"] = layout_provenance
        report["variants"][name] = {
            "contract": info["contract"],
            "cost": info["cost"],
            "validation": validation,
        }
        outcome = (
            "reference/symbolic/physical PASS"
            if lowered is not None
            else "reference/replay PASS"
        )
        print(
            f"{name}: {len(program.trace)} primitives, "
            f"{validation['pairs']:,} pairs, {outcome}",
            flush=True,
        )

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "validation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
