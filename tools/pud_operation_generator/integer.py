"""Exact widened UINT8 and signed INT8 arithmetic generators."""

from collections import deque

from .core import Builder


def _build_multiply(*, signed: bool):
    width = 8
    builder = Builder([f"{operand}{bit}" for operand in "AB" for bit in range(width)])
    builder.width = width
    builder.signed = signed
    builder.constants = {
        builder.zero: 0,
        **({builder.one: 1} if signed else {}),
    }
    builder.columns = []
    builder.complemented_partial_products = []
    buckets = [deque() for _ in range(2 * width + 1)]

    for i in range(width):
        for j in range(width):
            builder.stage = (
                f"partial_product_{i}_{j}: A{i} AND B{j}, weight 2^{i + j}"
            )
            partial_product = builder.bit_and(f"A{i}", f"B{j}")
            # In two's complement, a term containing exactly one sign bit has
            # a negative coefficient. Complement it here and correct the sum below.
            if signed and ((i == width - 1) != (j == width - 1)):
                builder.stage = f"signed_complement_{i}_{j}"
                builder.emit("NOT", partial_product)
                builder.complemented_partial_products.append([i, j])
            buckets[i + j].append(partial_product)

    if signed:
        # Together with the complemented cross terms, these constants transform
        # the accumulated value into A*B + 2^(2*width). The low 16 bits are A*B.
        buckets[width].append(builder.one)
        buckets[2 * width - 1].append(builder.one)

    result = []
    for bit in range(2 * width):
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

    builder.stage = "output: copy completed product bits to R rows"
    builder.export("R", result)
    return builder


def _build_add(*, signed: bool):
    width = 8
    builder = Builder([f"{operand}{bit}" for operand in "AB" for bit in range(width)])
    builder.width = width
    builder.signed = signed
    builder.constants = {builder.zero: 0}
    left, right = ([f"{operand}{bit}" for bit in range(width)] for operand in "AB")

    if signed:
        left.append(left[-1])
        right.append(right[-1])
        builder.stage = "signed ripple ADD: sign-extend both operands to nine bits"
    else:
        builder.stage = "unsigned ripple ADD: retain the final carry"

    result = builder.add(left, right)
    if signed:
        builder.carry_beyond_output = [result[-1]]
        result = result[:-1]
    else:
        builder.carry_beyond_output = []

    builder.stage = "output: copy exact nine-bit sum to R rows"
    builder.export("R", result)
    return builder


def build_uint8_add():
    """Build an unsigned 8-bit add with an exact unsigned 9-bit result."""
    return _build_add(signed=False)


def build_uint8_mul():
    """Build an unsigned 8-bit multiply with an exact unsigned 16-bit result."""
    return _build_multiply(signed=False)


def build_int8_add():
    """Build a two's-complement 8-bit add with an exact signed 9-bit result."""
    return _build_add(signed=True)


def build_int8_mul():
    """Build a two's-complement 8-bit multiply with a signed 16-bit result."""
    return _build_multiply(signed=True)
