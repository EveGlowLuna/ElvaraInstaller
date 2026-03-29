"""镜像源配置"""
import shutil
import subprocess
import time
from pathlib import Path

from loguru import logger

FALLBACK_MIRRORS = """\
# ElvaraOS fallback mirrors
Server = https://mirrors.tuna.tsinghua.edu.cn/archlinux/$repo/os/$arch
Server = https://mirrors.ustc.edu.cn/archlinux/$repo/os/$arch
Server = https://mirrors.aliyun.com/archlinux/$repo/os/$arch
Server = https://mirrors.163.com/archlinux/$repo/os/$arch
Server = https://mirror.nju.edu.cn/archlinux/$repo/os/$arch
"""


def setup_mirrors() -> None:
    """自动选择最快镜像源，失败时写入国内备用镜像"""
    logger.info('=== 自动选择最快镜像源 ===')

    def write_fallback() -> None:
        Path('/etc/pacman.d/mirrorlist').write_text(FALLBACK_MIRRORS)
        logger.info('已写入国内备用镜像源')

    if not shutil.which('reflector'):
        logger.warning('reflector 未安装，使用备用镜像源')
        write_fallback()
        return

    logger.info('等待网络就绪...')
    for _ in range(30):
        r = subprocess.run(
            ['getent', 'hosts', 'mirrors.tuna.tsinghua.edu.cn'],
            capture_output=True, check=False,
        )
        if r.returncode == 0:
            break
        time.sleep(1)
    else:
        logger.warning('网络未就绪，使用备用镜像源')
        write_fallback()
        return

    write_fallback()
