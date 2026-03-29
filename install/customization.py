"""将 LiveCD 定制内容复制并应用到新系统"""
import os
import shutil
import subprocess
from pathlib import Path

from loguru import logger

# ElvaraOS os-release（与 airootfs/etc/os-release 保持一致）
_OS_RELEASE = """\
NAME="ElvaraOS"
PRETTY_NAME="ElvaraOS"
ID=elvara
ID_LIKE=arch
HOME_URL="https://github.com/EveGlowLuna/ElvaraOS"
LOGO=elvara
"""

# zram 配置（与 airootfs/etc/systemd/zram-generator.conf 保持一致）
_ZRAM_CONF = """\
[zram0]
zram-size = ram / 2
compression-algorithm = zstd
swap-priority = 100
fs-type = swap
"""


def apply_livecd_customizations(mountpoint: Path, username: str) -> None:
    """将 LiveCD 中的定制内容复制并应用到新系统"""
    _write_os_release(mountpoint)
    _copy_gnome_extensions(mountpoint)
    _copy_skel(mountpoint, username)
    _apply_dconf(mountpoint, username)
    _copy_fcitx5(mountpoint)
    _register_system_icons(mountpoint)
    _copy_earlyoom_config(mountpoint)
    _write_zram_config(mountpoint)
    logger.info('LiveCD 定制内容复制完成')


def _write_os_release(mountpoint: Path) -> None:
    """写入 ElvaraOS os-release"""
    logger.info('写入 os-release...')
    target = mountpoint / 'etc/os-release'
    target.write_text(_OS_RELEASE)


def _copy_gnome_extensions(mountpoint: Path) -> None:
    """复制系统级 GNOME 扩展（/usr/share/gnome-shell/extensions/）"""
    src = Path('/usr/share/gnome-shell/extensions')
    dst = mountpoint / 'usr/share/gnome-shell/extensions'
    if not src.is_dir():
        logger.warning('未找到系统 GNOME 扩展目录，跳过')
        return
    logger.info('复制系统 GNOME 扩展...')
    dst.mkdir(parents=True, exist_ok=True)
    for ext_dir in src.iterdir():
        d = dst / ext_dir.name
        if d.exists():
            shutil.rmtree(d)
        shutil.copytree(ext_dir, d)
        logger.debug(f'  已复制扩展: {ext_dir.name}')


def _copy_skel(mountpoint: Path, username: str) -> None:
    src_skel = Path('/etc/skel')
    if not src_skel.is_dir():
        logger.warning('未找到 /etc/skel，跳过')
        return
    logger.info('复制 /etc/skel 配置...')
    _merge_copy(src_skel, mountpoint / 'etc/skel')

    user_home = mountpoint / 'home' / username
    if user_home.is_dir():
        _merge_copy(src_skel, user_home)

        ding_js = user_home / '.local/share/gnome-shell/extensions/ding@rastersoft.com/app/ding.js'
        if ding_js.exists():
            ding_js.chmod(ding_js.stat().st_mode | 0o111)

        wants_dir = user_home / '.config/systemd/user/graphical-session.target.wants'
        wants_dir.mkdir(parents=True, exist_ok=True)
        svc_symlink = wants_dir / 'ding-fix-permissions.service'
        if not svc_symlink.exists():
            os.symlink(
                f'/home/{username}/.config/systemd/user/ding-fix-permissions.service',
                svc_symlink,
            )

        subprocess.run(
            ['arch-chroot', str(mountpoint),
             'chown', '-R', f'{username}:{username}', f'/home/{username}'],
            check=False,
        )
    else:
        logger.warning(f'用户 home 目录不存在：{user_home}，跳过 skel 复制到 home')


def _apply_dconf(mountpoint: Path, username: str) -> None:
    dconf_src = Path('/root/dconf-settings.txt')
    if not dconf_src.is_file():
        logger.warning('未找到 /root/dconf-settings.txt，跳过 dconf 配置')
        return
    logger.info('编译 dconf 配置数据库...')

    tmp_dir = mountpoint / 'tmp/dconf-profile'
    tmp_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dconf_src, tmp_dir / 'user.ini')

    user_dconf_dir = mountpoint / 'home' / username / '.config/dconf'
    user_dconf_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ['dconf', 'compile', str(user_dconf_dir / 'user'), str(tmp_dir)],
        check=False, capture_output=True,
    )
    if result.returncode != 0:
        logger.warning(f'dconf compile 失败: {result.stderr.decode().strip()}')
    else:
        logger.info(f'dconf 数据库已写入 /home/{username}/.config/dconf/user')
        subprocess.run(
            ['arch-chroot', str(mountpoint),
             'chown', '-R', f'{username}:{username}',
             f'/home/{username}/.config/dconf'],
            check=False,
        )
    shutil.rmtree(tmp_dir, ignore_errors=True)


