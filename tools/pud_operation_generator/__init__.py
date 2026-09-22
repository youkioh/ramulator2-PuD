"""Standalone PuD trace generators for integer and FP8 arithmetic."""

from .fp8 import (
    build_e2m1_add,
    build_e2m1_mul,
    build_e4m3_add,
    build_e4m3_mul,
    build_e5m2_add,
    build_e5m2_mul,
)
from .integer import (
    build_int4_add,
    build_int4_mul,
    build_int8_add,
    build_int8_mul,
    build_uint4_add,
    build_uint4_mul,
    build_uint8_add,
    build_uint8_mul,
)
from .lowering import (
    LoweredPrimitive,
    NormalizedProgram,
    PhysicalLoweredProgram,
    PhysicalLoweringError,
    PhysicalRowLayout,
    analyze_physical_lowering,
    lower_to_physical,
    make_default_physical_layout,
)
from .physical_replay import execute_physical, extract_physical_results

__all__ = [
    "build_uint4_add",
    "build_uint4_mul",
    "build_int4_add",
    "build_int4_mul",
    "build_uint8_add",
    "build_uint8_mul",
    "build_int8_add",
    "build_int8_mul",
    "build_e2m1_add",
    "build_e2m1_mul",
    "build_e5m2_add",
    "build_e5m2_mul",
    "build_e4m3_add",
    "build_e4m3_mul",
    "PhysicalLoweringError",
    "PhysicalRowLayout",
    "NormalizedProgram",
    "LoweredPrimitive",
    "PhysicalLoweredProgram",
    "analyze_physical_lowering",
    "lower_to_physical",
    "make_default_physical_layout",
    "execute_physical",
    "extract_physical_results",
]
