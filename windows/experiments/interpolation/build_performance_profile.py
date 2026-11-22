"""Build the measured Saros performance profile from the local 1440p display overlay."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

ENTRY = "Guest/Config/PS5/PS5DeviceProfiles.ini"
INPUT = "d1027b46543044b962b5661dfc0c96c5a2c934822cc25adce6678f88bbebed8a"
PAKS = {
    "native-fxaa": "430e671e050ded1f5a6c3f32684f13f7ec3df14a940c9699aef764271c88a59f",
    "interpolation": "a74e247081009eeb51ab97e1af643504d38b53f99597364492c49381c2c8dfa8",
    "retail-interpolation": "512e87a78790f0a34b0dc4e35552372260188ff40a3ad84da22c7ba986ad4cac",
    "selectable": "283e8065dd5ac01dc1aaf2efcdc43b0902770204ff14980278dff6b676742af6",
}

def configure(data, mode):
    if hashlib.sha256(data).hexdigest() != INPUT:
        raise ValueError("Expected the display profile produced by windows/build_display_profile.py")
    newline = b"\r\n" if b"\r\n" in data else b"\n"
    marker = b"[DeviceProfiles]"
    profiles = {"SarosPerformance": mode}
    if mode == "selectable":
        profiles = {
            "SarosPerformance": "standard", "SarosNativeFXAA": "native-fxaa",
            "SarosInterpolated": "interpolation", "SarosRetailInterpolation": "retail-interpolation",
        }
    registrations = [f"+DeviceProfileNameAndTypes={name},PS5".encode() for name in profiles]
    registered = data.replace(marker, newline.join([marker, *registrations]), 1)
    lines = []
    for name, variant in profiles.items():
        lines.extend((
            "", f"[{name} DeviceProfile]", "DeviceType=PS5", "BaseProfileName=PS5",
            "+CVars=Hmq.Reflections.Trace.RTMode=0", "+CVars=r.RDG.AsyncCompute=0",
        ))
        if variant == "native-fxaa":
            lines.append("+CVars=r.AntiAliasingMethod=1")
        if variant in ("interpolation", "retail-interpolation"):
            lines.append("+CVars=r.FidelityFX.FI.Enabled=1")
        if variant == "retail-interpolation":
            lines.extend((
                "+CVars=r.DynamicRes.OperationMode=2", "+CVars=r.DynamicRes.MinScreenPercentage=41.666",
                "+CVars=r.DynamicRes.MaxScreenPercentage=60", "+CVars=r.ScreenPercentage=60",
            ))
    return registered.rstrip(b"\r\n") + newline + newline.join(line.encode() for line in lines) + newline


def build(repak, source, destination, mode):
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() == PAKS[mode]:
            return
        raise FileExistsError(f"Another file occupies {destination}")
    profile = configure(subprocess.check_output([repak, "get", source, ENTRY]), mode)
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        root = Path(tmp)
        config = root / "src" / ENTRY
        config.parent.mkdir(parents=True)
        config.write_bytes(profile)
        pak = root / "profile.pak"
        subprocess.run([repak, "pack", "--version", "V11", "--mount-point", "../../../",
                        "--path-hash-seed", "0", root / "src", pak], check=True)
        if hashlib.sha256(pak.read_bytes()).hexdigest() != PAKS[mode]:
            raise ValueError("Packed output differs from the measured profile. Check the repak version.")
        if os.name == "nt":
            os.rename(pak, destination)
        else:
            os.link(pak, destination)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repak", type=Path, required=True)
    parser.add_argument("--display-profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=PAKS, required=True)
    args = parser.parse_args()
    build(args.repak.resolve(strict=True), args.display_profile.resolve(strict=True), args.output.resolve(), args.mode)
    print(f"Verified {args.mode} profile at {args.output}")
