"""Prepare a private Windows installation from a player's local game files and start Saros."""
import argparse
import contextlib
import ctypes
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
WINDOWS = HERE.parent
KIT = WINDOWS.parent
TOOLS = KIT / "tools"
sys.path.insert(0, str(WINDOWS))
import build_display_profile
from experiments.interpolation import build_performance_profile
from run_milestone import launch

TITLE = "PPSA07631"
VERSION = "01.000.000"
PAKS = Path("guest/content/paks")
DISPLAY = PAKS / "pakchunk0-ps5_3_P.pak"
PROFILE = PAKS / "pakchunk0-ps5_5_P.pak"
DIRECTORIES = ("engine/config", "engine/content", "guest/content", "prx", "sce_module", "sce_sys")
ROOT_FILES = ("eboot.bin", "guest/Guest.uproject", "contentids.json", "package.manifest", "uecommandline.txt")
LINKABLE_CONTENT = {".pak", ".ucas", ".utoc", ".sig", ".mp4"}

def digest(path):
    with path.open("rb") as src:
        return hashlib.file_digest(src, "sha256").hexdigest()

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def write_json(path, obj):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, mode="w", encoding="utf-8") as f:
        staging = Path(f.name)
        json.dump(obj, f, indent=2)
    try:
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)

def browse():
    from ctypes import wintypes as wt
    class BrowseInfo(ctypes.Structure):
        _fields_ = [("owner", wt.HWND), ("root", ctypes.c_void_p), ("display", wt.LPWSTR),
                    ("title", wt.LPCWSTR), ("flags", wt.UINT), ("callback", ctypes.c_void_p),
                    ("parameter", wt.LPARAM), ("image", ctypes.c_int)]
    shell = ctypes.windll.shell32
    shell.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BrowseInfo)]
    shell.SHBrowseForFolderW.restype = ctypes.c_void_p
    shell.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, wt.LPWSTR]
    ole = ctypes.windll.ole32
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    result = ole.CoInitializeEx(None, 2)
    display = ctypes.create_unicode_buffer(260)
    info = BrowseInfo(None, None, ctypes.cast(display, wt.LPWSTR),
                      "Select your Saros folder containing eboot.bin", 0x41, None, 0, 0)
    item = None
    try:
        item = shell.SHBrowseForFolderW(ctypes.byref(info))
        if not item:
            return None
        output = ctypes.create_unicode_buffer(260)
        if not shell.SHGetPathFromIDListW(item, output):
            raise ValueError("Choose a local folder containing the game files.")
        return Path(output.value)
    finally:
        if item:
            ole.CoTaskMemFree(item)
        if result in (0, 1):
            ole.CoUninitialize()

def discover(selected):
    def find(folder):
        for candidate in (folder, folder / "app0"):
            if (candidate / "eboot.bin").is_file() and (candidate / "sce_sys/param.json").is_file():
                return candidate.resolve()
        return None
    if selected:
        folder = selected.parent if selected.is_file() and selected.name.lower() == "eboot.bin" else selected
        located = find(folder) if folder.is_dir() else None
        if not located:
            raise ValueError("Select the folder containing eboot.bin and sce_sys, or drop eboot.bin onto Play Saros.")
        return located
    inbox = KIT / "Game Files"
    options = [inbox, KIT]
    if inbox.is_dir():
        options.extend(p for p in inbox.iterdir() if p.is_dir())
    matches = list(dict.fromkeys(match for option in options if (match := find(option))))
    if len(matches) == 1:
        return matches[0]
    last = KIT / "last-game.json"
    if not matches and last.is_file():
        try:
            match = find(Path(read_json(last)["folder"]))
            if match:
                return match
        except (OSError, ValueError, KeyError):
            pass
    folder = browse()
    return discover(folder) if folder else None

@contextlib.contextmanager
def exclusive(folder):
    folder.mkdir(parents=True, exist_ok=True)
    lockpath = folder / ".saros-launch.lock"
    with lockpath.open("a+b") as f:
        if f.tell() == 0:
            f.write(b"\0")
            f.flush()
        f.seek(0)
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise ValueError("Saros is already running or this installation is being prepared.") from error
        try:
            yield
        finally:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

