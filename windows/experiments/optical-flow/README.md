# Saros optical frame generation on Windows

The Windows optical-flow build delivered **122.04 and 123.15 driver-reported scanouts per second** on two 30-second moving prologue routes at 2560 × 1440. The game engine advanced at **29.80 and 29.91 FPS**. The layer generated five intermediate images for each original frame. A second run with the same binaries and settings delivered **114.79 and 109.58 scanouts/s** after refresh separation. Across the four route measurements the mean was **117.39 scanouts/s**.

| Presentation method | Route | Game FPS | Vulkan presents/s | Distinct scanouts/s | Median scanout interval | 95th percentile |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Immediate submission to FIFO | Tight turn | 37.67 | 150.63 | 40.99 | 25.00 ms | 33.34 ms |
| Immediate submission to FIFO | Wide turn | 33.61 | 134.46 | 36.71 | 27.78 ms | 41.67 ms |
| Driver relative target of 8.33 ms | Tight turn | 29.43 | 117.56 | 33.16 | 33.33 ms | 47.22 ms |
| Driver relative target of 8.33 ms | Wide turn | 28.14 | 112.47 | 31.75 | 33.33 ms | 50.00 ms |
| Dedicated queue paced at 120 Hz | Tight turn | 20.10 | 80.38 | 56.75 | 16.67 ms | 33.34 ms |
| Dedicated queue paced at 120 Hz | Wide turn | 20.20 | 80.73 | 56.72 | 16.67 ms | 33.34 ms |
| Up to two presents pending | Tight turn | 29.80 | 119.22 | 84.42 | 11.11 ms | 22.22 ms |
| Up to two presents pending | Wide turn | 28.00 | 112.11 | 80.02 | 11.11 ms | 25.00 ms |
| GPU-ready, sixfold, up to two pending | Tight turn | 23.17 | 138.83 | 96.75 | 8.33 ms | 22.22 ms |
| GPU-ready, sixfold, up to two pending | Wide turn | 21.45 | 128.66 | 87.44 | 8.33 ms | 22.22 ms |
| GPU-ready, sixfold, up to four pending | Tight turn | 29.07 | 174.16 | 110.11 | 8.33 ms | 16.67 ms |
| GPU-ready, sixfold, up to four pending | Wide turn | 27.71 | 166.06 | 108.48 | 8.33 ms | 19.45 ms |
| Deferred acquisition at 180 Hz | Tight turn | 29.80 | 178.48 | 122.04 | 5.56 ms | 16.67 ms |
| Deferred acquisition at 180 Hz | Wide turn | 29.91 | 179.63 | 123.15 | 5.56 ms | 16.67 ms |
| Deferred acquisition at 240 Hz | Tight turn | 28.10 | 224.63 | 128.95 | 5.56 ms | 16.67 ms |
| Deferred acquisition at 240 Hz | Wide turn | 26.44 | 211.59 | 114.04 | 5.56 ms | 19.45 ms |
| Repeat at 180 Hz | Tight turn | 29.98 | 179.83 | 114.79 | 8.33 ms | 16.67 ms |
| Repeat at 180 Hz | Wide turn | 29.03 | 174.19 | 109.74 | 8.33 ms | 19.45 ms |
| Independent rebuild at 180 Hz | Tight turn | 29.97 | 179.85 | 114.90 | 8.33 ms | 16.67 ms |
| Independent rebuild at 180 Hz | Wide turn | 27.97 | 168.04 | 105.74 | 8.33 ms | 19.45 ms |
| Sixfold output at 200 Hz | Tight turn | 32.85 | 197.22 | 114.00 | 8.33 ms | 19.45 ms |
| Sixfold output at 200 Hz | Wide turn | 29.73 | 178.50 | 101.78 | 8.33 ms | 22.22 ms |

The independently rebuilt renderer and optical layer reached the same checkpoint, completed both movement routes and exited cleanly. The matching shader cache loaded 559 programs, 706 modules and 528 pipelines. Their refresh-separated rates were 114.90 and 105.71 scanouts/s. Raising the target to 216 Hz timed out while recycling a private output image during the tight turn. The launcher uses 180 Hz. [Build identities](source.json)

The graphics queue writes each generated image into one of twelve private 1440p images. A second queue acquires a display image when its presentation time arrives, copies the ready image into it and submits it for presentation. A GPU semaphore protects each private image until its copy finishes. At a target of 180 Hz, this raised the two-route mean from 109.29 to 122.60 scanouts/s. Eightfold generation at 240 Hz reached 128.95 on the tight turn and 114.04 on the wide turn. [Measurements](measurements.json)

The capture layer copies images on the queue that presents them. Both deferred-acquisition runs reached the checkpoint, passed movement checks and exited cleanly. The longest gap between scanouts on the sixfold run was 161.12 ms on the tight turn and 38.89 ms on the wide turn. The renderer drains issued GPU work and keeps its readback worker available during process exit. [Shutdown patch](exit-readbacks.patch)

