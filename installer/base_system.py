import subprocess
import os
import sys

# packages.txt 和可执行文件同级的 custom/ 目录里
# 打包后用 sys.executable 定位，未打包用本文件的上级目录
import sys as _sys
if getattr(_sys, 'frozen', False):
    _BASE = os.path.dirname(_sys.executable)
else:
    _BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUSTOM_PACKAGES_PATH = os.path.join(_BASE, 'custom', 'packages.txt')

# 日志回调，GUI 安装时由 setup_gui_logging 设置
_log_callback = None
_log_file_path = '/tmp/elvara_install.log'


def set_log_callback(cb):
    global _log_callback
    _log_callback = cb


def _log(msg: str):
    if _log_callback:
        _log_callback(msg)
    else:
        print(msg)
    # 同时写入日志文件
    try:
        with open(_log_file_path, 'a') as f:
            f.write(msg + '\n')
    except Exception:
        pass


import re as _re
_ANSI_ESCAPE = _re.compile(rb'\x1b\[[0-9;]*[mGKHF]|\x1b\][^\x07]*\x07|\r')


def _run(args: list, **kwargs) -> subprocess.CompletedProcess:
    """运行子进程，实时把 stdout/stderr 输出到日志，支持 \r 进度行"""
    _log(f'$ {" ".join(str(a) for a in args)}')
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **kwargs,
    )
    buf = b''
    while True:
        chunk = process.stdout.read(256)
        if not chunk:
            break
        buf += chunk
        # 按 \n 或 \r 分割，实时输出每一行
        while True:
            for sep in (b'\n', b'\r'):
                idx = buf.find(sep)
                if idx != -1:
                    raw_line = buf[:idx]
                    buf = buf[idx + 1:]
                    clean = _ANSI_ESCAPE.sub(b'', raw_line)
                    line = clean.decode('utf-8', errors='replace').strip()
                    if line:
                        _log(line)
                    break
            else:
                break
    # 输出剩余缓冲
    if buf:
        clean = _ANSI_ESCAPE.sub(b'', buf)
        line = clean.decode('utf-8', errors='replace').strip()
        if line:
            _log(line)
    process.wait()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, args)
    return process


def udevadm_settle() -> None:
    """等待内核刷新分区表"""
    _run(['sudo', 'udevadm', 'settle'])


def umount_all() -> None:
    """安装完成后卸载所有挂载点，失败则用 lazy umount 回退"""
    result = subprocess.run(['sudo', 'umount', '-R', '/mnt'], capture_output=True, text=True)
    if result.returncode != 0:
        _log('umount 失败，尝试 lazy umount...')
        if result.stderr:
            _log(result.stderr.strip())
        subprocess.run(['sudo', 'umount', '-Rl', '/mnt'], capture_output=True)


def install_base(target: str) -> None:
    default_packages = ['base', 'linux', 'linux-firmware', 'vim', 'sudo', 'grub',
                        'efibootmgr', 'networkmanager']
    try:
        with open(CUSTOM_PACKAGES_PATH) as f:
            pkgs = []
            for line in f:
                line = line.split('#')[0].strip()
                pkgs.extend(line.split())
            packages = pkgs if pkgs else default_packages
    except Exception:
        packages = default_packages

    for attempt in range(1, 4):
        try:
            _run(['sudo', 'pacstrap', '-K', target] + packages)
            return
        except subprocess.CalledProcessError:
            if attempt < 3:
                _log(f'pacstrap 第 {attempt} 次失败，10秒后重试...')
                import time
                time.sleep(10)
            else:
                raise


def generate_fstab(mount_point: str) -> None:
    _log('$ genfstab -U ' + mount_point)
    with open(f'{mount_point}/etc/fstab', 'a') as f:
        result = subprocess.run(
            ['sudo', 'genfstab', '-U', mount_point],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, check=True,
        )
        if result.stdout:
            _log(result.stdout)
        f.write(result.stdout)


def write_file(mount_point: str, path: str, content: str, mode: str = 'w') -> None:
    """直接写文件到挂载点，比通过 arch-chroot 更可靠"""
    full_path = f'{mount_point}{path}'
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    _log(f'写入 {full_path}')
    with open(full_path, mode) as f:
        f.write(content)


def arch_chroot(mount_point: str, system: list[str], out: str = '', out_mode: str = 'w'):
    args = ['sudo', 'arch-chroot', mount_point] + system
    if out == '':
        _run(args)
        return None
    else:
        # 输出重定向到文件，同时记录日志
        out_path = f'{mount_point}{out}'
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        _log(f'$ {" ".join(str(a) for a in args)} > {out_path}')
        result = subprocess.run(
            args,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, check=True,
        )
        if result.stderr:
            _log(result.stderr)
        with open(out_path, out_mode) as f:
            f.write(result.stdout)
        return None


def create_user(mount_point: str, username: str) -> None:
    """创建普通用户并加入 wheel 组，使用 zsh"""
    arch_chroot(mount_point, [
        'useradd', '-m', '-G', 'wheel', '-s', '/bin/zsh', username
    ])


def set_passwd(mount_point: str, user: str, password: str) -> None:
    # 用 stdin 传密码，避免特殊字符导致的 shell 注入
    _log(f'$ chpasswd [{user}]')
    args = ['sudo', 'arch-chroot', mount_point, 'chpasswd']
    subprocess.run(args, input=f'{user}:{password}\n', text=True, check=True)


def is_linux_tty_or_non_desktop() -> bool:
    """判断是否处于 Linux 的非图形终端环境（TTY / SSH 等）。"""
    if not sys.platform.startswith("linux"):
        return False

    # 1. 标准输入必须是一个终端（交互式）
    if not sys.stdin.isatty():
        return False

    # 2. 如果存在图形会话变量，说明在桌面环境内
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return False

    # 3. 进一步验证终端类型
    try:
        tty_name = os.ttyname(sys.stdin.fileno())
    except OSError:
        # 极少情况，取不到 tty 名，保守返回 True（因为前面已通过 isatty 且无图形变量）
        return True

    # 虚拟控制台 /dev/tty1-63 或串行控制台 /dev/ttyS*、/dev/ttyUSB* 等均视为真 TTY
    if tty_name.startswith("/dev/tty"):
        return True

    # 伪终端 /dev/pts/*：通常是 SSH 或图形终端模拟器。
    # 由于前面已经排除了 DISPLAY/WAYLAND_DISPLAY，此时 pts 多半是 SSH 会话。
    if tty_name.startswith("/dev/pts/"):
        return True

    # 其他未知类型保守返回 True
    return True


