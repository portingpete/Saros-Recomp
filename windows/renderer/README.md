# Build the Windows renderer

This reconstructs the renderer used for the 30.96 FPS Saros milestone. A Windows build of the five source patches and the two privately generated headers linked successfully and passed the renderer ABI check. The measured renderer begins with SHA-256 `04f7bb0c`. The rebuilt renderer begins with `d9104c28`. The historical performance measurement applies to the first binary. [Measured build](../../benchmarks.json) · [Patch trees and input hashes](manifest.json)

## Prepare the source

Use PowerShell, Git and Python 3.11 or later. Run these commands from the root of Saros-Recomp. Choose an empty directory outside this repository for the source, build and generated data.

```powershell
$pkg = (Resolve-Path windows/renderer).Path
$work = "D:/Saros-renderer"
$src = "$work/AnyPS5"
git clone --no-checkout https://github.com/simnJS/AnyPS5.git $src
git -C $src -c core.autocrlf=false checkout --detach 35419f3c75ae73354fa551f52415cbd07c9c562c
python -B "$pkg/verify.py" $src
if ($LASTEXITCODE) { throw "Source verification failed" }
$stages = (Get-Content "$pkg/manifest.json" -Raw | ConvertFrom-Json).patch_stages
foreach ($stage in $stages) {
    git -C $src -c core.autocrlf=false apply --index "$pkg/$($stage.path)"
    if ($LASTEXITCODE) { throw "Patch failed at $($stage.path)" }
}
git -C $src submodule update --init --recursive
$index = "core/kyty/graphics/host_gpu/renderer/cache/regionBufferIndex.h"
Copy-Item "$pkg/files/$index" "$src/$index"
```

The patches cover the benchmark fork, the source snapshot, the region buffer index, the shader hook and the display window. The verifier checks the SHA-256 of each supplied file and the Git tree after each patch. The dependency inventory lists upstream revisions and license notices. Some original test fixtures and generated title data were omitted. [Dependency inventory](dependencies.json) · [Omitted paths](excluded-paths.json) · [License notices](licenses/)

## Generate the two headers

Use the verified Windows guest from the title build and the original shader module from your own installation. The module SHA-256 starts with `6cd3bcf9`. The generator needs the Python `xxhash` package, SPIR-V Tools and its JSON grammar. Set the input and tool paths to their locations on your machine. Both generated headers matched the historical inputs byte for byte on Windows. [Title build](../README.md) · [Shader generation and validation](lds/README.md)

```powershell
python -B "$pkg/lds/generate_lds.py" --module D:/private/original.spv --grammar "$src/3rdparty/SPIRV-Headers/include/spirv/unified1/spirv.core.grammar.json" --spirv-dis D:/tools/spirv-dis.exe --spirv-val D:/tools/spirv-val.exe --private-output "$work/private-lds"
if ($LASTEXITCODE) { throw "Shader generation failed" }
Copy-Item "$work/private-lds/SarosLds.h" "$src/core/kyty/graphics/host_gpu/SarosLds.h"
python -B "$pkg/display/generate_native_scale.py" --guest D:/Saros-Windows/Saros.exe --output "$src/core/libs/prx/libSceVideoOut/src/SarosNativeScale.hpp"
```

## Compile the renderer

The successful renderer build used CMake 4.3.1, Ninja 1.13.2 and llvm-mingw Clang 23.1.5, LLVM revision `392dfff97d29b59d77e5cac6d4b6ef2585fe7117`. Add the toolchain to PATH and supply its compiler paths to CMake. The target produces `$work/build-renderer/kyty_gpu.prx`.

```powershell
$llvm = "D:/tools/llvm-mingw/bin"
$env:PATH = "$llvm;$env:PATH"
$flags = @(
    "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_TESTING=OFF",
    "-DCMAKE_C_COMPILER=$llvm/x86_64-w64-mingw32-clang.exe",
    "-DCMAKE_CXX_COMPILER=$llvm/x86_64-w64-mingw32-clang++.exe",
    "-DANYPS5_SOURCE_DIR=$src", "-DKYTY_THIN_LTO=OFF",
    "-DKYTY_DLL=ON", "-DKYTY_DLL_THIN_LTO=ON", "-DKYTY_DLL_PGO=OFF",
    "-DKYTY_PGO_PROFILE=$src/core/kyty/pgo/kyty_gpu.proftext"
)
cmake -S "$src/core/kyty" -B "$work/build-renderer" -G Ninja @flags
if ($LASTEXITCODE) { throw "Renderer configuration failed" }
cmake --build "$work/build-renderer" --target kyty_gpu_dll_bundle --parallel 2
```

The DLL uses ThinLTO and a shared upstream profile. The indexed profile matched the historical build, and CMake reported 68 changed files and 14 new files since training. The original build assembled its final archive in a separate relink. The reconstruction used local copies of upstream dependencies. The outer host configured with GCC 15.2 and a replacement FFmpeg package whose codec header differed from the historical header. The nested renderer build above can be run independently. [Build evidence](configure-evidence.json)

The region-index fixture matched 600,000 ordered range comparisons. The import inventory covers 364 symbols in 20 Windows libraries. Run `python -B windows/renderer/verify_windows_imports.py` on Windows to check symbol availability locally. [PE import inventory](pe-imports.json)