def assets(game):
    for name in ROOT_FILES:
        yield Path(name)
    for name in DIRECTORIES:
        base = game / name
        if not base.is_dir() or base.is_symlink() or os.path.isjunction(base):
            raise ValueError(f"The game folder is missing {name}.")
        def fail(error):
            raise error
        for folder, children, filenames in os.walk(base, followlinks=False, onerror=fail):
            for child in children:
                if os.path.islink(Path(folder) / child) or os.path.isjunction(Path(folder) / child):
                    raise ValueError(f"Select the original game files. This folder is linked: {Path(folder) / child}")
            for filename in filenames:
                rel = (Path(folder) / filename).relative_to(game)
                if rel != DISPLAY and rel != PROFILE and not filename.lower().endswith(".guest.prx"):
                    yield rel

def check_content_space(game, app, workspace):
    copy_bytes = 0
    links_per_volume = {}
    with tempfile.TemporaryDirectory(dir=workspace, prefix="space-") as folder:
        probe = Path(folder) / "link"
        for rel in assets(game):
            src = game / rel
            info = src.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError(f"Expected an original game file at {src}.")
            target = app / rel
            if target.is_file() and (target.stat().st_size == info.st_size or rel.name == "uecommandline.txt"):
                continue
            if rel.suffix.lower() in LINKABLE_CONTENT and not target.exists():
                volume = info.st_dev
                if volume not in links_per_volume:
                    try:
                        os.link(src, probe)
                    except OSError as error:
                        if error.winerror not in (1, 5, 17, 50, 1314):
                            raise
                        links_per_volume[volume] = False
                    else:
                        probe.unlink()
                        links_per_volume[volume] = True
                if links_per_volume[volume]:
                    continue
            copy_bytes += info.st_size
    if copy_bytes > shutil.disk_usage(workspace).free:
        raise ValueError(f"Preparing the game content here requires {copy_bytes / (1024**3):.1f} GiB "
                         "of free space. Extract the kit on the same NTFS drive as your game files.")

def stage_assets(game, app):
    for rel in assets(game):
        source = game / rel
        target = app / rel
        st = source.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f"Expected a game file at {source}.")
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel.as_posix() == "uecommandline.txt":
            text = source.read_text(encoding="utf-8-sig").strip()
            extra = [x for x in ("-Sound", "-NoThreadTimeout", "-NoSplash", "-NoMovie", "-ResX=2560", "-ResY=1440")
                     if x.lower() not in text.lower().split()]
            content = (" ".join([text, *extra]).strip() + "\n").encode()
            if target.is_file() and target.read_bytes() == content:
                continue
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as f:
                f.write(content)
            os.replace(f.name, target)
            continue
        if target.is_file() and (os.path.samefile(source, target) or
                (target.stat().st_size, target.stat().st_mtime_ns) == (st.st_size, st.st_mtime_ns)):
            continue
        if rel.suffix.lower() in LINKABLE_CONTENT and not target.exists():
            try:
                os.link(source, target)
                continue
            except OSError as exc:
                if exc.winerror not in (1, 5, 17, 50, 1314):
                    raise
        if shutil.disk_usage(target.parent).free < st.st_size:
            raise ValueError(f"Not enough space to copy {rel}. Use an installation folder on the same NTFS drive as your original game files.")
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as f:
            temp = Path(f.name)
        try:
            shutil.copy2(source, temp)
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)

