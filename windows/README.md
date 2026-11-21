# Build the Windows guest and run the milestone profile

The published 30.96 FPS milestone used Saros PPSA07631 version 01.000.000. The steps below rebuild the Windows guest executable and its 40 guest modules from your local decoded game files. The script checks every output against the recorded SHA-256 before moving it into the destination directory. Running the game also requires the Windows host libraries, renderer, your installed game assets and a save.

## Build the relinker

Use a Windows shell with Git, CMake, Ninja and a MinGW-w64 C++20 toolchain on PATH. The measured build used GCC 15.2. The relinker comes from this pinned AnyPS5 revision. [Upstream source](https://github.com/simnJS/AnyPS5/tree/35419f3c75ae73354fa551f52415cbd07c9c562c) · [Upstream build instructions](https://github.com/simnJS/AnyPS5/blob/35419f3c75ae73354fa551f52415cbd07c9c562c/docs/dev/BUILD.md)

```powershell
git clone --filter=blob:none --no-checkout https://github.com/simnJS/AnyPS5.git AnyPS5
git -C AnyPS5 checkout --detach 35419f3c75ae73354fa551f52415cbd07c9c562c
cmake -S AnyPS5 -B build-relinker -G Ninja -DANYPS5_RELINKER_ONLY=ON -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++
cmake --build build-relinker --target relinker
```

## Build the title

Use Python 3.11 or later. Point `--elf` at the decoded game executable and `--modules` at the parent directory of the decoded `prx` and `sce_module` folders. Choose a new output directory. Run the command from the root of this repository.

```powershell
python windows/recompile_guest.py --relinker build-relinker/core/relinker/relinker.exe --elf D:/Saros-input/Saros.elf --modules D:/Saros-input --output D:/Saros-Windows
```

The script recognizes the measured title by its hash, sets its two back-buffer dimensions to 2560 × 1440 in a temporary copy and runs the Intel-compatible Windows conversion with frame red zones. A successful build prints `Verified 41 Windows images`. The executable is `Saros.exe` and the modules are under `app0/prx` and `app0/sce_module`. [Output hashes](guest-files.json)

## Build the native display profile

Place your installed content under `app0` in the output directory. The overlay builder reads two configuration entries from your local content pak, sets native 2560 × 1440 rendering, disables frame generation and sets the cap to 120. It verifies both entries and the finished pak against the measured build. Use the Windows release of repak 0.2.3. [repak release](https://github.com/trumank/repak/releases/tag/v0.2.3)

```powershell
$paks = "D:/Saros-Windows/app0/guest/content/paks"
python windows/build_display_profile.py --repak D:/tools/repak.exe --source "$paks/pakchunk0-ps5.pak" --output "$paks/pakchunk0-ps5_3_P.pak"
```

## Launch the prologue

Use an assembled AnyPS5 Windows installation with the compatible host libraries under `libs`, the title's `app0/uecommandline.txt` and a copy of your own playable prologue checkpoint under `_sd`. The benchmark reused a warmed shader cache from this renderer. A first run must build its own cache. The November 20 measurement used an RTX 5080 and Core i9-14900K. [Hardware, route results and renderer identity](../benchmarks.json)

```powershell
python windows/run_milestone.py --play D:/Saros-Windows --check
python windows/run_milestone.py --play D:/Saros-Windows
```

The launcher supplies the splash and movie skip flags and enables the host's intro seek. It starts the game with four lighting and effects groups at level 1 and writes its settings to a temporary INI for the session. The game loads the progression stored in your checkpoint. The recorded average covers player movement after the prologue had loaded. [Launcher environment](30fps-environment.json)