The host was a Core i9-14900K with a GeForce RTX 5080, driver 617.14 and a 360 Hz monitor. The game rendered at 100% scale with FXAA and its own frame interpolation disabled. A separate Vulkan layer ran optical flow at a scale of 0.75. The Windows client and Vulkan images measured 2560 × 1440 on an isolated desktop. The engine rate comes from Unreal's frame counter. The Vulkan rate counts successful presentation calls. The scanout rate counts distinct positive first-pixel-out timestamps reported by the driver. That stage tracks transmission to display hardware. The driver did not expose first-pixel-visible timing. [Vulkan stage definitions](https://docs.vulkan.org/refpages/latest/refpages/source/VkPresentStageFlagBitsEXT.html)

The compressed CSV contains all 101,695 successful presents from twenty-two route windows. Present IDs select submissions that returned during movement. Return times use host QPC nanoseconds from the first guest flip. Scanout times use Vulkan stage-local nanoseconds from the earliest positive report in the same route. A numeric zero marks this origin. An empty cell denotes a complete report without a positive timestamp. Original images have index −1. [Per-present evidence](per-present.csv.gz)

On both sixfold deferred-acquisition routes, every distinct scanout timestamp was at least half a 360 Hz refresh apart. The conservative count gives the same 122.04 and 123.15 scanouts/s. Applying that filter to the eightfold trial gives 128.92 and 113.97. The verification script reproduces each rate from the per-present evidence. [Measurement script](summarize_presentations.py)

Six consecutive original and generated swapchain images from the tight turn show the moving character, scenery and HUD. All six 2560 × 1440 source images had different hashes. The contact sheet shows the images submitted to Vulkan.

![Six consecutive Saros gameplay frames from the paced output queue](consecutive-frames.jpg)

## Build and launch

Use an assembled game installation with the selectable presentation overlay, the rebuilt renderer and a prologue checkpoint. The optical layer reads the shader resource library from an existing Lossless Scaling installation. This Windows experiment was tested with MinGW-w64 GCC 15, CMake, Ninja, Vulkan-Headers 1.4.335 and the RTX 5080 driver listed above. The patch uses Vulkan present timing and present ID 2. [Saros installation and selectable profiles](../interpolation/README.md) · [Windows Vulkan layer](https://github.com/56TR/lsfg-vk-windows/blob/b03458e44eb5cc5a87537b3743f52617974e2389/WINDOWS.md) · [Lossless Scaling](https://store.steampowered.com/app/993090/LosslessScaling/)

Apply the shutdown patch to the reconstructed AnyPS5 source tree after the interpolation renderer patch, then rebuild its documented Windows renderer target. The patch changes the process-exit path in the Kyty shim. [Renderer build steps](../interpolation/README.md)

```powershell
$experiment = (Resolve-Path windows/experiments/optical-flow).Path
git -C $src apply --check "$experiment/exit-readbacks.patch"
if ($LASTEXITCODE) { throw "Renderer patch check failed" }
git -C $src apply "$experiment/exit-readbacks.patch"
if ($LASTEXITCODE) { throw "Renderer patch failed" }
```

Run these commands from the Saros-Recomp repository in a PowerShell session with the compiler, CMake and Ninja on PATH. Set VULKAN_SDK to the installed SDK directory containing Include.

```powershell
$experiment = (Resolve-Path windows/experiments/optical-flow).Path
git clone https://github.com/56TR/lsfg-vk-windows.git lsfg-vk-windows
git -C lsfg-vk-windows checkout --detach b03458e44eb5cc5a87537b3743f52617974e2389
git -C lsfg-vk-windows apply --check "$experiment/paced-output.patch"
if ($LASTEXITCODE) { throw "Optical patch check failed" }
git -C lsfg-vk-windows apply "$experiment/paced-output.patch"
if ($LASTEXITCODE) { throw "Optical patch failed" }
$env:CPATH = (Join-Path $env:VULKAN_SDK "Include")
cmake -S lsfg-vk-windows -B optical-build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=g++.exe -DLSFGVK_BUILD_UI=OFF -DLSFGVK_BUILD_CLI=OFF -DLSFGVK_BUILD_VK_LAYER=ON
if ($LASTEXITCODE) { throw "Optical layer configuration failed" }
cmake --build optical-build --target lsfg-vk-layer
if ($LASTEXITCODE) { throw "Optical layer build failed" }
python "$experiment/run_optical.py" --play "D:/Games/Saros/play" --layer "optical-build/lsfg-vk-layer/liblsfg-vk-layer.dll" --check
```

Use the same launcher command without `--check` to play. Pass `--lossless-dll` if Steam uses another library location. The launcher selects the native FXAA profile, skips the startup movies and creates a temporary layer manifest and configuration for the game process. The existing checkpoint supplies the gameplay starting point. The upstream layer and its patch use the GPL-3.0-or-later license. [Windows launcher](run_optical.py) · [Build identities](source.json) · [Upstream license](https://github.com/56TR/lsfg-vk-windows/blob/b03458e44eb5cc5a87537b3743f52617974e2389/LICENSE.md)
