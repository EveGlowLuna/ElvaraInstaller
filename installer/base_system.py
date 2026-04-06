import subprocess
import os

# 相对于本文件所在目录定位 packages.txt，打包后也能找到
_HERE = os.path.dirname(os.path.abspath(__file__))
CUSTOM_PACKAGES_PATH = os.path.join(os.path.dirname(_HERE), 'custom', 'packages.txt')

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


def _run(args: list, **kwargs) -> subprocess.CompletedProcess:
    """运行子进程，实时把 stdout/stderr 输出到日志"""
    _log(f'$ {" ".join(str(a) for a in args)}')
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        **kwargs,
    )
    output_lines = []
    for line in process.stdout:
        line = line.rstrip('\n')
        output_lines.append(line)
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
    _run(['sudo', 'pacstrap', '-K', target] + packages)


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
