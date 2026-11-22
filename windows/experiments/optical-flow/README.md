# Saros optical frame generation on Windows

The optical-flow layer reached an average of **56.73 distinct driver-reported scanouts per second** across two moving prologue routes at 2560 × 1440. The game advanced **20.15 frames per second**. The layer generated three intermediate images per game frame. Waiting for their presentation improved display delivery and slowed the game simulation.

| Presentation method | Route | Game FPS | Vulkan presents/s | Distinct scanouts/s | Median scanout interval | 95th percentile |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Immediate submission to FIFO | Tight turn | 37.67 | 150.63 | 40.99 | 25.00 ms | 33.34 ms |
| Immediate submission to FIFO | Wide turn | 33.61 | 134.46 | 36.71 | 27.78 ms | 41.67 ms |
| Driver relative target of 8.33 ms | Tight turn | 29.43 | 117.56 | 33.16 | 33.33 ms | 47.22 ms |
| Driver relative target of 8.33 ms | Wide turn | 28.14 | 112.47 | 31.75 | 33.33 ms | 50.00 ms |
| Dedicated queue paced at 120 Hz | Tight turn | 20.10 | 80.38 | 56.75 | 16.67 ms | 33.34 ms |
| Dedicated queue paced at 120 Hz | Wide turn | 20.20 | 80.73 | 56.72 | 16.67 ms | 33.34 ms |

The patched layer spaces the generated and original images on a second Vulkan queue in the same graphics family. On the measured build it releases all four images before returning from each game present. Tight-turn scanout rose by 15.76 frames/s and wide-turn scanout rose by 20.01. Waiting on a group also raised the median engine frame interval to roughly 50 ms. These measurements cover the existing prologue checkpoint, with the player running and the camera turning for 30 seconds per route. Each trial closed cleanly. [Measurements](measurements.json)

The host was a Core i9-14900K with a GeForce RTX 5080, driver 617.14 and a 360 Hz monitor. The game rendered at 100% scale with FXAA and its own frame interpolation disabled. A separate Vulkan layer ran optical flow at a scale of 0.75. The Windows client and Vulkan images measured 2560 × 1440 on an isolated desktop. The engine rate comes from Unreal's frame counter. The Vulkan rate counts successful presentation calls. The scanout rate counts distinct positive first-pixel-out timestamps reported by the driver. That stage tracks transmission to display hardware. The driver did not expose first-pixel-visible timing. [Vulkan stage definitions](https://docs.vulkan.org/refpages/latest/refpages/source/VkPresentStageFlagBitsEXT.html)

The compressed CSV contains all 20,304 successful presents from the six route windows. Times are nanoseconds relative to the start of each route. An empty scanout timestamp represents a complete report with a zero timestamp. The generated-image index runs from 0 to 2 and the original image has index −1. Across the two paced routes the driver returned positive timestamps for 3,406 of 4,836 presentations. [Per-present evidence](per-present.csv.gz)

Six consecutive original and generated swapchain images from the tight turn show the moving character, scenery and HUD. All six 2560 × 1440 source images had different hashes. The contact sheet shows the images submitted to Vulkan.

![Six consecutive Saros gameplay frames from the paced output queue](consecutive-frames.jpg)

## Build and launch

Use an assembled game installation with the selectable presentation overlay, the rebuilt renderer and a prologue checkpoint. The optical layer reads the shader resource library from an existing Lossless Scaling installation. This Windows experiment was tested with MinGW-w64 GCC 15, CMake, Ninja, Vulkan-Headers 1.4.335 and the RTX 5080 driver listed above. The patch uses Vulkan present timing and present ID 2. [Saros installation and selectable profiles](../interpolation/README.md) · [Windows Vulkan layer](https://github.com/56TR/lsfg-vk-windows/blob/b03458e44eb5cc5a87537b3743f52617974e2389/WINDOWS.md) · [Lossless Scaling](https://store.steampowered.com/app/993090/LosslessScaling/)

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