def _copy_fcitx5(mountpoint: Path) -> None:
    src_profile = Path('/etc/profile.d/fcitx5.sh')
    if src_profile.is_file():
        logger.info('复制 fcitx5 profile.d 配置...')
        dst = mountpoint / 'etc/profile.d'
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_profile, dst / 'fcitx5.sh')

    src_autostart = Path('/etc/xdg/autostart/fcitx5.desktop')
    if src_autostart.is_file():
        logger.info('复制 fcitx5 autostart...')
        dst = mountpoint / 'etc/xdg/autostart'
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_autostart, dst / 'fcitx5.desktop')


def _register_system_icons(mountpoint: Path) -> None:
    """注册 ElvaraOS 图标，并替换 archlinux-logo.*（与 customize_airootfs.sh 一致）"""
    pixmaps_src = Path('/usr/share/pixmaps')

    # (源文件名, hicolor 目标文件名)
    icon_map_256 = [
        ('elvara.png',                 'elvara.png'),
        ('elvara-logo-text.png',       'elvara-text.png'),
        ('elvara-logo-text-dark.png',  'elvara-text-dark.png'),
    ]
    icon_map_scalable = [
        ('elvara.svg',                 'elvara.svg'),
        ('elvara-logo-text.svg',       'elvara-text.svg'),
        ('elvara-logo-text-dark.svg',  'elvara-text-dark.svg'),
    ]

    dst_256      = mountpoint / 'usr/share/icons/hicolor/256x256/apps'
    dst_scalable = mountpoint / 'usr/share/icons/hicolor/scalable/apps'
    dst_pixmaps  = mountpoint / 'usr/share/pixmaps'

    dst_256.mkdir(parents=True, exist_ok=True)
    dst_scalable.mkdir(parents=True, exist_ok=True)
    dst_pixmaps.mkdir(parents=True, exist_ok=True)

    any_copied = False
    for src_name, dst_name in icon_map_256:
        src = pixmaps_src / src_name
        if src.is_file():
            shutil.copy2(src, dst_256 / dst_name)
            shutil.copy2(src, dst_pixmaps / src_name)
            any_copied = True

    for src_name, dst_name in icon_map_scalable:
        src = pixmaps_src / src_name
        if src.is_file():
            shutil.copy2(src, dst_scalable / dst_name)
            shutil.copy2(src, dst_pixmaps / src_name)
            any_copied = True

    if not any_copied:
        logger.warning('未找到 ElvaraOS 图标文件（/usr/share/pixmaps/elvara.*），跳过图标注册')
        return

    logger.info('注册 ElvaraOS 系统图标...')

    # 替换 archlinux-logo.*
    replacements = [
        ('elvara.png',               'archlinux-logo.png'),
        ('elvara.svg',               'archlinux-logo.svg'),
        ('elvara-logo-text.svg',     'archlinux-logo-text.svg'),
        ('elvara-logo-text-dark.svg','archlinux-logo-text-dark.svg'),
    ]
    for src_name, dst_name in replacements:
        src = pixmaps_src / src_name
        if src.is_file():
            shutil.copy2(src, dst_pixmaps / dst_name)

    subprocess.run(
        ['arch-chroot', str(mountpoint),
         'gtk-update-icon-cache', '-f', '-t', '/usr/share/icons/hicolor/'],
        check=False,
    )


def _copy_earlyoom_config(mountpoint: Path) -> None:
    """复制 earlyoom 配置"""
    src = Path('/etc/default/earlyoom')
    if not src.is_file():
        logger.warning('未找到 /etc/default/earlyoom，跳过')
        return
    logger.info('复制 earlyoom 配置...')
    dst_dir = mountpoint / 'etc/default'
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst_dir / 'earlyoom')


def _write_zram_config(mountpoint: Path) -> None:
    """写入 zram-generator 配置"""
    logger.info('写入 zram-generator 配置...')
    dst_dir = mountpoint / 'etc/systemd'
    dst_dir.mkdir(parents=True, exist_ok=True)
    (dst_dir / 'zram-generator.conf').write_text(_ZRAM_CONF)


def _merge_copy(src: Path, dst: Path) -> None:
    """递归合并复制目录"""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        d = dst / item.name
        if item.is_symlink():
            link_target = os.readlink(item)
            if d.exists() or d.is_symlink():
                d.unlink()
            os.symlink(link_target, d)
        elif item.is_dir():
            _merge_copy(item, d)
        else:
            shutil.copy2(item, d)