def prepare_guest(game, play, workspace):
    def decode(source, dest):
        with source.open("rb") as f:
            plain = f.read(4) == b"\x7fELF"
        if plain:
            shutil.copyfile(source, dest)
        else:
            subprocess.run([sys.executable, "-I", "-B", TOOLS / "unwrap_self.py", source, dest], check=True)
    with tempfile.TemporaryDirectory(dir=workspace, prefix="convert-") as tmp:
        work = Path(tmp)
        elf = work / "Saros.elf"
        decode(game / "eboot.bin", elf)
        for name in ("prx", "sce_module"):
            (work / name).mkdir()
            for source in sorted((game / name).glob("*.prx")):
                decode(source, work / name / source.name)
        images = work / "images"
        subprocess.run([sys.executable, "-I", "-B", WINDOWS / "recompile_guest.py",
                        "--relinker", TOOLS / "relinker.exe", "--elf", elf, "--modules", work,
                        "--output", images], check=True)
        if not play.exists():
            images.rename(play)
        else:
            for name in read_json(WINDOWS / "guest-files.json"):
                dst = play / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.replace(images / name, dst)

def install_host(play, expected):
    dst = play / "libs"
    dst.mkdir(exist_ok=True)
    for name, sha in expected.items():
        if Path(name).name != name or Path(name).suffix.lower() not in {".prx", ".dll"}:
            raise ValueError("The runtime manifest contains an invalid filename.")
        src = KIT / "runtime/libs" / name
        target = dst / name
        if target.is_file() and target.stat().st_size == src.stat().st_size and digest(target) == sha:
            continue
        with tempfile.NamedTemporaryFile(dir=dst, delete=False) as f:
            staging = Path(f.name)
        try:
            shutil.copyfile(src, staging)
            if digest(staging) != sha:
                raise ValueError(f"The release runtime file {name} failed verification. Extract the ZIP again.")
            os.replace(staging, target)
        finally:
            staging.unlink(missing_ok=True)

