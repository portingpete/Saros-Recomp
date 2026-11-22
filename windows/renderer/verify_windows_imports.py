"""Check declared renderer imports against this Windows installation's system DLLs."""
import ctypes
import json
from pathlib import Path
import sys

if sys.platform != 'win32':
    raise SystemExit('Windows only')
record = json.loads((Path(__file__).resolve().parent/'pe-imports.json').read_text(encoding='utf-8'))
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.GetProcAddress.argtypes = (ctypes.c_void_p, ctypes.c_char_p)
kernel.GetProcAddress.restype = ctypes.c_void_p
missing = []
loaded = []
for item in record['imports']:
    name = item['library']
    if '/' in name or '\\' in name:
        raise SystemExit('unexpected library path')
    try:
        lib = ctypes.WinDLL(name, winmode=0x800)  # LOAD_LIBRARY_SEARCH_SYSTEM32
    except OSError:
        missing.append({'library': name, 'symbol': None})
        continue
    loaded.append(lib)
    for symbol in item['symbols']:
        if not kernel.GetProcAddress(lib._handle, symbol['name'].encode('ascii')):
            missing.append({'library': name, 'symbol': symbol['name']})
result = {'libraries_checked': len(record['imports']),
          'symbols_checked': sum(len(item['symbols']) for item in record['imports']),
          'unresolved': missing,
          'scope': 'Name resolution against system32 only; no function calls or ABI-behavior test.'}
print(json.dumps(result, indent=2))
raise SystemExit(bool(missing))
