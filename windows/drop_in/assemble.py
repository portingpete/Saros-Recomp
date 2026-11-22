"""Assemble the Windows kit from audited runtime inputs and pinned upstream tools."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
WINDOWS = HERE.parent
PYTHON = "9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38"
PYWIN32 = "718a38f7e5b058e76aee1c56ddd06908116d35147e133427e59a3983f703a20d"
REPAK = "6720d602144d75df477a99d5bedb6ea780997546afc335901d4937cafeaa73fa"
UNWRAP = "d5fe77f593faff316b2e513cc97582f1229789c998b7f790b1ce497d85f5e21a"
RUNTIME_SCRIPTS = (
    "drop_in/play.py", "drop_in/controls.ini", "build_display_profile.py", "recompile_guest.py",
    "guest-files.json", "30fps-environment.json", "run_milestone.py",
    "experiments/interpolation/windowed_client.py", "experiments/interpolation/build_performance_profile.py",
)
WIN32_MODULES = (
    "win32/_win32sysloader.pyd", "win32/win32api.pyd", "win32/win32gui.pyd", "win32/win32process.pyd",
    "win32/lib/pywintypes.py", "win32/lib/win32con.py", "pywin32_system32/pywintypes313.dll",
)

def verify(path, expected):
    with path.open("rb") as f:
        actual = hashlib.file_digest(f, "sha256").hexdigest()
    if actual != expected:
        raise ValueError(f"Unexpected contents of {path}: {actual}")
    return path

def assemble(a):
    manifest = json.loads(a.manifest.read_text(encoding="utf-8-sig"))
    checked = {}
    for name, sha in manifest["files"].items():
        if Path(name).name != name or Path(name).suffix.lower() not in (".prx", ".dll") or name.lower().endswith(".guest.prx"):
            raise ValueError(f"Invalid runtime module {name}")
        checked[name] = verify(a.libs / name, sha)
    for path, expected in ((a.python_zip, PYTHON), (a.pywin32, PYWIN32), (a.repak, REPAK),
                           (a.unwrap, UNWRAP), (a.relinker, manifest["relinker_sha256"])):
        verify(path, expected)
    kit = a.output.resolve()
    kit.mkdir(parents=True, exist_ok=False)
    tools = kit / "tools"
    licenses = kit / "licenses"
    libs = kit / "runtime/libs"
    libs.mkdir(parents=True)
    licenses.mkdir()
    for label, source in (("host", a.host_notices), ("renderer", a.renderer_notices)):
        if not source.is_dir() or not any(p.is_file() for p in source.rglob("*")):
            raise ValueError(f"Missing {label} notices in {source}")
        shutil.copytree(source, licenses / label)
    (kit / "Game Files").mkdir()
    for name, path in checked.items():
        shutil.copyfile(path, libs / name)
    shutil.copyfile(a.manifest, kit / "runtime/manifest.json")
    for name in RUNTIME_SCRIPTS:
        out = kit / "windows" / name
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(WINDOWS / name, out)
    with zipfile.ZipFile(a.python_zip) as python:
        python.extractall(tools / "python")
    with zipfile.ZipFile(a.pywin32) as win32:
        for name in WIN32_MODULES:
            (tools / "python" / Path(name).name).write_bytes(win32.read(name))
        (licenses / "pywin32.txt").write_bytes(win32.read("win32/license.txt"))
    with zipfile.ZipFile(a.repak) as repak:
        for name in ("LICENSE-APACHE", "LICENSE-MIT"):
            (licenses / ("repak-" + name)).write_bytes(repak.read(name))
        (tools / "repak.exe").write_bytes(repak.read("repak.exe"))
    shutil.copyfile(a.relinker, tools / "relinker.exe")
    shutil.copyfile(a.unwrap, tools / "unwrap_self.py")
    shutil.copyfile(HERE / "START.txt", kit / "START.txt")
    subprocess.run([str(a.cxx.resolve()), "-std=c++17", "-O2", "-s", "-static", "-municode",
                    "-Wl,--no-insert-timestamp", HERE / "PlaySaros.cpp", "-lshlwapi",
                    "-o", kit / "Play Saros.exe"], check=True)
    subprocess.run([tools / "python/python.exe", "-I", "-B", "-c",
                    "import win32api, win32gui, win32process, win32con, pywintypes"], check=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("output", "manifest", "libs", "relinker", "unwrap", "python-zip", "pywin32", "repak", "cxx",
                 "host-notices", "renderer-notices"):
        parser.add_argument("--" + flag, required=True, type=Path)
    assemble(parser.parse_args())
