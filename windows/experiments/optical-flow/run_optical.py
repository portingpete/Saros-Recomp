"""Launch the 1440p prologue with per-game Vulkan optical frame generation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import tomllib


NAME = "VK_LAYER_LSFGVK_frame_generation"
PROFILE = "Saros native input"


def windows_dll(value):
    path = Path(value).expanduser().resolve()
    try:
        with path.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ValueError
            stream.seek(60)
            pe_offset = struct.unpack("<I", stream.read(4))[0]
            stream.seek(pe_offset)
            if stream.read(6) != b"PE\0\0\x64\x86":
                raise ValueError
            stream.seek(pe_offset + 22)
            if not struct.unpack("<H", stream.read(2))[0] & 0x2000:
                raise ValueError
    except (ValueError, OSError, struct.error) as exc:
        raise argparse.ArgumentTypeError(f"Expected a 64-bit Windows DLL at {path}") from exc
    return path


def prepend(value, entry):
    existing = [part for part in value.split(os.pathsep) if part and part.casefold() != entry.casefold()]
    return os.pathsep.join([entry, *existing])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--play", type=Path, required=True, help="Game installation with the selectable presentation profile")
    parser.add_argument("--layer", required=True, type=windows_dll, help="Locally built lsfg-vk Windows layer")
    default = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam/steamapps/common/Lossless Scaling/Lossless.dll"
    parser.add_argument("--lossless-dll", type=windows_dll, default=str(default), help="Lossless.dll from your Steam installation")
    parser.add_argument("--check", action="store_true", help="Verify launch inputs and exit")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This launcher requires Windows")
    manifest = {
        "file_format_version": "1.1.0",
        "layer": {
            "name": NAME, "description": "Lossless Scaling frame generation layer",
            "implementation_version": "2", "type": "GLOBAL", "api_version": "1.4.328",
            "library_path": str(args.layer), "disable_environment": {"DISABLE_LSFGVK": "1"},
        },
    }
    config = (
        'version = 2\n[global]\n'
        f'dll = {json.dumps(args.lossless_dll.as_posix(), ensure_ascii=False)}\n'
        'allow_fp16 = true\n[[profile]]\n'
        f'name = "{PROFILE}"\n'
        'active_in = ["Saros.exe"]\nmultiplier = 4\nflow_scale = 0.75\n'
        'performance_mode = true\npacing = "none"\n'
    )
    launcher = Path(__file__).resolve().parents[2] / "run_milestone.py"
    with tempfile.TemporaryDirectory(prefix="saros-optical-") as directory:
        work = Path(directory)
        config_path = work / "saros.toml"
        manifest_path = work / "VkLayer_LSFGVK_frame_generation.json"
        config_path.write_text(config, encoding="utf-8")
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        env = os.environ.copy()
        env.pop("DISABLE_LSFGVK", None)
        env.update(
            VK_LAYER_PATH=prepend(env.get("VK_LAYER_PATH", ""), directory),
            VK_INSTANCE_LAYERS=prepend(env.get("VK_INSTANCE_LAYERS", ""), NAME),
            LSFGVK_CONFIG=str(config_path), LSFGVK_PROFILE=PROFILE,
        )
        cmd = [sys.executable, "-B", str(launcher), "--play", str(args.play), "--profile", "native-fxaa"]
        if args.check:
            if Path(tomllib.loads(config_path.read_text(encoding="utf-8"))["global"]["dll"]) != args.lossless_dll:
                parser.error("Lossless Scaling DLL path did not round-trip through TOML")
            if Path(json.loads(manifest_path.read_bytes())["layer"]["library_path"]) != args.layer:
                parser.error("Layer DLL path did not round-trip through JSON")
            with args.layer.open("rb") as stream:
                print(f"Verified the optical-flow layer {hashlib.file_digest(stream, 'sha256').hexdigest()}", flush=True)
            cmd.append("--check")
        return subprocess.run(cmd, env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
