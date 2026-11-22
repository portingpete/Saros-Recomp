"""Verify patches against a disposable checkout, without changing its worktree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def git(repo, env, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], env=env).decode().strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('repo', type=Path, help='disposable Git checkout with public upstream commit available')
    args = ap.parse_args()
    manifest = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
    actual_files = set()
    for path in HERE.rglob('*'):
        if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
            raise SystemExit('link not permitted in payload: ' + str(path.relative_to(HERE)))
        if path.is_file() and path.relative_to(HERE).as_posix() != 'manifest.json':
            actual_files.add(path.relative_to(HERE).as_posix())
    if actual_files != set(manifest['payload_sha256']):
        raise SystemExit('payload file inventory differs from manifest')
    for name, expected in manifest['payload_sha256'].items():
        actual = hashlib.sha256((HERE / name).read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit('hash mismatch: ' + name)
    fd, index_path = tempfile.mkstemp(prefix='milestone-index-')
    os.close(fd)
    os.unlink(index_path)
    env = dict(os.environ, GIT_INDEX_FILE=index_path, GIT_CONFIG_NOSYSTEM='1')
    try:
        git(args.repo, env, 'read-tree', manifest['public_base_commit'])
        for stage in manifest['patch_stages']:
            git(args.repo, env, 'apply', '--cached', str(HERE / stage['path']))
            actual = git(args.repo, env, 'write-tree')
            if actual != stage['tree']:
                raise RuntimeError('tree mismatch at ' + stage['path'])
            print(stage['path'], actual)
        blob = git(args.repo, env, 'rev-parse', ':core/kyty/graphics/host_gpu/renderer/cache/bufferCache.cpp')
        if blob != manifest['region_buffer_source_git_blob_lf']:
            raise RuntimeError('region source mismatch')
        print('region source blob', blob)
        blob = git(args.repo, env, 'rev-parse', ':core/kyty/graphics/host_gpu/vulkanCommon.cpp')
        if blob != manifest['lds_hook_source_git_blob_lf']:
            raise RuntimeError('LDS hook source mismatch')
        print('LDS hook source blob', blob)
        blob = git(args.repo, env, 'rev-parse', ':core/libs/prx/libSceVideoOut/src/DisplayWindow.cpp')
        if blob != manifest['display_window_source_git_blob_lf']:
            raise RuntimeError('display source mismatch')
        print('display source blob', blob)
        print('PASS; headers copied/generated separately as described in README')
    finally:
        if os.path.isfile(index_path):
            os.unlink(index_path)


if __name__ == '__main__':
    main()
