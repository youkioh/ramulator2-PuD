"""Generate the fixed shared-K DDR4-packed Q[8,128] x K[128,2048] GEMM."""
import argparse
from pathlib import Path
from .generator import PROFILES, write_gemm

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--profile", choices=PROFILES, required=True)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
try:
    layout, path = write_gemm(args.profile, args.out)
except ValueError as error:
    parser.error(str(error))
print(f"16 Bank CHAINs, {len(layout['outputs'])} outputs, {layout['request_count']} Requests -> {path}")
