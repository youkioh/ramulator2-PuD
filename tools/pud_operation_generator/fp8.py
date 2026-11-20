"""E2M1, E5M2, and E4M3 arithmetic traces with scalar references."""

from dataclasses import dataclass
from fractions import Fraction

from .core import Builder


@dataclass(frozen=True)
class FP8Format:
    name: str
    exponent_bits: int
    fraction_bits: int
    bias: int
    finite_only: bool
    has_nan: bool

    @property
    def total_bits(self):
        return 1 + self.exponent_bits + self.fraction_bits

    @property
    def sign_bit(self):
        return self.total_bits - 1

    @property
    def exponent_mask(self):
        return (1 << self.exponent_bits) - 1

    @property
    def fraction_mask(self):
        return (1 << self.fraction_bits) - 1

    @property
    def min_normal(self):
        return Fraction(1, 1 << (self.bias - 1))

    @property
    def max_normal(self):
        if self.finite_only:
            significand = (
                (1 << self.fraction_bits)
                + self.fraction_mask
                - int(self.has_nan)
            )
            exponent = self.exponent_mask
        else:
            significand = (1 << self.fraction_bits) + self.fraction_mask
            exponent = self.exponent_mask - 1
        shift = exponent - self.bias - self.fraction_bits
        return Fraction(significand * (1 << shift), 1)

    def is_normal(self, byte):
        exponent = (byte >> self.fraction_bits) & self.exponent_mask
        fraction = byte & self.fraction_mask
        if exponent == 0:
            return False
        if self.finite_only and self.has_nan:
            return not (
                exponent == self.exponent_mask and fraction == self.fraction_mask
            )
        return self.finite_only or exponent != self.exponent_mask


E2M1 = FP8Format(
    "e2m1", exponent_bits=2, fraction_bits=1, bias=1,
    finite_only=True, has_nan=False,
)
E5M2 = FP8Format(
    "e5m2", exponent_bits=5, fraction_bits=2, bias=15,
    finite_only=False, has_nan=True,
)
E4M3 = FP8Format(
    "e4m3", exponent_bits=4, fraction_bits=3, bias=7,
    finite_only=True, has_nan=True,
)


class FP8Builder(Builder):
    def const(self, value, width):
        return [self.one if (value >> bit) & 1 else self.zero for bit in range(width)]

    def equals(self, value, constant):
        terms = [
            row if (constant >> bit) & 1 else self.bit_not(row)
            for bit, row in enumerate(value)
        ]
        return self.reduce_and(terms)

    def or_terms(self, terms):
        return self.reduce_or(terms) if terms else self.zero

    def case_select(self, cases, width):
        """OR masked alternatives supplied with mutually exclusive predicates."""
        result = []
        for bit in range(width):
            terms = []
            for predicate, value in cases:
                row = value[bit]
                if row == self.zero:
                    continue
                terms.append(
                    predicate if row == self.one else self.bit_and(predicate, row)
                )
            result.append(self.or_terms(terms))
        return result

    def conditional_twos_complement(self, magnitude, negative):
        inverted = [
            negative if row == self.zero else self.bit_xor(row, negative)
            for row in magnitude
        ]
        return self.add(
            inverted, [self.zero] * len(magnitude), cin=negative
        )[:-1]


def _new_builder(format_):
    builder = FP8Builder(
        [
            f"{operand}{bit}"
            for operand in ("A", "B")
            for bit in range(format_.total_bits)
        ]
    )
    builder.width = format_.total_bits
    builder.format_name = format_.name
    builder.exponent_bits = format_.exponent_bits
    builder.fraction_bits = format_.fraction_bits
    builder.constants = {builder.zero: 0, builder.one: 1}
    return builder


