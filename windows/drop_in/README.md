# Windows drop-in launcher

A player extracts the assembled kit, drops their original Saros folder onto **Play Saros.exe**, and uses the same executable on subsequent launches. Double-clicking the executable also accepts a folder through the Windows folder chooser. The supported input is a decrypted dump of PPSA07631 version 01.000.000. The launcher generates the Windows guest and both profile overlays from that input. It stores the prepared game, saves, settings and game logs in the kit's **Saros Windows** folder by default.

The launcher supports drag-and-drop and these arguments.

```text
Play Saros.exe [game folder or eboot.bin]
Play Saros.exe --game PATH [--build-dir PATH] [--fullscreen | --windowed]
Play Saros.exe --game PATH --prepare-only
Play Saros.exe --game PATH --check
```

Preparing on the same NTFS volume lets Windows hard-link immutable game archives and movies. On different volumes, first launch needs space for a second copy. The launcher checks available space before staging, verifies the generated images, and retains settings and saves across subsequent launches. The windowed default requests a 2560 × 1440 client. Fullscreen uses the host's borderless display mode.

## Building a kit

The packaging script accepts a manifest with flat host library filenames and their SHA-256 digests under `files`, a digest under `relinker_sha256`, and optional per-game launch variables under `environment`. Use the host and renderer notices for the particular binaries being assembled. Corresponding-source archives and their build instructions belong alongside the release. The existing v0.1.0 download is the original source and launcher kit.

The assembler checks the pinned Python, pywin32 and repak archives and the original LF-encoded unwrap script before extraction. It compiles the small Windows entry point with MinGW and checks imports using the embedded interpreter.

| Packaging input | Source |
| --- | --- |
| Windows x64 embedded Python 3.13.17 | [Python embeddable ZIP](https://www.python.org/ftp/python/3.13.17/python-3.13.17-embed-amd64.zip) |
| pywin32 311, cp313, win_amd64 | [pywin32 release files](https://pypi.org/project/pywin32/311/#files) |
| repak CLI v0.2.3, x86_64 Windows MSVC | [repak release](https://github.com/trumank/repak/releases/tag/v0.2.3) |
| AnyPS5 unwrap script | [Pinned source](https://github.com/simnJS/AnyPS5/blob/35419f3c75ae73354fa551f52415cbd07c9c562c/tools/unwrap_self.py) |

```powershell
python windows/drop_in/assemble.py --help
```
