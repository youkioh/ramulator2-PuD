"""One text/row manifest/symbolic C++ format for all arithmetic profiles."""
from collections import Counter
import json
from .core import validate_structure
from .lowering import PhysicalLoweredProgram

PROFILES = {
    'uint8-add': 'Exact unsigned 8+8 -> unsigned 9-bit sum.',
    'uint8-mul': 'Exact unsigned 8x8 -> unsigned 16-bit product.',
    'int8-add': 'Full exact signed 9-bit internal sum; low 8 bits exported, no saturation.',
    'int8-mul': 'Full exact signed 16-bit internal product, columns 0..15 computed; low 8 bits exported.',
    'fp8-e5m2-add': 'E5M2 bounded-alignment addition without rounding or complete special-value handling.',
    'fp8-e5m2-mul': 'E5M2 multiplication with magnitude truncation over the documented normal domain.',
    'fp8-e4m3-add': 'OFP8 E4M3 bounded-alignment addition without rounding or complete special-value handling.',
    'fp8-e4m3-mul': 'OFP8 E4M3 multiplication with magnitude truncation over the documented normal domain.',
}

def manifest(name, b):
    constants = getattr(b, 'constants', {b.zero: 0, b.one: 1})
    output = b.outputs['R']
    validate_structure(b.trace, b.inputs, constants, output)
    used = set(r for p in b.trace for r in p.rows)
    work = sorted(used - set(b.inputs) - set(constants) - set(output))
    counts = dict(sorted(Counter(p.op for p in b.trace).items()))
    return {'schema_version': 1, 'name': name, 'contract': PROFILES[name],
            'numeric_format': getattr(b, 'format_name', 'int8' if getattr(b, 'signed', False) else 'uint8'),
            'bit_order': 'LSB first', 'inputs': b.inputs, 'constants': constants,
            'output_width': len(output), 'outputs_lsb_first': output,
            'work_rows': work, 'diagnostic_taps': b.taps,
            'discarded_carry': getattr(b, 'carry_beyond_output', []),
            'column_schedule': getattr(b, 'columns', []),
            'signed_complemented_partial_products': getattr(b, 'complemented_partial_products', []),
            'cost': {'primitive_count': len(b.trace), 'primitive_counts': counts,
                     'arithmetic_core_primitives': len(b.trace)-len(output),
                     'output_copy_primitives': len(output), 'work_row_names': len(work),
                     'max_rowcopy_destinations': max((len(p.rows)-1 for p in b.trace if p.op=='RowCopy'), default=0),
                     'max_not_copy_destinations': max((len(p.rows)-1 for p in b.trace if p.op=='NOT_COPY'), default=0)},
            'stage_counts': dict(Counter(p.stage for p in b.trace)),
            'physical_allocation_and_timing': 'Not implemented; counts are logical primitive requests.'}

def write_program(name, b, directory):
    directory.mkdir(parents=True, exist_ok=True)
    info = manifest(name, b)
    lines = ['# '+name, '# '+info['contract'],
             '# Symbolic functional trace; not a simulator ABI.',
             '# RowCopy preserves source. NOT_COPY complements source AND destinations.',
             '# TRA/5RA snapshot and overwrite ALL participating rows.',
             '# Inputs: '+', '.join(b.inputs),
             '# Constants: '+json.dumps(info['constants']),
             '# Outputs LSB first: '+', '.join(info['outputs_lsb_first']),
             '# Diagnostic taps: '+json.dumps(b.taps)]
    cpp = ['// Symbolic request fragment; bind rows to legal locations before integration.',
           '// '+info['contract']]
    stage = None
    for i, p in enumerate(b.trace):
        if stage != p.stage:
            stage = p.stage
            lines.extend(['', '# '+stage])
            cpp.extend(['', '// '+stage])
        args = ', '.join(p.rows)
        lines.append(f'{i:04d}: {p.op}({args})')
        op = {'TRA':'MAJ3', '5RA':'MAJ5'}.get(p.op, p.op)
        cpp.append(f'request(Request::Type::{op}, {{{args}}}),')
    path = directory/(name+'.primitives.txt')
    path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    (directory/(name+'.requests.inc')).write_text('\n'.join(cpp)+'\n', encoding='utf-8')
    (directory/(name+'.rows.json')).write_text(json.dumps(info,indent=2)+'\n', encoding='utf-8')
    return path, info


def physical_layout_record(layout):
    """Return the reusable four-field JSON record for one physical layout."""
    return {
        "local_row_count": layout.local_row_count,
        "inputs": dict(layout.inputs),
        "constants": dict(layout.constants),
        "outputs": dict(layout.outputs),
        **({"temporary_rows": list(layout.temporary_rows)} if layout.temporary_rows is not None else {}),
    }


def write_default_physical_layout(layouts, directory):
    """Write deterministic per-profile default layouts for later reuse."""
    directory.mkdir(parents=True, exist_ok=True)
    document = {
        name: physical_layout_record(layout) for name, layout in layouts.items()
    }
    path = directory / "default-physical-layout.json"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path, document


def write_physical_program(
    name, lowered, directory, layout_provenance="caller_provided"
):
    """Write one deterministic local-row physical lowering artifact."""
    if not isinstance(lowered, PhysicalLoweredProgram):
        raise TypeError("lowered must be a PhysicalLoweredProgram")
    directory.mkdir(parents=True, exist_ok=True)
    artifact = lowered.to_dict()
    artifact = {
        "schema_version": artifact.pop("schema_version"),
        "kind": artifact.pop("kind"),
        "profile": name,
        "contract": PROFILES[name],
        "layout_provenance": layout_provenance,
        **artifact,
    }
    path = directory/(name+'.physical.json')
    path.write_text(json.dumps(artifact, indent=2)+'\n', encoding='utf-8')
    return path, artifact
