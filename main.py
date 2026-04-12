"""ElvaraOS 安装程序入口"""
import asyncio
import os
import sys


def _reexec_as_root() -> None:
    """若当前不是 root，用 sudo 重新执行自身（利用 livecd 的 NOPASSWD 配置）"""
    if os.getuid() == 0:
        return

    env_passthrough = []
    for var in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'XDG_RUNTIME_DIR'):
        if var in os.environ:
            env_passthrough += [f'{var}={os.environ[var]}']

    cmd = ['sudo']
    if env_passthrough:
        cmd += ['env'] + env_passthrough
    cmd += [sys.executable] + sys.argv

    os.execvp('sudo', cmd)


def main() -> None:
    _reexec_as_root()

    if '--cli' in sys.argv:
        from installer_cli import main as cli_main
        cli_main()
    else:
        from installer_ws import main as ws_main
        asyncio.run(ws_main())


if __name__ == '__main__':
    main()
