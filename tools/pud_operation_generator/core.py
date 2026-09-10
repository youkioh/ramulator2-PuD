"""Shared bitslice builder and destructive primitive interpreter (stdlib only)."""
from __future__ import annotations
from dataclasses import dataclass
from itertools import combinations
import re

@dataclass(frozen=True)
class Primitive:
    op: str
    rows: tuple[str, ...]
    stage: str = ""

class Builder:
    """Shared Boolean and arithmetic helpers; optimized five-leaf substrate.

    All helper inputs are preserved. TRA/5RA work on distinct copied rows.
    Row names are symbolic; no physical allocator or timing model is implied.
    """

    def __init__(self, input_names: list[str]):
        self.inputs = list(input_names)
        self.zero = 'CONST_ZERO'
        self.one = 'CONST_ONE'
        self.rows = self.inputs + [self.zero, self.one]
        self.trace: list[Primitive] = []
        self.stage = 'setup'
        self.counter = 0
        self.outputs: dict[str, list[str]] = {}
        self.taps: dict[str, list[str]] = {}

    def new_row(self) -> str:
        row = f't{self.counter:04d}'
        self.counter += 1
        self.rows.append(row)
        return row

    def emit(self, op: str, *rows: str) -> None:
        self.trace.append(Primitive(op, tuple(rows), self.stage))

    def copy(self, src: str) -> str:
        dst = self.new_row()
        self.emit('RowCopy', src, dst)
        return dst

    def bit_not(self, a: str) -> str:
        dst = self.copy(a)
        self.emit('NOT', dst)
        return dst

    def majority(self, args):
        if len(args) not in (3, 5):
            raise ValueError('Only majority of three or five is supported')
        copied = self.copied_arguments(args)
        self.emit('TRA' if len(args) == 3 else '5RA', *copied)
        return copied[0]

    def bit_and(self, a: str, b: str) -> str:
        return self.majority([a, b, self.zero])

    def bit_or(self, a: str, b: str) -> str:
        return self.majority([a, b, self.one])

    def bit_xor(self, a: str, b: str) -> str:
        union = self.bit_or(a, b)
        intersection = self.bit_and(a, b)
        return self.bit_and(union, self.bit_not(intersection))

    def select(self, p: str, yes: str, no: str) -> str:
        np = self.bit_not(p)
        left = self.bit_and(p, yes)
        right = self.bit_and(np, no)
        return self.bit_or(left, right)

    def reduce_or(self, bits: list[str]) -> str:
        if not bits:
            raise ValueError('This demo only needs nonempty Boolean reductions.')
        value = bits[0]
        for bit in bits[1:]:
            value = self.bit_or(value, bit)
        return value

    def reduce_and(self, bits: list[str]) -> str:
        if not bits:
            raise ValueError('This demo only needs nonempty Boolean reductions.')
        value = bits[0]
        for bit in bits[1:]:
            value = self.bit_and(value, bit)
        return value

    def full_add(self, a, b, cin):
        (ac, asum, bc, bsum, cc, csum) = self.copied_arguments([a, a, b, b, cin, cin])
        self.emit('TRA', ac, bc, cc)
        (nc,) = self.not_copy_many(bc, 1)
        self.emit('5RA', asum, bsum, csum, bc, nc)
        return (asum, ac)

    def add(self, a, b, cin=None):
        if len(a) != len(b) or not a:
            raise ValueError('Nonempty equal-width operands required')
        (carry_tra, carry_sum) = self.copy_many(self.zero if cin is None else cin, 2)
        sums = []
        for (ai, bi) in zip(a, b):
            (ac, asum, bc, bsum) = self.copied_arguments([ai, ai, bi, bi])
            self.emit('TRA', carry_tra, ac, bc)
            (nc,) = self.not_copy_many(ac, 1)
            self.emit('5RA', asum, bsum, carry_sum, ac, nc)
            sums.append(asum)
            carry_sum = bc
        return sums + [carry_tra]

    def multiply(self, a: list[str], b: list[str]) -> list[str]:
        """Partial products and bit-position-wise addition, PRADA-style.

        This particular compressor ordering is derived, not paper-reported.
        """
        width = len(a) + len(b)
        buckets: list[list[str]] = [[] for _ in range(width + 1)]
        for (i, ai) in enumerate(a):
            for (j, bj) in enumerate(b):
                buckets[i + j].append(self.bit_and(ai, bj))
        result = []
        for k in range(width):
            bucket = buckets[k]
            while len(bucket) >= 3:
                abc = [bucket.pop(0) for _ in range(3)]
                (total, carry) = self.full_add(*abc)
                bucket.append(total)
                buckets[k + 1].append(carry)
            if len(bucket) == 2:
                (total, carry) = self.full_add(bucket[0], bucket[1], self.zero)
                result.append(total)
                buckets[k + 1].append(carry)
            elif len(bucket) == 1:
                result.append(bucket[0])
            else:
                result.append(self.zero)
        if buckets[width]:
            raise AssertionError('Unexpected product carry structure.')
        return result

    def export(self, label, bits):
        self.outputs[label] = [f'{label}{i}' for i in range(len(bits))]
        for source, destination in zip(bits, self.outputs[label]):
            self.emit('RowCopy', source, destination)
            self.rows.append(destination)

    def copy_many(self, src, count):
        if count < 1:
            raise ValueError('At least one destination is required')
        dsts = [self.new_row() for _ in range(count)]
        self.emit('RowCopy', src, *dsts)
        return dsts

    def copied_arguments(self, args):
        groups = {}
        for (index, src) in enumerate(args):
            groups.setdefault(src, []).append(index)
        copied = [None] * len(args)
        for (src, indices) in groups.items():
            for (index, dst) in zip(indices, self.copy_many(src, len(indices))):
                copied[index] = dst
        return copied

    def not_copy_many(self, disposable_source, count):
        if count < 1:
            raise ValueError('At least one explicit destination is required')
        dsts = [self.new_row() for _ in range(count)]
        self.emit('NOT_COPY', disposable_source, *dsts)
        return dsts