def _build_fp8_mul(format_):
    builder = _new_builder(format_)
    left = [f"A{bit}" for bit in range(format_.total_bits)]
    right = [f"B{bit}" for bit in range(format_.total_bits)]
    fraction_bits = format_.fraction_bits
    exponent_bits = format_.exponent_bits
    left_exponent = left[fraction_bits:format_.sign_bit]
    right_exponent = right[fraction_bits:format_.sign_bit]

    builder.stage = f"{format_.name.upper()} MUL.1: sign XOR"
    sign = builder.bit_xor(left[format_.sign_bit], right[format_.sign_bit])

    builder.stage = (
        f"{format_.name.upper()} MUL.2: multiply implicit-one significands"
    )
    product = builder.multiply(
        left[:fraction_bits] + [builder.one],
        right[:fraction_bits] + [builder.one],
    )
    builder.taps["significand_product"] = product
    normalization = product[2 * fraction_bits + 1]

    builder.stage = (
        f"{format_.name.upper()} MUL.3: select truncating fraction bits"
    )
    fraction = [
        builder.select(
            normalization,
            product[fraction_bits + 1 + bit],
            product[fraction_bits + bit],
        )
        for bit in range(fraction_bits)
    ]

    builder.stage = (
        f"{format_.name.upper()} MUL.4: add exponents and normalization bit"
    )
    exponent_sum = builder.add(
        left_exponent, right_exponent, cin=normalization
    )
    builder.taps["exponent_sum"] = exponent_sum

    builder.stage = f"{format_.name.upper()} MUL.5: subtract exponent bias"
    exponent_sum_width = exponent_bits + 1
    bias_complement = (1 << exponent_sum_width) - format_.bias
    bias = builder.const(bias_complement, exponent_sum_width)
    adjusted = builder.add(exponent_sum, bias)
    builder.taps["adjusted_exponent"] = adjusted

    builder.stage = f"{format_.name.upper()} MUL.6: clamp exponent field range"
    nonnegative = adjusted[exponent_bits + 1]
    overflow = builder.bit_and(nonnegative, adjusted[exponent_bits])
    exponent = [
        builder.bit_or(overflow, builder.bit_and(nonnegative, adjusted[bit]))
        for bit in range(exponent_bits)
    ]

    builder.stage = f"{format_.name.upper()} MUL.7: mask zero-exponent inputs"
    neither_exponent_zero = builder.bit_and(
        builder.reduce_or(left_exponent), builder.reduce_or(right_exponent)
    )
    exponent = [builder.bit_and(bit, neither_exponent_zero) for bit in exponent]

    if not format_.finite_only:
        builder.stage = (
            f"{format_.name.upper()} MUL.8: propagate all-ones input exponents"
        )
        either_exponent_all_ones = builder.bit_or(
            builder.reduce_and(left_exponent), builder.reduce_and(right_exponent)
        )
        exponent = [
            builder.bit_or(bit, either_exponent_all_ones) for bit in exponent
        ]

    builder.stage = (
        f"{format_.name.upper()} MUL output: export fraction, exponent, and sign"
    )
    builder.export("R", fraction + exponent + [sign])
    return builder


def _alignment_predicates(builder, difference, fraction_bits):
    equal = {
        delta: builder.equals(difference, delta)
        for delta in range(-fraction_bits, fraction_bits + 1)
    }
    positive_window = builder.reduce_or(
        [equal[delta] for delta in range(0, fraction_bits + 1)]
    )
    greater = builder.bit_and(
        builder.bit_not(difference[-1]), builder.bit_not(positive_window)
    )
    negative_window = builder.reduce_or(
        [equal[-delta] for delta in range(1, fraction_bits + 1)]
    )
    less = builder.bit_and(difference[-1], builder.bit_not(negative_window))

    names = [f"d>{fraction_bits}"]
    predicates = [greater]
    for delta in range(fraction_bits, 0, -1):
        names.append(f"d={delta}")
        predicates.append(equal[delta])
    names.append("d=0")
    predicates.append(equal[0])
    for delta in range(1, fraction_bits + 1):
        names.append(f"d=-{delta}")
        predicates.append(equal[-delta])
    names.append(f"d<-{fraction_bits}")
    predicates.append(less)
    return names, predicates


