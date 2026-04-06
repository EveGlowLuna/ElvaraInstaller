import shutil
import subprocess
import os
import sys

from installer import base_system

_RESULT_FILE = '/tmp/elvara_desktop_choice'


def run(mount_point: str, username: str) -> None:
    desktop_env = _pick_desktop()

    shorin_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shorin-arch-setup')
    shorin_dst = os.path.join(mount_point, 'root', 'shorin-arch-setup')

    if os.path.exists(shorin_dst):
        shutil.rmtree(shorin_dst)
    shutil.copytree(shorin_src, shorin_dst)

    compat = os.path.join(shorin_src, 'scripts', 'chroot-compat.sh')
    subprocess.run(['bash', compat, mount_point, username, desktop_env], check=True)

    base_system.arch_chroot(mount_point, ['bash', '/root/run-shorin.sh'])

    # 清理
    shutil.rmtree(shorin_dst, ignore_errors=True)
    for f in [os.path.join(mount_point, 'root', 'run-shorin.sh'), _RESULT_FILE]:
        try:
            os.remove(f)
        except FileNotFoundError:
            pass


def _pick_desktop() -> str:
    # 可执行文件和 custom.py 在同一目录
    custom_dir = os.path.dirname(os.path.abspath(__file__))
    picker = os.path.join(custom_dir, 'desktop_picker')
    subprocess.run([picker, _RESULT_FILE], check=True)
    try:
        with open(_RESULT_FILE) as f:
            return f.read().strip() or 'none'
    except FileNotFoundError:
        return 'none'
