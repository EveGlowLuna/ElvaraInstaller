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


def _service_state(name: str) -> str:
    r = subprocess.run(
        ['systemctl', 'is-active', name],
        capture_output=True, text=True, check=False,
    )
    return r.stdout.strip()


def _wait_for_reflector() -> None:
    """等待 reflector.service 结束，最多 60 秒，防止它覆盖我们写的 mirrorlist"""
    logger.info('等待 reflector.service 结束...')
    for _ in range(60):
        state = _service_state('reflector')
        if state in ('inactive', 'dead', 'failed', 'exited', ''):
            break
        time.sleep(1)
    else:
        logger.warning('reflector 超时未结束，继续安装')


def setup_mirrors() -> None:
    """等待 reflector 结束后，写入国内镜像源"""
    _wait_for_reflector()

    logger.info('=== 配置镜像源 ===')

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


def sync_pacman_db() -> None:
    """同步 pacman 包数据库，写完 mirrorlist 后必须调用"""
    logger.info('=== 同步 pacman 数据库 ===')
    for attempt in range(3):
        r = subprocess.run(['pacman', '-Sy', '--noconfirm'], capture_output=True, check=False)
        if r.returncode == 0:
            logger.info('pacman 数据库同步成功')
            return
        logger.warning(f'pacman -Sy 失败（第 {attempt + 1} 次）: {r.stderr.decode().strip()}')
        time.sleep(2)
    logger.error('pacman 数据库同步失败，安装可能出现问题')
