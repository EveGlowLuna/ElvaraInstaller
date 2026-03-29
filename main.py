"""ElvaraOS 安装程序入口"""
import os
import sys


def _reexec_as_root() -> None:
    """若当前不是 root，用 sudo 重新执行自身（利用 livecd 的 NOPASSWD 配置）"""
    if os.getuid() == 0:
        return

    # 保留 DISPLAY / WAYLAND_DISPLAY / XAUTHORITY，让 GUI 能正常弹出
    env_passthrough = []
    for var in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'XDG_RUNTIME_DIR'):
        if var in os.environ:
            env_passthrough += [f'{var}={os.environ[var]}']

    cmd = ['sudo']
    if env_passthrough:
        cmd += ['env'] + env_passthrough
    cmd += [sys.executable] + sys.argv

    os.execvp('sudo', cmd)  # 替换当前进程，不返回


def main() -> None:
    _reexec_as_root()

    cli_mode = '--cli' in sys.argv

    if cli_mode:
        from installer import main as cli_main
        cli_main()
    else:
        from installer_gui import main as gui_main
        gui_main()


if __name__ == '__main__':
    main()