def _leading_bit_predicates(builder, magnitude):
    highest = len(magnitude) - 1
    predicates = [magnitude[highest]]
    names = [f"leading_bit_{highest}"]
    prefix_zero = builder.bit_not(magnitude[highest])
    for bit in range(highest - 1, -1, -1):
        predicates.append(builder.bit_and(prefix_zero, magnitude[bit]))
        names.append(f"leading_bit_{bit}")
        prefix_zero = builder.bit_and(
            prefix_zero, builder.bit_not(magnitude[bit])
        )
    predicates.append(prefix_zero)
    names.append("magnitude_zero")
    return names, predicates


def _build_fp8_add(format_):
    builder = _new_builder(format_)
    left, right = (
        [f"{operand}{bit}" for bit in range(format_.total_bits)]
        for operand in ("A", "B")
    )
    exponent_bits = format_.exponent_bits
    fraction_bits = format_.fraction_bits
    left_exponent = left[fraction_bits:format_.sign_bit]
    right_exponent = right[fraction_bits:format_.sign_bit]
    zero = builder.zero
    one = builder.one

    builder.stage = (
        f"{format_.name.upper()} ADD.1: exponent difference and alignment predicates"
    )
    difference = builder.add(
        left_exponent + [zero], # add zero to LSB to get signed difference of unsigned exponents
        [builder.bit_not(row) for row in right_exponent + [zero]],
        cin=one,
    )[: exponent_bits + 1]
    branch_names, branch_predicates = _alignment_predicates(
        builder, difference, fraction_bits
    )
    builder.taps["exponent_difference_signed"] = difference
    builder.taps.update(
        {name: [predicate] for name, predicate in zip(branch_names, branch_predicates)}
    )

    builder.stage = (
        f"{format_.name.upper()} ADD.2: select aligned operands and common exponent"
    )
    aligned_width = fraction_bits + 2
    full_left = left[:fraction_bits] + [one, zero] # bit list is aligned from LSB to MSB from right to left, so add implicit one and zero for sign bit
    full_right = right[:fraction_bits] + [one, zero]

    alternatives = [(full_left, [zero] * aligned_width, left_exponent)]
    for shift in range(fraction_bits, 0, -1):
        shifted_right = full_right[shift:] + [zero] * shift
        alternatives.append((full_left, shifted_right, left_exponent))
    alternatives.append((full_left, full_right, left_exponent))
    for shift in range(1, fraction_bits + 1):
        shifted_left = full_left[shift:] + [zero] * shift
        alternatives.append((shifted_left, full_right, right_exponent))
    alternatives.append(([zero] * aligned_width, full_right, right_exponent))

    aligned_left = builder.case_select(
        [
            (predicate, alternative[0])
            for predicate, alternative in zip(branch_predicates, alternatives)
        ],
        aligned_width,
    )
    aligned_right = builder.case_select(
        [
            (predicate, alternative[1])
            for predicate, alternative in zip(branch_predicates, alternatives)
        ],
        aligned_width,
    )
    common_exponent = builder.case_select(
        [
            (predicate, alternative[2])
            for predicate, alternative in zip(branch_predicates, alternatives)
        ],
        exponent_bits,
    )
    builder.taps.update(
        aligned_left=aligned_left,
        aligned_right=aligned_right,
        common_exponent=common_exponent,
    )

    builder.stage = (
        f"{format_.name.upper()} ADD.3: convert aligned operands to signed values"
    )
    signed_left = builder.conditional_twos_complement(
        aligned_left + [zero], left[format_.sign_bit]
    )
    signed_right = builder.conditional_twos_complement(
        aligned_right + [zero], right[format_.sign_bit]
    )
    builder.taps.update(signed_left=signed_left, signed_right=signed_right)

    builder.stage = f"{format_.name.upper()} ADD.4: add signed significands"
    signed_sum = builder.add(signed_left, signed_right)[: aligned_width + 1]
    sign = signed_sum[-1]
    builder.taps["signed_sum"] = signed_sum

    builder.stage = (
        f"{format_.name.upper()} ADD.5: obtain sign and absolute magnitude"
    )
    magnitude = builder.conditional_twos_complement(signed_sum, sign)[:aligned_width]
    builder.taps.update(result_sign=[sign], magnitude=magnitude)

    builder.stage = f"{format_.name.upper()} ADD.6: detect leading magnitude bit"
    normalization_names, normalization_predicates = _leading_bit_predicates(
        builder, magnitude
    )
    builder.taps.update(
        {
            name: [predicate]
            for name, predicate in zip(
                normalization_names, normalization_predicates
            )
        }
    )

    builder.stage = (
        f"{format_.name.upper()} ADD.7: select fraction bits without rounding"
    )
    fraction_cases = []
    for leading_bit, predicate in zip(
        range(aligned_width - 1, -1, -1), normalization_predicates[:-1]
    ):
        fraction = []
        for bit in range(fraction_bits):
            source = leading_bit - fraction_bits + bit
            fraction.append(magnitude[source] if source >= 0 else zero)
        fraction_cases.append((predicate, fraction))
    fraction_cases.append((normalization_predicates[-1], [zero] * fraction_bits))
    fraction = builder.case_select(fraction_cases, fraction_bits)

    builder.stage = (
        f"{format_.name.upper()} ADD.8: apply normalization exponent adjustment"
    )
    exponent_width = exponent_bits + 2
    exponent_mask = (1 << exponent_width) - 1
    delta_cases = []
    for leading_bit, predicate in zip(
        range(aligned_width - 1, -1, -1), normalization_predicates[:-1]
    ):
        delta = leading_bit - fraction_bits
        delta_cases.append(
            (predicate, builder.const(delta & exponent_mask, exponent_width))
        )
    delta_cases.append((normalization_predicates[-1], [zero] * exponent_width))
    exponent_delta = builder.case_select(delta_cases, exponent_width)
    exponent = builder.add(
        common_exponent + [zero, zero], exponent_delta
    )[:exponent_width]
    nonzero = builder.bit_not(normalization_predicates[-1])
    exponent = [builder.bit_and(nonzero, row) for row in exponent]
    builder.taps.update(fraction=fraction, exponent_signed=exponent)

    builder.stage = f"{format_.name.upper()} ADD output: export candidate fields"
    builder.export("R", fraction + exponent[:exponent_bits] + [sign])
    return builder


