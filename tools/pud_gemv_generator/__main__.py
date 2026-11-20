"""Generate one explicit MIMDRAM GEMV baseline/format trace; CUDA is not runtime input."""
import argparse
from pathlib import Path
from .generator import PROFILES, write_gemv
from .targets import TARGETS

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--profile", choices=PROFILES, required=True)
parser.add_argument("--m", type=int, required=True)
parser.add_argument("--n", type=int, required=True)
parser.add_argument("--target", choices=TARGETS, default="DDR4")
parser.add_argument("--out", type=Path, default=Path("build/pud-gemv"))
args = parser.parse_args()
try:
    metadata, path = write_gemv(args.profile, args.m, args.n, args.out, target=args.target)
except ValueError as error:
    parser.error(str(error))
print(f"{args.profile}: {metadata['request_count']} physical requests -> {path}")
