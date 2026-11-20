"""Full-width integer arithmetic with fixed-width UINT and INT exports."""

from collections import deque

from .core import Builder


def _build_multiply(*, signed: bool, width: int):
    builder = Builder([f"{operand}{bit}" for operand in "AB" for bit in range(width)])
    builder.width = width
    builder.signed = signed
    builder.format_name = f"{'int' if signed else 'uint'}{width}"
    builder.constants = {
        builder.zero: 0,
        **({builder.one: 1} if signed else {}),
    }
    builder.columns = []
    builder.complemented_partial_products = []
    buckets = [deque() for _ in range(2 * width + 1)]

    def partial_product(i, j):
        builder.stage = (
            f"partial_product_{i}_{j}: A{i} AND B{j}, weight 2^{i + j}"
        )
        product = builder.bit_and(f"A{i}", f"B{j}")
        # A term containing exactly one sign bit has a negative coefficient.
        if signed and ((i == width - 1) != (j == width - 1)):
            builder.stage = f"signed_complement_{i}_{j}"
            builder.emit("NOT", product)
            builder.complemented_partial_products.append([i, j])
        return product

    result = []
    for bit in range(2 * width):
        # Emit only this column's products, then reduce before emitting the
        # next column. Preserve the compressor's products/correction/carries
        # operand order from the original all-products-first algorithm.
        incoming = buckets[bit]
        buckets[bit] = deque(
            partial_product(i, bit - i)
            for i in range(width)
            if 0 <= bit - i < width
        )
        # With complemented cross terms these yield A*B + 2^(2*width).
        if signed and bit in (width, 2 * width - 1):
            buckets[bit].append(builder.one)
        buckets[bit].extend(incoming)
        bucket = buckets[bit]
        initial_count = len(bucket)
        builder.stage = (
            f"column_{bit}: sum weight-2^{bit} bits; carry to column {bit + 1}"
        )
        full_adders = 0
        half_adders = 0
        while len(bucket) >= 3:
            arguments = [bucket.popleft() for _ in range(3)]
            total, carry = builder.full_add(*arguments)
            bucket.append(total)
            buckets[bit + 1].append(carry)
            full_adders += 1
        if len(bucket) == 2:
            total, carry = builder.full_add(bucket[0], bucket[1], builder.zero)
            result.append(total)
            buckets[bit + 1].append(carry)
            half_adders += 1
        else:
            result.append(bucket[0] if bucket else builder.zero)
        builder.columns.append(
            {
                "bit": bit,
                "input_bits_including_carries": initial_count,
                "three_input_adders": full_adders,
                "two_input_adders_using_zero": half_adders,
            }
        )

    builder.carry_beyond_output = list(buckets[2 * width])
    if signed and len(builder.carry_beyond_output) != 1:
        raise AssertionError("expected exactly one signed correction carry")
    if not signed and builder.carry_beyond_output:
        raise AssertionError("unexpected unsigned overflow structure")

    builder.taps["full_result"] = result
    builder.stage = f"output: copy low {width} product bits to R rows"
    builder.export("R", result[:width])
    return builder


def _build_add(*, signed: bool, width: int):
    builder = Builder([f"{operand}{bit}" for operand in "AB" for bit in range(width)])
    builder.width = width
    builder.signed = signed
    builder.format_name = f"{'int' if signed else 'uint'}{width}"
    builder.constants = {builder.zero: 0}
    left, right = ([f"{operand}{bit}" for bit in range(width)] for operand in "AB")

    if signed:
        left.append(left[-1])
        right.append(right[-1])
        builder.stage = (
            f"signed ripple ADD: sign-extend both operands to {width + 1} bits"
        )
    else:
        builder.stage = "unsigned ripple ADD: retain the final carry"

    result = builder.add(left, right)
    if signed:
        builder.carry_beyond_output = [result[-1]]
        result = result[:-1]
    else:
        builder.carry_beyond_output = []

    builder.taps["full_result"] = result
    builder.stage = f"output: copy low {width} sum bits to R rows"
    builder.export("R", result[:width])
    return builder


def build_uint4_add():
    """Compute the exact unsigned 5-bit sum and expose only its low four bits."""
    return _build_add(signed=False, width=4)


def build_uint4_mul():
    """Compute the exact unsigned 8-bit product and expose only its low four bits."""
    return _build_multiply(signed=False, width=4)


def build_int4_add():
    """Compute the exact signed 5-bit sum and expose only its low four bits."""
    return _build_add(signed=True, width=4)


def build_int4_mul():
    """Compute the exact signed 8-bit product and expose only its low four bits."""
    return _build_multiply(signed=True, width=4)


def build_uint8_add():
    """Compute the exact unsigned 9-bit sum and expose only its low eight bits."""
    return _build_add(signed=False, width=8)


def build_uint8_mul():
    """Compute the exact unsigned 16-bit product and expose only its low eight bits."""
    return _build_multiply(signed=False, width=8)


def build_int8_add():
    """Compute the exact signed 9-bit sum and expose only its low eight bits."""
    return _build_add(signed=True, width=8)


def build_int8_mul():
    """Compute all 16 signed product bits and expose only the low eight bits."""
    return _build_multiply(signed=True, width=8)
