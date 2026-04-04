import subprocess
import os

CUSTOM_PACKAGES_PATH = "custom/packages.txt"

def install_base(target: str):
    default_packages = ['base', 'linux', 'linux-firmware', 'vim', 'sudo', 'grub']
    try:
        with open(CUSTOM_PACKAGES_PATH) as f:
            pkgs = []
            for line in f:
                line = line.split('#')[0].strip()  # 去掉注释和首尾空白
                pkgs.extend(line.split())
            packages = pkgs if pkgs else default_packages
    except Exception:
        packages = default_packages
    args = ['pacstrap', '-K', target] + packages
    subprocess.run(args)

def generate_fstab(mount_point: str):
    with open(f'{mount_point}/etc/fstab', 'a') as f:
        subprocess.run(['genfstab', '-U', mount_point],
                       stdout=f,
                       check=True
                       )

def arch_chroot(mount_point: str, system: list[str], out: str = "", out_mode: str = 'w'):
    args = ['sudo', 'arch-chroot', mount_point]
    for sh in system:
        args.append(sh)
    if out == "":
        res = subprocess.run(args, check=True, capture_output=True)
        return res.stdout
    else:
        with open(f'{mount_point}{out}',out_mode) as f:
            subprocess.run(args, check=True, stdout=f)
            return None

def set_passwd(mount_point: str, user: str, password: str):
    arch_chroot(mount_point, ['bash', '-c', f'echo "{user}:{password}" | chpasswd'])