def scalar_fp8_mul_reference(left, right, format_):
    """Scalar transcription of the generated truncating multiplication trace."""
    fraction_bits = format_.fraction_bits
    exponent_mask = format_.exponent_mask
    left_exponent = (left >> fraction_bits) & exponent_mask
    right_exponent = (right >> fraction_bits) & exponent_mask
    left_significand = (1 << fraction_bits) + (left & format_.fraction_mask)
    right_significand = (1 << fraction_bits) + (right & format_.fraction_mask)
    product = left_significand * right_significand
    normalized = product >= (1 << (2 * fraction_bits + 1))
    shift = fraction_bits + int(normalized)
    fraction = (product >> shift) & format_.fraction_mask
    exponent = min(
        exponent_mask,
        max(0, left_exponent + right_exponent - format_.bias + int(normalized)),
    )
    if left_exponent == 0 or right_exponent == 0:
        exponent = 0
    if not format_.finite_only and (
        left_exponent == exponent_mask or right_exponent == exponent_mask
    ):
        exponent = exponent_mask
    sign = ((left ^ right) >> format_.sign_bit) & 1
    return (sign << format_.sign_bit) | (exponent << fraction_bits) | fraction


def fp8_add_reference(left, right, format_):
    """Scalar transcription of bounded alignment and truncating normalization."""
    fraction_bits = format_.fraction_bits
    exponent_mask = format_.exponent_mask
    left_exponent = (left >> fraction_bits) & exponent_mask
    right_exponent = (right >> fraction_bits) & exponent_mask
    left_significand = (1 << fraction_bits) + (left & format_.fraction_mask)
    right_significand = (1 << fraction_bits) + (right & format_.fraction_mask)
    difference = left_exponent - right_exponent

    if difference > fraction_bits:
        aligned_left, aligned_right, common, branch = (
            left_significand,
            0,
            left_exponent,
            f"d>{fraction_bits}",
        )
    elif difference >= 0:
        aligned_left = left_significand
        aligned_right = right_significand >> difference
        common = left_exponent
        branch = f"d={difference}"
    elif difference >= -fraction_bits:
        aligned_left = left_significand >> -difference
        aligned_right = right_significand
        common = right_exponent
        branch = f"d={difference}"
    else:
        aligned_left, aligned_right, common, branch = (
            0,
            right_significand,
            right_exponent,
            f"d<-{fraction_bits}",
        )

    sign_mask = 1 << format_.sign_bit
    signed_left = -aligned_left if left & sign_mask else aligned_left
    signed_right = -aligned_right if right & sign_mask else aligned_right
    signed_sum = signed_left + signed_right
    sign = int(signed_sum < 0)
    magnitude = abs(signed_sum)

    if magnitude:
        leading_bit = magnitude.bit_length() - 1
        delta = leading_bit - fraction_bits
        retained = (
            magnitude >> delta if delta >= 0 else magnitude << -delta
        )
        fraction = retained & format_.fraction_mask
        exponent = common + delta
        normalization = f"leading_bit_{leading_bit}"
    else:
        fraction = 0
        exponent = 0
        normalization = "magnitude_zero"

    fields_fit = 0 <= exponent <= exponent_mask
    encoding = (
        (sign << format_.sign_bit) | (exponent << fraction_bits) | fraction
        if fields_fit
        else None
    )
    normal_inputs = format_.is_normal(left) and format_.is_normal(right)
    normal_result_or_cancellation = magnitude == 0 or (
        fields_fit and format_.is_normal(encoding)
    )
    comparison_domain = normal_inputs and normal_result_or_cancellation
    if comparison_domain:
        comparison_reason = "normal inputs; normal output or exact cancellation"
    elif not normal_inputs:
        comparison_reason = "zero, subnormal, or special input"
    else:
        comparison_reason = "nonzero result is outside the normal finite field"

    return {
        "difference": difference,
        "branch": branch,
        "aligned_left": aligned_left,
        "aligned_right": aligned_right,
        "common_exponent": common,
        "signed_left": signed_left,
        "signed_right": signed_right,
        "signed_sum": signed_sum,
        "result_sign": sign,
        "magnitude": magnitude,
        "normalization": normalization,
        "fraction": fraction,
        "exponent": exponent,
        "fields_fit": fields_fit,
        "encoding": encoding,
        "comparison_domain": comparison_domain,
        "comparison_reason": comparison_reason,
    }


def normal_value(byte, format_):
    if not format_.is_normal(byte):
        raise ValueError(f"{format_.name} normal encodings only")
    exponent = (byte >> format_.fraction_bits) & format_.exponent_mask
    significand = (1 << format_.fraction_bits) + (byte & format_.fraction_mask)
    shift = exponent - format_.bias - format_.fraction_bits
    magnitude = (
        Fraction(significand * (1 << shift), 1)
        if shift >= 0
        else Fraction(significand, 1 << -shift)
    )
    return -magnitude if byte & (1 << format_.sign_bit) else magnitude


def normal_positive_grid(format_):
    return [
        (normal_value(byte, format_), byte)
        for byte in range(1 << format_.sign_bit)
        if format_.is_normal(byte)
    ]


def build_e2m1_add():
    return _build_fp8_add(E2M1)


def build_e2m1_mul():
    return _build_fp8_mul(E2M1)


def build_e5m2_add():
    return _build_fp8_add(E5M2)


def build_e5m2_mul():
    return _build_fp8_mul(E5M2)


def build_e4m3_add():
    return _build_fp8_add(E4M3)


def build_e4m3_mul():
    return _build_fp8_mul(E4M3)
