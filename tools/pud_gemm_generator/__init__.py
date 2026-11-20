"""Shared-K DDR4-packed GEMM with one query per chip."""
from .generator import generate, write_gemm
from .validation import execute_trace, read_gemm, scalar_graph

__all__ = ["generate", "write_gemm", "execute_trace", "read_gemm", "scalar_graph"]
