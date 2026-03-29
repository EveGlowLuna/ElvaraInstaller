"""核心安装流程"""
from pathlib import Path

from loguru import logger

from archinstall.lib.disk.filesystem import FilesystemHandler
from archinstall.lib.hardware import SysInfo
from archinstall.lib.installer import Installer
from archinstall.lib.models.bootloader import BootloaderConfiguration
from archinstall.lib.models.device import DiskLayoutConfiguration
from archinstall.lib.models.locale import LocaleConfiguration
from archinstall.lib.models.users import User

from install.customization import apply_livecd_customizations
from install.disk import umount_target
from install.mirrors import setup_mirrors, sync_pacman_db

GNOME_PACKAGES = [
    # GNOME 核心
    'gnome-shell', 'gnome-session', 'gnome-settings-daemon',
    'gnome-control-center', 'gnome-keyring', 'gdm',
    'xdg-desktop-portal-gnome', 'xdg-user-dirs-gtk',
    'gvfs', 'gvfs-mtp', 'gvfs-gphoto2',
    # GNOME 应用
    'nautilus', 'gnome-terminal', 'gnome-tweaks',
    'gnome-disk-utility', 'gnome-system-monitor',
    'gnome-text-editor', 'gnome-calculator',
    'gnome-font-viewer', 'gnome-logs', 'loupe', 'baobab',
    'file-roller', 'evince',
    # 主题 / 壁纸
    'gnome-backgrounds', 'gnome-themes-extra', 'adwaita-icon-theme',
    # 字体
    'noto-fonts-cjk', 'adobe-source-han-sans-cn-fonts',
    'ttf-dejavu', 'ttf-liberation',
    # 输入法
    'fcitx5', 'fcitx5-gtk', 'fcitx5-qt',
    'fcitx5-chinese-addons', 'fcitx5-configtool', 'fcitx5-im',
    # 音频
    'pipewire', 'pipewire-pulse', 'wireplumber',
    # 蓝牙
    'bluez', 'bluez-utils',
    # 网络
    'networkmanager', 'xdg-utils',
    # 图形
    'mesa', 'libglvnd', 'librsvg',
    # 启动动画
    'plymouth',
    # 内存保护
    'earlyoom',
    # 常用应用
    'vlc', 'firefox',
    # 游戏支持
    'lutris', 'wine', 'wine-gecko', 'wine-mono', 'gamemode',
    # Shell
    'zsh', 'grml-zsh-config',
    # 系统工具
    'git', 'vim', 'nano', 'sudo', 'lvm2',
    'zram-generator', 'reflector',
]


def perform_installation(
    disk_layout_config: DiskLayoutConfiguration,
    hostname: str,
    timezone: str,
    locale_config: LocaleConfiguration,
    user: User,
    kernels: list[str] | None = None,
    mountpoint: Path = Path('/mnt'),
) -> None:
    """执行完整安装流程"""
    uefi = SysInfo.has_uefi()
    bootloader_config = BootloaderConfiguration.get_default(uefi)

    setup_mirrors()
    sync_pacman_db()
    umount_target(mountpoint)

    logger.info('=== 创建文件系统 ===')
    fs_handler = FilesystemHandler(disk_layout_config)
    fs_handler.perform_filesystem_operations()

    logger.info('=== 开始安装系统 ===')
    with Installer(
        target=mountpoint,
        disk_config=disk_layout_config,
        kernels=kernels or ['linux-zen'],
        silent=True,  # 后台线程中不能交互，失败直接抛异常
    ) as installation:
        installation.mount_ordered_layout()

        # 等待 NTP、reflector、keyring 同步（与 archinstall 原版一致）
        installation.sanity_check()

        installation.minimal_installation(
            hostname=hostname,
            locale_config=locale_config,
        )

        logger.info('=== 安装 GNOME 桌面环境 ===')
        installation.add_additional_packages(GNOME_PACKAGES)

        installation.enable_service(['gdm', 'NetworkManager', 'bluetooth', 'earlyoom'])
        installation.set_timezone(timezone)
        installation.activate_time_synchronization()

        # 配置 zram（包已在 GNOME_PACKAGES 中，这里写配置并启用服务）
        installation.setup_swap()

        logger.info(f'=== 安装引导加载程序 ({bootloader_config.bootloader.value}) ===')
        installation.add_bootloader(
            bootloader=bootloader_config.bootloader,
            uki_enabled=bootloader_config.uki,
            bootloader_removable=bootloader_config.removable,
        )

        installation.create_users(user)
        apply_livecd_customizations(mountpoint, user.username)
        _install_yay(mountpoint)
        _install_amber_store(mountpoint)
        installation.enable_service('systemd-resolved')
        installation.genfstab()

    logger.success('✅ 安装完成！')


