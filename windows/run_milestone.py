"""Start an assembled Windows installation with the 30.96 FPS milestone settings."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
GUEST_CONFIG = "/download0/guest/saved/ps5"
GROUPS = {"sg." + key + "Quality": value for key, value in {
    "Resolution": "0", "ViewDistance": "3", "AntiAliasing": "1", "Shadow": "1",
    "GlobalIllumination": "1", "Reflection": "1", "PostProcess": "3", "Texture": "3",
    "Effects": "1", "Foliage": "3", "Shading": "3", "Landscape": "3",
}.items()}
VIDEO = {
    "bUseVSync": "True", "bUseDynamicResolution": "False", "FrameRateLimit": "120.000000",
    "ResolutionSizeX": "2560", "ResolutionSizeY": "1440", "LastUserConfirmedResolutionSizeX": "2560",
    "LastUserConfirmedResolutionSizeY": "1440", "FullscreenMode": "1", "LastConfirmedFullscreenMode": "1",
    "PreferredFullscreenMode": "1",
}


def settings(text):
    sections = {"ScalabilityGroups": GROUPS, "/Script/Guest.GuestGameUserSettings": VIDEO}
    added = set()
    skip = set()
    lines = []
    for line in text.splitlines():
        clean = line.strip()
        if clean.startswith("[") and clean.endswith("]"):
            section = clean[1:-1]
            values = sections.get(section, {})
            skip = {k.casefold() for k in values}
            lines.append(line)
            if section not in added:
                lines.extend(f"{k}={v}" for k, v in values.items())
                added.add(section)
        elif clean.partition("=")[0].strip().casefold() not in skip:
            lines.append(line)
    for section, values in sections.items():
        if section not in added:
            lines.extend(["", f"[{section}]", *(f"{k}={v}" for k, v in values.items())])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--play", type=Path, required=True, help="Installation containing Saros.exe, libs and app0")
    parser.add_argument("--check", action="store_true", help="Verify the launch inputs and exit")
    args = parser.parse_args()
    play = args.play.resolve(strict=True)
    expected = json.loads((HERE / "guest-files.json").read_text(encoding="utf-8"))
    expected["app0/guest/content/paks/pakchunk0-ps5_3_P.pak"] = "c09fed1d7b8634e2f5fe7495a2230ea456e32792a472656c93bea3ff5a1957b0"
    for name, digest in expected.items():
        with (play / name).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                parser.error(f"Unexpected contents of {name}")
    for name in ("libs/kyty_gpu.prx", "libs/libSceAgc.prx", "libs/libSceAgcDriver.prx", "libs/libSceVideoOut.prx",
                 "app0/uecommandline.txt", "app0/guest/content/paks/pakchunk0-ps5.pak"):
        if not (play / name).is_file():
            parser.error(f"Missing installation file {name}")
    directory = play / GUEST_CONFIG.lstrip("/")
    original = directory / "gameusersettings.ini"
    text = settings(original.read_text(encoding="utf-8-sig") if original.exists() else "")
    if args.check:
        print("Verified the guest images, native display profile and required launch paths.")
        return 0
    directory.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("ANYPS5_", "APS5_", "KYTY_", "SAROS_"))}
    env.update(json.loads((HERE / "30fps-environment.json").read_text(encoding="utf-8")))
    env["ANYPS5_SHADER_CACHE_DIR"] = str(play / "shader_cache")
    with tempfile.NamedTemporaryFile(dir=directory, prefix="saros-30fps-", suffix=".ini", delete=False) as stream:
        config = Path(stream.name)
    try:
        config.write_text(text, encoding="utf-8")
        cmd = [play / "Saros.exe", "-NoSplash", "-NoMovie", "-ResX=2560", "-ResY=1440",
               f"-GameUserSettingsINI={GUEST_CONFIG}/{config.name}"]
        return subprocess.run(cmd, cwd=play, env=env).returncode
    finally:
        config.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
