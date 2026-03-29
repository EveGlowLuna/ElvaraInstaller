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
    _patch_pacman_conf(mountpoint)
    _copy_gnome_extensions(mountpoint)
    _copy_skel(mountpoint, username)
    _apply_dconf(mountpoint, username)
    _copy_fcitx5(mountpoint)
    _register_system_icons(mountpoint)
    _setup_plymouth(mountpoint)
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

_HICOLOR_INDEX = """\
[Icon Theme]
Hidden=false
Comment=Fallback icon theme
Directories=256x256/apps,128x128/apps,96x96/apps,72x72/apps,64x64/apps,48x48/apps,36x36/apps,32x32/apps,24x24/apps,22x22/apps,16x16/apps,scalable/apps

[256x256/apps]
Size=256
Context=Applications
Type=Threshold
MinSize=256
MaxSize=256

[128x128/apps]
Size=128
Context=Applications
Type=Threshold
MinSize=128
MaxSize=128

[96x96/apps]
Size=96
Context=Applications
Type=Threshold
MinSize=96
MaxSize=96

[72x72/apps]
Size=72
Context=Applications
Type=Threshold
MinSize=72
MaxSize=72

[64x64/apps]
Size=64
Context=Applications
Type=Threshold
MinSize=64
MaxSize=64

[48x48/apps]
Size=48
Context=Applications
Type=Threshold
MinSize=48
MaxSize=48

[36x36/apps]
Size=36
Context=Applications
Type=Threshold
MinSize=36
MaxSize=36

[32x32/apps]
Size=32
Context=Applications
Type=Threshold
MinSize=32
MaxSize=32

[24x24/apps]
Size=24
Context=Applications
Type=Threshold
MinSize=24
MaxSize=24

[22x22/apps]
Size=22
Context=Applications
Type=Threshold
MinSize=22
MaxSize=22

[16x16/apps]
Size=16
Context=Applications
Type=Threshold
MinSize=16
MaxSize=16

[scalable/apps]
Size=48
Context=Applications
Type=Scalable
MinSize=1
MaxSize=512
"""


def _patch_pacman_conf(mountpoint: Path) -> None:
    """启用 ParallelDownloads，注释掉 CheckSpace（与 customize_airootfs.sh 一致）"""
    logger.info('修改 pacman.conf...')
    conf = mountpoint / 'etc/pacman.conf'
    if not conf.is_file():
        logger.warning('未找到 /etc/pacman.conf，跳过')
        return
    text = conf.read_text()
    text = text.replace('#ParallelDownloads', 'ParallelDownloads')
    text = text.replace('\nCheckSpace', '\n#CheckSpace')
    conf.write_text(text)


def _setup_plymouth(mountpoint: Path) -> None:
    """
    复制 Plymouth elvara 主题并设为默认。
    - 复制主题文件（.plymouth + .script）
    - 复制 elvara-logo-text.png 到主题目录
    - 写入完整的 hicolor index.theme
    - 运行 plymouth-set-default-theme -R elvara（重新生成 initramfs）
    """
    src_theme_dir = Path('/usr/share/plymouth/themes/elvara')
    dst_theme_dir = mountpoint / 'usr/share/plymouth/themes/elvara'

    if not src_theme_dir.is_dir():
        logger.warning('未找到 Plymouth elvara 主题目录，跳过')
        return

    logger.info('复制 Plymouth elvara 主题...')
    dst_theme_dir.mkdir(parents=True, exist_ok=True)
    _merge_copy(src_theme_dir, dst_theme_dir)

    # elvara-logo-text.png 主题脚本里直接引用，必须在主题目录里
    logo_src = Path('/usr/share/pixmaps/elvara-logo-text.png')
    if logo_src.is_file():
        shutil.copy2(logo_src, dst_theme_dir / 'elvara-logo-text.png')
    else:
        logger.warning('未找到 elvara-logo-text.png，Plymouth 主题可能显示异常')

    # 写入完整 hicolor index.theme（gtk-update-icon-cache 需要它）
    index_theme = mountpoint / 'usr/share/icons/hicolor/index.theme'
    index_theme.parent.mkdir(parents=True, exist_ok=True)
    index_theme.write_text(_HICOLOR_INDEX)

    # 设置默认主题（-R 会重新生成 initramfs，包含 plymouth hook）
    result = subprocess.run(
        ['arch-chroot', str(mountpoint),
         'plymouth-set-default-theme', '-R', 'elvara'],
        check=False, capture_output=True,
    )
    if result.returncode != 0:
        logger.warning(f'plymouth-set-default-theme 失败: {result.stderr.decode().strip()}')
    else:
        logger.info('Plymouth 主题设置完成')