def validate_structure(trace, inputs, constants, outputs):
    defined = set(inputs) | set(constants)
    protected = defined.copy()
    for index, inst in enumerate(trace):
        op, rr = inst.op, inst.rows
        if len(set(rr)) != len(rr):
            raise AssertionError((index, "Aliased row roles"))
        if op in ("RowCopy", "NOT_COPY"):
            assert len(rr) >= 2
            reads = rr[:1]
            writes = rr[1:] if op == "RowCopy" else rr
        elif op in ("TRA", "5RA", "NOT"):
            assert len(rr) == {"TRA": 3, "5RA": 5, "NOT": 1}[op]
            reads = writes = rr
        else:
            raise AssertionError((index, "Non-primitive", op))
        assert set(reads) <= defined, (index, "Read before write", set(reads)-defined)
        assert not (set(writes) & protected), (index, "Input/constant overwritten")
        defined.update(writes)
    assert set(outputs) <= defined

def execute(trace, initial, lanes, protected=None):
    """A Python integer stores a ROW of independent lane bits.

    This interpreter implements only the five leaf primitives. No multiply,
    integer add, sign test, or conditional selection occurs here.
    """
    protected = initial if protected is None else protected
    mask = (1 << lanes) - 1
    rows = dict(initial)
    for inst in trace:
        op, rr = inst.op, inst.rows
        if op in ("RowCopy", "NOT_COPY"):
            value = rows[rr[0]]  # snapshot; destinations need no prior value
            if op == "NOT_COPY":
                value ^= mask
                rows[rr[0]] = value
            for dst in rr[1:]:
                rows[dst] = value
        elif op == "NOT":
            rows[rr[0]] ^= mask
        elif op in ("TRA", "5RA"):
            old = [rows[r] for r in rr]
            value = 0
            for group in combinations(old, len(old)//2 + 1):
                term = mask
                for word in group:
                    term &= word
                value |= term
            for r in rr:
                rows[r] = value
        else:
            raise AssertionError(op)
    assert all(rows[r] == initial[r] for r in protected), "Protected row changed"
    return rows

def pack(values, width):
    values = list(values)
    words = []
    for bit in range(width):
        data = bytearray((len(values) + 7)//8)
        for lane, value in enumerate(values):
            data[lane//8] |= ((value >> bit) & 1) << (lane % 8)
        words.append(int.from_bytes(data, "little"))
    return words

def unpack(words, lanes):
    data = [word.to_bytes((lanes + 7)//8, "little") for word in words]
    return [sum(((v[lane//8] >> (lane % 8)) & 1) << i
                for i, v in enumerate(data)) for lane in range(lanes)]

def signed_value(value, width):
    return value - (1 << width) if value & (1 << (width - 1)) else value

def read_program(path):
    trace = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        m = re.fullmatch(r"(\d+): (RowCopy|NOT_COPY|NOT|TRA|5RA)\(([^)]+)\)", line)
        if not m or int(m[1]) != len(trace):
            raise ValueError(f"Malformed trace line: {line}")
        trace.append(Primitive(m[2], tuple(m[3].split(", "))))
    return trace
