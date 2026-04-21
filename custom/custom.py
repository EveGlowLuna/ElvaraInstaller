import shutil
import subprocess
import os
import json

from installer import base_system

_RESULT_FILE = '/tmp/elvara_desktop_choice'


class CustomInstaller:
    def run(self, mount_point: str) -> None:
        desktop_env = _pick_desktop()

        shorin_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shorin-arch-setup')
        shorin_dst = os.path.join(mount_point, 'root', 'shorin-arch-setup')

        if os.path.exists(shorin_dst):
            shutil.rmtree(shorin_dst)
        shutil.copytree(shorin_src, shorin_dst, symlinks=True)

        # 写入 setup-config.json（新版接口）
        config = {
            'desktop_env': desktop_env,
            'optional_modules': ['gpu', 'grub', 'apps'],
            'mirror': 'cn',
            'grub_theme': '1CyberGRUB-2077',
            'flatpak_mirror': 'ustc',
        }
        config_path = os.path.join(mount_point, 'tmp', 'setup-config.json')
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        # 运行 customize_system.sh
        customize_sh = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'customize_system.sh')
        customize_dst = os.path.join(mount_point, 'root', 'customize_system.sh')
        shutil.copy(customize_sh, customize_dst)
        base_system.arch_chroot(mount_point, ['bash', '/root/customize_system.sh'])

        # 运行 install.sh
        base_system.arch_chroot(mount_point, ['bash', '/root/shorin-arch-setup/install.sh'])

        # 清理
        shutil.rmtree(shorin_dst, ignore_errors=True)
        for f in [config_path, _RESULT_FILE,
                  os.path.join(mount_point, 'tmp', 'shorin_install_user'),
                  os.path.join(mount_point, 'root', 'customize_system.sh')]:
            try:
                os.remove(f)
            except FileNotFoundError:
                pass


def _pick_desktop() -> str:
    custom_dir = os.path.dirname(os.path.abspath(__file__))
    picker = os.path.join(custom_dir, 'desktop_picker')
    subprocess.run([picker, _RESULT_FILE], check=True)
    try:
        with open(_RESULT_FILE) as f:
            return f.read().strip() or 'none'
    except FileNotFoundError:
        return 'none'
