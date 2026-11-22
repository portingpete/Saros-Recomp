"""Generate the native display helper from the locally recompiled Saros.exe."""
import argparse
import hashlib
from pathlib import Path
import re
import struct


GUEST = "6bd1ce70dea706e606aa49133166cd523e6317d559e71dbfa3d9e0117303f0b4"
HEADER = "eaba042ec62b43998c86e1216afe06521e89d51e7fba8a283069ad016509310d"


def generate(exe, output):
    image = exe.read_bytes()
    if hashlib.sha256(image).hexdigest() != GUEST:
        raise ValueError("Expected the verified native 1440p Windows guest")
    pe, = struct.unpack_from("<I", image, 60)
    sections, = struct.unpack_from("<H", image, pe + 6)
    optional_size, = struct.unpack_from("<H", image, pe + 20)
    optional = pe + 24
    if image[pe:pe + 4] != b"PE\0\0" or struct.unpack_from("<H", image, optional)[0] != 0x20b:
        raise ValueError("Expected a PE32+ executable")
    base, = struct.unpack_from("<Q", image, optional + 24)
    table = optional + optional_size
    ranges = [struct.unpack_from("<III", image, table + 40 * i + 12) for i in range(sections)]

    def instruction(match):
        rva = int(match[1], 16) - base
        offsets = [raw + rva - start for start, size, raw in ranges if start <= rva and rva + 7 <= start + size]
        if len(offsets) != 1:
            raise ValueError("Display setting check is outside the guest image")
        code = image[offsets[0]:offsets[0] + 7]
        sep = ", " if match[2] == "spaced" else ","
        return sep.join(f"0x{byte:02x}" for byte in code)

    template = Path(__file__).with_name("SarosNativeScale.hpp.in").read_text(encoding="utf-8")
    source, count = re.subn(r"@guest_([0-9a-f]{8})_(spaced|compact)@", instruction, template)
    header = source.replace("\n", "\r\n").encode("utf-8")
    if count != 12 or hashlib.sha256(header).hexdigest() != HEADER:
        raise ValueError("Generated native display header differs from the measured source")
    if output.is_file() and output.read_bytes() == header:
        return
    with output.open("xb") as stream:
        stream.write(header)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.guest, args.output)
    print(f"Verified native display header at {args.output}")
