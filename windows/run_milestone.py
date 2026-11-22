"""Launch Saros on Windows with a measured gameplay profile."""
import argparse
import hashlib
import json
import mmap
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


def settings(text, groups=GROUPS, video=VIDEO):
    sections = {"ScalabilityGroups": groups, "/Script/Guest.GuestGameUserSettings": video}
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
    uploads = {"native-upload-scatter": "0", "native-upload-copies": "1"}
    profiles = {**dict.fromkeys(uploads, "SarosNativeFXAA"), "native-fxaa": "SarosNativeFXAA", "interpolation": "SarosInterpolated",
                "retail-interpolation": "SarosRetailInterpolation"}
    parser.add_argument("--profile", choices=profiles, help="Use a profile from the optional presentation experiment")
    args = parser.parse_args()
    play = args.play.resolve(strict=True)
    expected = json.loads((HERE / "guest-files.json").read_text(encoding="utf-8"))
    expected["app0/guest/content/paks/pakchunk0-ps5_3_P.pak"] = "c09fed1d7b8634e2f5fe7495a2230ea456e32792a472656c93bea3ff5a1957b0"
    if args.profile:
        expected["app0/guest/content/paks/pakchunk0-ps5_5_P.pak"] = "283e8065dd5ac01dc1aaf2efcdc43b0902770204ff14980278dff6b676742af6"
    for name, digest in expected.items():
        if not (play / name).is_file():
            parser.error(f"Missing installation file {name}")
        with (play / name).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                parser.error(f"Unexpected contents of {name}")
    for name in ("libs/kyty_gpu.prx", "libs/libSceAgc.prx", "libs/libSceAgcDriver.prx", "libs/libSceVideoOut.prx",
                 "app0/uecommandline.txt", "app0/guest/content/paks/pakchunk0-ps5.pak"):
        if not (play / name).is_file():
            parser.error(f"Missing installation file {name}")
    directory = play / GUEST_CONFIG.lstrip("/")
    original = directory / "gameusersettings.ini"
    groups = GROUPS.copy()
    video = VIDEO.copy()
    if args.profile:
        from experiments.interpolation.windowed_client import run_windowed
        with (play / "libs/kyty_gpu.prx").open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as image:
            if image.find(b"[rgba16s-storage]") == -1:
                parser.error("Install the renderer built with the presentation experiment patch")
            if args.profile in uploads and image.find(b"[transfer-batches]") == -1:
                parser.error("Install the renderer built with the native upload patch")
        for group in ("Shadow", "GlobalIllumination", "Reflection", "Effects"):
            groups[f"sg.{group}Quality"] = "0"
        video["bUseVSync"] = "False"
    text = settings(original.read_text(encoding="utf-8-sig") if original.exists() else "", groups, video)
    if args.check:
        print("Verified the guest images, native display profile and required launch paths.")
        return 0
    directory.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("ANYPS5_", "APS5_", "KYTY_", "SAROS_"))}
    env.update(json.loads((HERE / "30fps-environment.json").read_text(encoding="utf-8")))
    env["ANYPS5_SHADER_CACHE_DIR"] = str(play / "shader_cache")
    if args.profile:
        env.update(ANYPS5_FULLSCREEN="windowed", SAROS_EXCLUSIVE_1440P120="0", KYTY_PRESENT_MODE="immediate",
                   KYTY_GPU_THREAD_CPUS="off", KYTY_BDA_REGIONS="0", SAROS_PARALLEL_PROTECTION="1")
        if args.profile in uploads:
            env.update(SAROS_TRANSFER_BATCHES=uploads[args.profile], KYTY_IDLE_SUBMIT="1")
        if args.profile == "retail-interpolation":
            env.pop("APS5_SAROS_NATIVE_1440P", None)
    with tempfile.NamedTemporaryFile(dir=directory, prefix="saros-gameplay-", suffix=".ini", delete=False) as stream:
        config = Path(stream.name)
    try:
        config.write_text(text, encoding="utf-8")
        cmd = [play / "Saros.exe", "-NoSplash", "-NoMovie", "-ResX=2560", "-ResY=1440",
               f"-GameUserSettingsINI={GUEST_CONFIG}/{config.name}"]
        if args.profile:
            cmd.append("-DeviceProfile=" + profiles[args.profile])
            return run_windowed(cmd, play, env)
        return subprocess.run(cmd, cwd=play, env=env).returncode
    finally:
        config.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