def _aur_build(mountpoint: Path, pkg_url: str, pkg_dir: str) -> bool:
    """
    通用 AUR 构建辅助：在新系统内 clone → makepkg → pacman -U。
    使用临时用户 builduser 避免 nobody 权限问题。
    返回 True 表示成功。
    """
    import subprocess

    build_home = mountpoint / 'tmp/aurbuild'
    build_home.mkdir(parents=True, exist_ok=True)
    build_home.chmod(0o777)

    pkg_path = f'/tmp/aurbuild/{pkg_dir}'

    # 确保 builduser 存在（useradd 幂等）
    subprocess.run(
        ['arch-chroot', str(mountpoint),
         'bash', '-c',
         'id builduser &>/dev/null || useradd -m -d /tmp/aurbuild builduser'],
        check=False,
    )
    subprocess.run(
        ['arch-chroot', str(mountpoint),
         'chown', '-R', 'builduser:builduser', '/tmp/aurbuild'],
        check=False,
    )

    # clone
    r = subprocess.run(
        ['arch-chroot', str(mountpoint),
         'sudo', '-u', 'builduser',
         'git', 'clone', '--depth=1', pkg_url, pkg_path],
        capture_output=True,
    )
    if r.returncode != 0:
        logger.warning(f'clone {pkg_url} 失败: {r.stderr.decode().strip()}')
        return False

    # makepkg
    r = subprocess.run(
        ['arch-chroot', str(mountpoint),
         'sudo', '-u', 'builduser',
         'bash', '-c', f'cd {pkg_path} && makepkg --noconfirm --needed -s'],
        capture_output=True,
    )
    if r.returncode != 0:
        logger.warning(f'makepkg {pkg_dir} 失败: {r.stderr.decode().strip()}')
        return False

    # pacman -U
    r = subprocess.run(
        ['arch-chroot', str(mountpoint),
         'bash', '-c', f'pacman -U --noconfirm {pkg_path}/*.pkg.tar.zst'],
        capture_output=True,
    )
    if r.returncode != 0:
        logger.warning(f'pacman -U {pkg_dir} 失败: {r.stderr.decode().strip()}')
        return False

    return True


def _install_yay(mountpoint: Path) -> None:
    """从 AUR 构建并安装 yay"""
    import subprocess

    logger.info('=== 安装 yay (AUR helper) ===')

    # go 缓存目录
    go_cache = mountpoint / 'build/go-cache'
    go_cache.mkdir(parents=True, exist_ok=True)
    go_cache.chmod(0o777)

    # builduser 需要能写 go cache
    subprocess.run(
        ['arch-chroot', str(mountpoint),
         'bash', '-c',
         'id builduser &>/dev/null || useradd -m -d /tmp/aurbuild builduser'],
        check=False,
    )
    subprocess.run(
        ['arch-chroot', str(mountpoint),
         'chown', '-R', 'builduser:builduser', '/build'],
        check=False,
    )
    # 允许 builduser 免密调用 pacman（makepkg -s 需要）
    sudoers_file = mountpoint / 'etc/sudoers.d/builduser-tmp'
    sudoers_file.write_text('builduser ALL=(ALL) NOPASSWD: /usr/bin/pacman\n')
    sudoers_file.chmod(0o440)

    ok = _aur_build(
        mountpoint,
        'https://aur.archlinux.org/yay.git',
        'yay',
    )

    # 清理 go cache（节省空间）
    subprocess.run(
        ['arch-chroot', str(mountpoint), 'rm', '-rf', '/build/go-cache'],
        check=False,
    )

    if ok:
        logger.info('yay 安装成功')
    else:
        logger.warning('yay 安装失败，跳过（不影响主安装流程）')


def _install_amber_store(mountpoint: Path) -> None:
    """
    安装星火应用商店（amber-pm-store）。
    依赖链：amber-package-manager → amber-pm-store
    先用 yay 安装（如果 yay 可用），失败则手动 clone PKGBUILD 构建。
    """
    import subprocess

    logger.info('=== 安装星火应用商店 (amber-pm-store) ===')

    # 优先用 yay（已安装时最简单）
    r = subprocess.run(
        ['arch-chroot', str(mountpoint),
         'bash', '-c',
         'which yay && sudo -u builduser yay -S --noconfirm amber-pm-store'],
        capture_output=True,
    )
    if r.returncode == 0:
        logger.info('amber-pm-store 通过 yay 安装成功')
        return

    logger.warning('yay 安装 amber-pm-store 失败，尝试手动构建...')

    # 手动构建：先装 amber-package-manager，再装 amber-pm-store
    for pkg, url in [
        ('amber-package-manager', 'https://aur.archlinux.org/amber-package-manager.git'),
        ('amber-pm-store',        'https://aur.archlinux.org/amber-pm-store.git'),
    ]:
        ok = _aur_build(mountpoint, url, pkg)
        if not ok:
            logger.warning(f'{pkg} 手动构建失败，跳过星火应用商店安装')
            return

    logger.info('amber-pm-store 手动构建安装成功')

    # 清理构建目录和临时用户
    subprocess.run(
        ['arch-chroot', str(mountpoint), 'rm', '-rf', '/tmp/aurbuild'],
        check=False,
    )
    subprocess.run(
        ['arch-chroot', str(mountpoint), 'userdel', '-r', 'builduser'],
        check=False,
    )
    sudoers_file = mountpoint / 'etc/sudoers.d/builduser-tmp'
    sudoers_file.unlink(missing_ok=True)
