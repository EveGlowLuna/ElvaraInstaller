import shutil
import os
from installer import base_system


class CustomInstaller:
    def run(self, mount_point: str):
        # 请修改此方法来实现自定义效果。这是一个示例自定义效果（也是 ElvaraOS 最终效果），执行 customize_system.sh
        custom_dir = os.path.dirname(os.path.abspath(__file__))
        src = os.path.join(custom_dir, 'customize_system.sh')
        shutil.copy(src, f'{mount_point}/root/customize_system.sh')
        base_system.arch_chroot(mount_point, ['bash', '/root/customize_system.sh'])
        base_system.arch_chroot(mount_point, ['rm', '-rf', '/root/customize_system.sh'])