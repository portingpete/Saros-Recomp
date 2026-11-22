# Private LDS reconstruction

Distribute only `generate_lds.py`, `choose-lds-phases.py`, `prove-lds-footprints.py`, and this README. **Do not include generated output, shader modules, assembly, caches, test outputs, or a generated `SarosLds.h` in a source-only distribution.** The header contains compiled replacement shader words and the disassembly and generated module contain game-derived shader data. Generate these only in a private directory from the user's own module.

## Inputs

- The exact original SPIR-V module, supplied privately by the user; SHA-256 `6cd3bcf93c0a0f72855a0d979a5643618377cc3841ac71fa8055d2f21e4f1835`. Other modules fail closed.
- Python 3.10 or newer and the `xxhash` Python package.
- SPIR-V Tools `spirv-dis` and `spirv-val`, and the SPIR-V Headers `spirv.core.grammar.json`. Tools and grammar are supplied by the user; they are not included here. The proof expects the identifier naming and instruction format produced by the locally tested disassembler. Different versions may fail its strict assertions.

The original module is the sole shader input. The generator does not require a shader store, the prebuilt replacement module, a generated header, compression, a game launch, or network access. Obtaining the module from the user's own setup is outside this generator.

## Invocation

```text
python -B generate_lds.py --module /private/original.spv \
  --grammar /tools/spirv.core.grammar.json \
  --spirv-dis /tools/spirv-dis --spirv-val /tools/spirv-val \
  --private-output /private/generated-lds
```

Choose platform-appropriate executable names and paths. The private output directory receives `private-input.asm`, `private-generated.spv`, and `SarosLds.h`; the generator refuses to overwrite any existing file with those names. The script validates the exact source hash, disassembles, checks per-invocation shared-memory footprints and control-flow/overwrite conditions, constructs the private-array and scratch-handoff replacement, validates it for Vulkan 1.3 with uniform-buffer-standard-layout, and emits an instruction-diff based header. The header guards the input and output with word counts and XXH3-128 hashes. A compatible `xxhash.h` is needed later to compile that header. The source generator alone does not integrate it into a renderer.

For the measured input, the output header SHA-256 on the tested Windows environment is `64de36dda6e1303e424d343684780459e9a39f132024e7aca867edacc7d678a6`, and the generated module SHA-256 is `b8cecafa801b8515166527965b9ab8a5c8498cd84c162e2c23deb973552baa16`. Header line endings may change its byte hash on other platforms. Strict checks apply to this one module, not arbitrary shaders; validator acceptance and static proof do not independently establish all runtime correctness or performance.
