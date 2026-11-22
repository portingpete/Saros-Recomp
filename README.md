# Saros on Windows

[![Saros prologue gameplay showing the character running in circles while the camera turns](media/prologue.gif)](https://portingpete.github.io/Saros-Recomp/)

[Watch the prologue recording and see the latest movement benchmark](https://portingpete.github.io/Saros-Recomp/).

This project tracks a Windows recompile using [AnyPS5](https://github.com/boykopovar/AnyPS5). The target is 120 FPS at a native render resolution of 2560 × 1440. Terra measures two 30-second prologue routes with simultaneous character movement and camera rotation. Each 10 FPS gain in their combined average gets a new recording and benchmark entry.

## Run the native 1440p release

The Windows kit includes the launcher, renderer build patches, profile generators and benchmark evidence for Saros PPSA07631 version 01.000.000. It works with the assembled native AnyPS5 Windows installation and supports starting a new game. [Download the native 1440p release](https://github.com/portingpete/Saros-Recomp/releases/tag/v0.1.0-native-1440p)

The benchmark renderer averaged **41.02 FPS**, then **38.51 FPS** on a repeat. The independently built renderer averaged **39.76 FPS** with a warm cache. All three results cover the same two moving prologue routes at 2560 × 1440, 100% internal scale, with FXAA enabled and frame generation disabled. [Route timings and renderer hashes](windows/experiments/native-uploads/measurements.json)

Install Python 3.11 or newer and pywin32. Extract the kit to its own folder. Run these commands there, substituting the path to the installation containing your `Saros.exe` and `libs` folder. The first command checks the launch inputs. The second skips startup movies and starts the game.

```powershell
.\Run-Saros-Native-1440p.cmd --play "D:\Saros-Windows" --check
.\Run-Saros-Native-1440p.cmd --play "D:\Saros-Windows"
```

To assemble the guest and renderer, generate the title-specific files locally from your own installation. The renderer build uses an original shader module from a matching local shader cache. The [host file manifest](windows/native-host-sha256.json) identifies all 419 libraries in the tested install. Terra also started the installed native renderer with empty save and shader-cache folders, held Cross for about three seconds on each first-run prompt, then walked, turned the camera and strafed in the Movement & Camera tutorial. [Fresh-start evidence](windows/experiments/native-uploads/fresh-start.json) [Guest build](windows/README.md) · [Native renderer, overlays and gameplay evidence](windows/experiments/native-uploads/README.md)

## Other rendering experiments

A separate frame-interpolation experiment produced 66.16 completed flips per second at native 1440p while the game advanced 33.11 frames per second. The benchmark includes both moving routes, six consecutive swapchain images and the renderer source changes. [Interpolation results and build instructions](windows/experiments/interpolation/README.md)

The Windows optical-flow build at 2560 × 1440 reached 122.04 and 123.15 driver-reported scanouts per second on the two moving routes. The game engine advanced at 29.80 and 29.91 FPS with five generated images per original frame. Repeating those routes with the same build produced 114.79 and 109.58 refresh-separated scanouts per second. [Display timing, source patch and launcher](windows/experiments/optical-flow/README.md)

The Windows build scripts reproduce the executable, all 40 guest modules and the native display configuration from your local game files. The 30.96 FPS milestone includes its measured settings and a launcher for an assembled installation.

[Build and launch instructions](windows/README.md) · [Measured milestones](benchmarks.json) · [Movement video](media/prologue.mp4)
