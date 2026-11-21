"""Recompile a locally supplied Saros ELF and its 40 guest modules for Windows."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

CLEAN_ELF = "7340d93dc9e90a3590c00c49c73b2f26373696b29afa214aeb6fffd80e7afc24"
NATIVE_ELF = "2bf0b49a214223c949c37c9743c6a75003c079b4701b1b7c21a4928b9cea0d6c"


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def native_title(elf, output):
    image = bytearray(elf.read_bytes())
    original = hashlib.sha256(image).hexdigest()
    if original not in (CLEAN_ELF, NATIVE_ELF):
        raise ValueError(f"Unrecognized Saros ELF SHA-256 {original}")
    if original == CLEAN_ELF:
        headers = struct.unpack_from("<Q", image, 32)[0]
        stride, count = struct.unpack_from("<HH", image, 54)
        segments = [struct.unpack_from("<IIQQQQQQ", image, headers + i * stride) for i in range(count)]
        for va, old, new in [(0x20AEEE6, 3840, 2560), (0x20AEF07, 2160, 1440)]:
            matches = [s for s in segments if s[0] == 1 and s[3] <= va and va + 7 <= s[3] + s[5]]
            if len(matches) != 1:
                raise ValueError(f"Invalid segment for display initializer at {va:#x}")
            offset = matches[0][2] + va - matches[0][3]
            if image[offset:offset + 7] != bytes.fromhex("41c707") + struct.pack("<I", old):
                raise ValueError(f"Unexpected display initializer at {va:#x}")
            struct.pack_into("<I", image, offset + 3, new)
    if hashlib.sha256(image).hexdigest() != NATIVE_ELF:
        raise ValueError("The 1440p title does not match the measured input")
    output.write_bytes(image)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relinker", type=Path, required=True, help="Path to the Windows AnyPS5 relinker.exe")
    parser.add_argument("--elf", type=Path, required=True, help="Decoded ELF for PPSA07631, version 01.000.000")
    parser.add_argument("--modules", type=Path, required=True, help="Directory containing decoded prx/ and sce_module/")
    parser.add_argument("--output", type=Path, required=True, help="New directory for the verified Windows guest images")
    args = parser.parse_args()
    dest = args.output.resolve()
    if dest.exists() or not dest.parent.is_dir():
        parser.error("--output must name a new directory beneath an existing parent")
    modules = args.modules.resolve(strict=True)
    for name in ("prx", "sce_module"):
        if not (modules / name).is_dir():
            parser.error(f"Missing module directory {modules / name}")
    expected = json.loads(Path(__file__).with_name("guest-files.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(dir=dest.parent, prefix="saros-build-") as temporary:
        work = Path(temporary)
        title = work / "Saros.elf"
        native_title(args.elf, title)
        images = work / "images"
        images.mkdir()
        subprocess.run([str(args.relinker.resolve(strict=True)), "--windows", "--to-intel", "--frame-red-zone",
                        "--sce-module-path", str(modules), str(title), str(images / "Saros.exe")],
                       cwd=work, check=True)
        actual = {p.relative_to(images).as_posix(): file_hash(p) for p in images.rglob("*") if p.is_file()}
        if actual != expected:
            changes = sorted(path for path in actual.keys() | expected.keys() if actual.get(path) != expected.get(path))
            raise ValueError("Files differ from the measured Windows build: " + ", ".join(changes))
        images.rename(dest)
    print(f"Verified {len(expected)} Windows images in {dest}")


if __name__ == "__main__":
    main()