def run(args):
    game = discover(args.game_option or args.game)
    if not game:
        return 0
    param = read_json(game / "sce_sys/param.json")
    if (param.get("titleId"), param.get("contentVersion")) != (TITLE, VERSION):
        raise ValueError(f"This kit supports Saros {TITLE}, version {VERSION}.")
    for rel in (PAKS / "global.utoc", PAKS / "pakchunk0-ps5.pak", PAKS / "pakchunk0-ps5.ucas"):
        if not (game / rel).is_file():
            raise ValueError(f"The game folder is missing {rel}.")
    workspace = (args.workspace or KIT / "Saros Windows").resolve()
    if game.is_relative_to(workspace) or any(workspace.is_relative_to(game / name) for name in DIRECTORIES):
        raise ValueError("Keep the prepared installation separate from the original game content.")
    owner = workspace / "source.json"
    manifest = KIT / "runtime/manifest.json"
    if not manifest.is_file():
        raise ValueError("The Windows runtime is missing. Extract the complete portable release ZIP.")
    runtime = read_json(manifest)
    required = {"kyty_gpu.prx", "libSceAgcDriver.prx", "libSceVideoOut.prx", "libkernel.prx", "libc.prx"}
    if not required.issubset(runtime["files"]):
        raise ValueError("The Windows runtime manifest is incomplete.")
    expected = read_json(WINDOWS / "guest-files.json")
    if workspace.exists() and not owner.is_file() and any(p.name != ".saros-launch.lock" for p in workspace.iterdir()):
        raise ValueError(f"The installation folder already contains unrelated files: {workspace}")
    with exclusive(workspace):
        source_record = read_json(owner) if owner.is_file() else {}
        previous = source_record.get("folder")
        if previous != str(game) or "eboot_sha256" not in source_record:
            image_hash = digest(game / "eboot.bin")
            if previous and Path(previous) != game and source_record.get("eboot_sha256") != image_hash:
                raise ValueError(f"This installation belongs to different game files: {workspace}")
            write_json(owner, {"folder": str(game), "eboot_sha256": image_hash})
        play = workspace / "play"
        stamp = workspace / "prepared.json"
        receipt = read_json(stamp) if stamp.exists() else {}
        build = digest(manifest)
        files = [play / name for name in expected]
        regenerate = not all(f.is_file() for f in files) or receipt.get("guest_manifest") != digest(WINDOWS / "guest-files.json")
        if args.check and not regenerate:
            regenerate = any(digest(play / name) != sha for name, sha in expected.items())
        if not stamp.is_file() or args.check:
            check_content_space(game, play / "app0", workspace)
        if regenerate:
            print("Preparing the Windows game files. This runs once.", flush=True)
            prepare_guest(game, play, workspace)
        paks = play / "app0" / PAKS
        paks.mkdir(parents=True, exist_ok=True)
        stage_assets(game, play / "app0")
        complete = (not regenerate and receipt.get("runtime") == build and
                    all((play / "libs" / name).is_file() for name in runtime["files"]) and
                    all((play / "app0" / rel).is_file() for rel in (DISPLAY, PROFILE, PAKS / "global.utoc")))
        if not complete or args.check:
            print("Preparing the game content and native 1440p profile.", flush=True)
            repak = TOOLS / "repak.exe"
            with tempfile.TemporaryDirectory(dir=paks) as folder:
                display = Path(folder) / DISPLAY.name
                performance = Path(folder) / PROFILE.name
                build_display_profile.build(repak, game / PAKS / "pakchunk0-ps5.pak", display, allow_equivalent=True)
                build_performance_profile.build(repak, display, performance, "selectable")
                os.replace(display, play / "app0" / DISPLAY)
                os.replace(performance, play / "app0" / PROFILE)
            print("Verifying the bundled Windows runtime.", flush=True)
            install_host(play, runtime["files"])
            write_json(stamp, {"runtime": build, "guest_manifest": digest(WINDOWS / "guest-files.json")})
        controls = play / "anyps5-input.ini"
        if not controls.exists():
            shutil.copyfile(HERE / "controls.ini", controls)
        if not args.workspace:
            try:
                write_json(KIT / "last-game.json", {"folder": str(game)})
            except OSError:
                pass
        if args.prepare_only or args.check:
            print(f"Saros is ready in {play}", flush=True)
            return 0
        print("Starting Saros. First launch may take several minutes to compile shaders.", flush=True)
        print("On the first-run screens, hold Enter or the controller confirm button to continue.", flush=True)
        environment = dict(runtime.get("environment", {}))
        for variable, relative in (("LOCALAPPDATA", "Local"), ("APPDATA", "Roaming"),
                                   ("USERPROFILE", "Profile"), ("TEMP", "Temp"), ("TMP", "Temp")):
            folder = workspace / "state" / relative
            folder.mkdir(parents=True, exist_ok=True)
            environment[variable] = str(folder)
        with (workspace / "last-game.log").open("w", encoding="utf-8") as log:
            status = launch(play, "native-upload-scatter", env_overrides=environment, display_mode=args.display, output=log)
        if status:
            raise RuntimeError(f"Saros exited with code 0x{status & 0xffffffff:08x}. See {workspace / 'last-game.log'}")
        return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", type=Path, nargs="?", help="Game folder or eboot.bin")
    parser.add_argument("--game", dest="game_option", type=Path, help="Game folder or eboot.bin")
    display = parser.add_mutually_exclusive_group()
    display.add_argument("--fullscreen", dest="display", action="store_const", const="borderless",
                         help="Fill the monitor with a borderless window")
    display.add_argument("--windowed", dest="display", action="store_const", const="windowed",
                         help="Use the measured 2560 by 1440 client size (default)")
    parser.set_defaults(display="windowed")
    parser.add_argument("--workspace", "--build-dir", type=Path, help="Use a separate installation folder")
    parser.add_argument("--prepare-only", action="store_true", help="Prepare the game without starting it")
    parser.add_argument("--check", action="store_true", help="Verify and repair the prepared installation")
    args = parser.parse_args()
    if args.game and args.game_option:
        parser.error("Use one game path.")
    try:
        raise SystemExit(run(args))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        message = str(error)
        print(f"Could not start Saros. {message}", file=sys.stderr, flush=True)
        if not (args.prepare_only or args.check or args.workspace):
            ctypes.windll.user32.MessageBoxW(None, message, "Saros", 0x10)
        raise SystemExit(1)
