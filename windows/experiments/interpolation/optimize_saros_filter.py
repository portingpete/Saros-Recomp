"""Rebuild the prologue filter in a Windows AnyKyty shader cache.

Uses Python 3.14, xxhash, and the SPIRV-Tools disassembler, assembler and
validator. Accepts a stock cache or a cache already using the requested variant.
"""

import argparse
from compression import zstd
import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

import xxhash


SHADER = 0x89AFD9E77DC00730
STOCK = '0e394e9d96a23ac75c257fec3a7108702c8a3690f3e7ec731ca032406902072b'
GUARDED_STOCK = '7d2e0f6433df6adc7396d11e02170691b1e6a9b6fd20c70ec535441c74a4f336'
VARIANTS = {
    'bounded': '6c18d7749618e2b3201e1c4ba5b695f1ff50e1e8dfd9da46af424be5ebf2f9ac',
    'hoisted': 'a127d5e751245e5caf067abbbb0301defd748067bfac83df4bda3b50854a5e2a',
    'guarded-hoisted': '47a9308a94204ab453f006941580ccb55c428cf6939189f84a82ef5b593bb6ad',
}
FRAME = struct.Struct('<IIQ')
# The raw module hash pins these SSA IDs to the verified eight-tap filter.
# Each tuple identifies the first comparison, the resulting lower bound,
# the count, the key, and the end of the exact-match/default selection.
SEARCHES = [
    (1705, 1845, 1704, 1661, 1861), (1911, 2051, 1910, 1632, 2067),
    (2088, 2228, 2087, 1622, 2244), (2508, 2648, 2507, 1642, 2664),
    (2803, 2943, 2802, 1651, 2959), (2980, 3120, 2979, 1593, 3136),
    (3218, 3358, 3217, 1612, 3374), (3396, 3536, 3395, 1602, 3552),
]
HELPER = """
%search = OpFunction %uint None %search_type
%mapping_param = OpFunctionParameter %uint
%count_param = OpFunctionParameter %uint
%key_param = OpFunctionParameter %uint
%search_entry = OpLabel
OpBranch %search_head
%search_head = OpLabel
%search_lo = OpPhi %uint %uint_0 %search_entry %next_lo %search_step
%search_hi = OpPhi %uint %count_param %search_entry %next_hi %search_step
%search_active = OpULessThan %bool %search_lo %search_hi
OpLoopMerge %search_end %search_step DontUnroll
OpBranchConditional %search_active %search_body %search_end
%search_body = OpLabel
%search_width = OpISub %uint %search_hi %search_lo
%half_width = OpShiftRightLogical %uint %search_width %uint_1
%search_mid = OpIAdd %uint %search_lo %half_width
%double_mid = OpShiftLeftLogical %uint %search_mid %uint_1
%relative_key = OpIAdd %uint %double_mid %uint_1
%key_index = OpIAdd %uint %mapping_param %relative_key
%candidate_pointer = OpAccessChain %_ptr_StorageBuffer_uint %50 %uint_0 %key_index
%candidate_key = OpLoad %uint %candidate_pointer
%search_less = OpULessThan %bool %candidate_key %key_param
%after_mid = OpIAdd %uint %search_mid %uint_1
%next_lo = OpSelect %uint %search_less %after_mid %search_lo
%next_hi = OpSelect %uint %search_less %search_hi %search_mid
OpBranch %search_step
%search_step = OpLabel
OpBranch %search_head
%search_end = OpLabel
OpReturnValue %search_lo
OpFunctionEnd
"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def compile_filter(stock, variant, directory):
    if digest(stock) != STOCK:
        raise ValueError('Unrecognized input SPIR-V')
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        shader, assembly = work/'filter.spv', work/'filter.spvasm'
        shader.write_bytes(stock)

        def run(name, *args):
            exe = shutil.which(name, path=directory)
            if exe is None:
                raise FileNotFoundError(name)
            env = dict(os.environ, PATH=str(Path(exe).parent) + os.pathsep + os.environ['PATH'])
            subprocess.run([exe, *args], check=True, env=env)

        run('spirv-dis', shader, '-o', assembly)
        lines = assembly.read_text().splitlines()
        definitions = {l.split()[0]: i for i, l in enumerate(lines) if ' = ' in l}
        preheader = next(i for i, l in enumerate(lines) if l.strip() == 'OpBranch %65')
        first_function = next(i for i, l in enumerate(lines) if ' = OpFunction ' in l)
        insertions = {first_function: ['%search_type = OpTypeFunction %uint %uint %uint %uint']}
        removed = set()
        for slot, (start, lower, count, key, result) in enumerate(SEARCHES):
            begin = definitions[f'%{start}']
            end = definitions[f'%{result}'] + 1
            mapping = f'%uint_{52 + 513 * slot}'
            if not (definitions[f'%{key}'] < preheader < begin and
                    lines[begin].split()[2:] == ['OpULessThan', '%bool', '%uint_0', f'%{count}'] and
                    lines[begin-2].split()[4:] == ['%50', '%uint_0', mapping]):
                raise ValueError(f'Unexpected search structure in slot {slot}')
            # Each of the nine unrolled binary-search steps has 16 operations.
            after_steps = begin + 9 * 16
            call = f'%{lower} = OpFunctionCall %uint %search {mapping} %{count} %{key}'
            replacement = [*lines[begin-2:begin], call, *lines[after_steps:end]]
            removed.update(range(begin-2, end))
            location = preheader if variant == 'hoisted' else begin-2
            insertions.setdefault(location, []).extend(replacement)
        output = []
        for i, line in enumerate(lines):
            output.extend(insertions.get(i, ()))
            if i not in removed:
                output.append(line)
        output.append(HELPER)
        assembly.write_text('\n'.join(output) + '\n')
        run('spirv-as', '--target-env', 'spv1.3', assembly, '-o', shader)
        run('spirv-val', '--target-env', 'vulkan1.3', '--uniform-buffer-standard-layout', shader)
        compiled = shader.read_bytes()
        if digest(compiled) != VARIANTS[variant]:
            raise ValueError('The assembled shader differs from the validated game benchmark')
        return compiled


def compile_guarded_filter(installed, directory, guard_header, cxx):
    if digest(installed) != GUARDED_STOCK:
        raise ValueError('Expected the stock filter from the guarded renderer')
    # This build adds six global declarations and two loop-exit checks. Recover
    # the logical input to the guard so it can charge the rewritten loop bodies.
    # Both complete module hashes and a forward round trip protect the offsets.
    original = bytearray(installed)
    for first, last in ((37752, 37908), (12228, 12384), (5860, 5960)):
        del original[first:last]
    struct.pack_into('<I', original, 12, 4406)  # original SPIR-V ID bound
    optimized = compile_filter(bytes(original), 'hoisted', directory)

    source = Path(__file__).with_name('apply_loop_guard.cpp')
    compiler = shutil.which(cxx)
    if not compiler:
        raise FileNotFoundError(f'C++20 compiler {cxx!r} was not found')
    env = dict(os.environ, PATH=str(Path(compiler).parent) + os.pathsep + os.environ['PATH'])
    for name in ('KYTY_LOOP_FUEL', 'KYTY_LOOP_FUEL_MIN', 'KYTY_LOOP_FUEL_RAY_WALKS'):
        env.pop(name, None)
    with tempfile.TemporaryDirectory() as temp:
        helper = Path(temp) / 'apply_loop_guard.exe'
        subprocess.run([compiler, '-std=c++20', '-O2', '-I', guard_header.parent,
                        source, '-o', helper], check=True, env=env)
        def guard(module):
            framed = struct.pack('<I', len(module) // 4) + module
            result = subprocess.run([helper], input=framed, stdout=subprocess.PIPE, check=True, env=env).stdout
            if len(result) < 4 or struct.unpack_from('<I', result)[0] * 4 != len(result) - 4:
                raise ValueError('Incomplete result from the production guard')
            return result[4:]
        if guard(original) != installed:
            raise ValueError('Current guard settings do not reproduce the input module')
        guarded = guard(optimized)
        if digest(guarded) != VARIANTS['guarded-hoisted']:
            raise ValueError('Guarded filter differs from the verified module')
        return guarded


def replace_shader(data, variant, directory, guard_header=None, cxx='g++'):
    # After the store header, Kyty writes length/raw size/XXH3 followed by a Zstd frame.
    pos = data.index(bytes.fromhex('28b52ffd')) - FRAME.size
    if pos < 8:
        raise ValueError('Invalid native store header')
    result = bytearray(data[:pos])
    found = total = 0
    while pos < len(data):
        compressed, raw_size, checksum = FRAME.unpack_from(data, pos)
        end = pos + FRAME.size + compressed
        payload = data[pos + FRAME.size:end]
        if end > len(data) or xxhash.xxh3_64_intdigest(payload) != checksum:
            raise ValueError(f'Invalid store checksum in record {total}')
        record = zstd.decompress(payload)
        if len(record) != raw_size:
            raise ValueError(f'Invalid size in record {total}')
        frame = data[pos:end]
        if record[0] == 0 and struct.unpack_from('<Q', record, 5)[0] == SHADER:
            # This module's SPIR-V vector is followed by an empty plain-variant vector.
            magic = bytes.fromhex('03022307')
            matches = []
            cursor = 4
            while (offset := record.find(magic, cursor)) >= 0:
                words = struct.unpack_from('<I', record, offset - 4)[0]
                if offset + words * 4 == len(record) - 4 and record[-4:] == bytes(4):
                    matches.append(offset)
                cursor = offset + 4
            if len(matches) != 1:
                raise ValueError('Unrecognized target module layout')
            offset = matches[0]
            stock = record[offset:-4]
            if digest(stock) != VARIANTS[variant]:
                if variant == 'guarded-hoisted':
                    if guard_header is None:
                        guard_header = Path(__file__).resolve().parents[1] / 'build-loopfuel/subsync/SpirvLoopFuel.h'
                    shader = compile_guarded_filter(stock, directory, guard_header, cxx)
                else:
                    shader = compile_filter(stock, variant, directory)
                record = record[:offset-4] + struct.pack('<I', len(shader)//4) + shader + record[-4:]
                payload = zstd.compress(record, level=3)
                frame = FRAME.pack(len(payload), len(record), xxhash.xxh3_64_intdigest(payload)) + payload
            found += 1
        result.extend(frame)
        total += 1
        pos = end
    if found != 1:
        raise ValueError(f'Expected one matching module, found {found}')
    return bytes(result), total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cache', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--variant', choices=VARIANTS, default='hoisted')
    parser.add_argument('--spirv-tools', help='Directory containing spirv-dis, spirv-as, and spirv-val')
    parser.add_argument('--cxx', default=os.environ.get('CXX', 'g++'), help='C++20 compiler for the guarded renderer')
    parser.add_argument('--guard-header', type=Path, help='Path to the production SpirvLoopFuel.h')
    args = parser.parse_args()
    if args.cache.resolve() == args.output.resolve():
        parser.error('Choose a separate output path to preserve the input cache')
    data, records = replace_shader(args.cache.read_bytes(), args.variant, args.spirv_tools, args.guard_header, args.cxx)
    with args.output.open('xb') as out:
        try:
            out.write(data)
            out.flush()
        except OSError:
            out.close()
            args.output.unlink(missing_ok=True)
            raise
    print(f'{records} records, shader {SHADER:016x}, {args.variant}, output SHA-256 {digest(data)}')


if __name__ == '__main__':
    main()
