"""Build the native 1440p configuration overlay from a local Saros content pak."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile


CONFIG = "Guest/Config/PS5/"
PROFILES = "PS5DeviceProfiles.ini"
ENGINE = "PS5Engine.ini"
INPUT = {
    PROFILES: "a13f558e339530e88560b6f80a3bc1ad35ea8c5b2a04646b0ecb445675837cf9",
    ENGINE: "0a77f72ef697fed02c8837aa8f8cbe293406aff538871cb51069233af754f555",
}
OUTPUT = {
    PROFILES: "d1027b46543044b962b5661dfc0c96c5a2c934822cc25adce6678f88bbebed8a",
    ENGINE: "dc3c523ea1e13fc51ffc86d42bd155fa26fe878ca8566922a27205dddd96117b",
}
DISPLAY = ["r.SetRes=2560x1440f", "rhi.EnableConsole120Fps=1", "r.FidelityFX.FI.Enabled=0",
           "t.MaxFPS=120", "rhi.SyncInterval=1", "r.DynamicRes.OperationMode=0", "r.ScreenPercentage=100"]
PAK_SHA256 = "c09fed1d7b8634e2f5fe7495a2230ea456e32792a472656c93bea3ff5a1957b0"


def configure(name, data):
    if hashlib.sha256(data).hexdigest() != INPUT[name]:
        raise ValueError(f"Unrecognized local {name}")
    lines = data.decode("utf-8").splitlines()
    if name == ENGINE:
        lines.extend(["", "[SystemSettings]", DISPLAY[0], DISPLAY[1], DISPLAY[3], DISPLAY[2]])
    else:
        keys = {"+cvars=" + setting.split("=")[0].lower() for setting in DISPLAY}
        for profile in ("PS5", "PS5_Trinity", "PS5_Trinity_Turbo"):
            start = lines.index(f"[{profile} DeviceProfile]") + 1
            end = next((i for i in range(start, len(lines)) if not lines[i] or lines[i].startswith("[")), len(lines))
            keep = [line for line in lines[start:end] if line.lower().rsplit("=", 1)[0] not in keys]
            lines[start:end] = keep + ["+CVars=" + setting for setting in DISPLAY]
        lines.append("")
    output = ("\r\n".join(lines) + "\r\n").encode("utf-8-sig")
    if hashlib.sha256(output).hexdigest() != OUTPUT[name]:
        raise ValueError(f"Generated {name} differs from the measured profile")
    return output


def verify_archive(repak, pak):
    info = subprocess.check_output([repak, "info", pak], text=True).splitlines()
    required = {"mount point: ../../../", "version: V11", "encrypted index: false",
                "compression: None", "path hash seed: Some(00000000)", "2 file entries"}
    if not required.issubset(info):
        raise ValueError("The display pak has unexpected settings")
    entries = subprocess.check_output([repak, "hash-list", pak], text=True).splitlines()
    expected = {f"{digest} {CONFIG}{name}" for name, digest in OUTPUT.items()}
    if len(entries) != len(expected) or set(entries) != expected:
        raise ValueError("The display pak has unexpected entries")


def build(repak, source, dest, *, allow_equivalent=False):
    if dest.exists():
        if hashlib.sha256(dest.read_bytes()).hexdigest() == PAK_SHA256:
            return
        if allow_equivalent:
            verify_archive(repak, dest)
            return
        raise FileExistsError(f"Another file occupies {dest}")
    with tempfile.TemporaryDirectory(dir=dest.parent) as temporary:
        work = Path(temporary)
        config = work / "source" / CONFIG
        config.mkdir(parents=True)
        for name in INPUT:
            data = subprocess.check_output([repak, "get", source, CONFIG + name])
            (config / name).write_bytes(configure(name, data))
        pak = work / "profile.pak"
        subprocess.run([repak, "pack", "--version", "V11", "--mount-point", "../../../", "--path-hash-seed",
                        "0", work / "source", pak], check=True)
        if hashlib.sha256(pak.read_bytes()).hexdigest() != PAK_SHA256:
            if allow_equivalent:
                verify_archive(repak, pak)
            else:
                raise ValueError("The packed overlay differs from the measured build. Use repak 0.2.3.")
        if os.name == "nt":
            os.rename(pak, dest)
        else:
            os.link(pak, dest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repak", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True, help="Local pakchunk0-ps5.pak")
    parser.add_argument("--output", type=Path, required=True, help="Destination pakchunk0-ps5_3_P.pak")
    args = parser.parse_args()
    build(args.repak.resolve(strict=True), args.source.resolve(strict=True), args.output.resolve())
    print(f"Verified 1440p display profile at {args.output}")
