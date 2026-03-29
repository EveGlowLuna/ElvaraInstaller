"""ElvaraOS 安装程序 — CLI 入口"""
import os
import sys

from archinstall.lib.disk.device_handler import device_handler
from archinstall.lib.hardware import SysInfo
from archinstall.lib.models.locale import LocaleConfiguration
from archinstall.lib.models.users import Password, User
from archinstall.lib.output import error

from install.disk import (
    build_disk_layout,
    build_disk_layout_coexist,
    detect_existing_systems,
)
from install.core import perform_installation
from install.log import setup_cli_logging


# ── 输入辅助 ────────────────────────────────────────────────────────────────

def get_input(prompt: str, default: str | None = None) -> str:
    display = f"{prompt} [{default}]: " if default else f"{prompt}: "
    value = input(display).strip() or default
    if not value:
        raise ValueError(f"输入不能为空: {prompt}")
    return value


def create_user_interactive() -> User:
    print("\n=== 创建用户 ===")
    username = get_input("用户名")
    password = get_input("密码")
    sudo = input("是否添加到 wheel 组 (y/n) [y]: ").strip().lower() != 'n'
    groups: list[str] = []
    extra = input("额外组 (逗号分隔，留空跳过): ").strip()
    if extra:
        groups = [g.strip() for g in extra.split(',') if g.strip()]
    return User(username=username, password=Password(plaintext=password), sudo=sudo, groups=groups)


def ask_coexist_or_wipe(device) -> bool:
    """返回 True = 清空全盘，False = 共存"""
    existing = detect_existing_systems(device)
    if not existing:
        return True

    print("\n检测到以下已有分区：")
    print(f"  {'#':<4} {'路径':<16} {'大小':<10} {'文件系统':<14} {'可能的系统'}")
    print("  " + "-" * 60)
    for i, p in enumerate(existing):
        print(f"  {i+1:<4} {p['path']:<16} {p['size']:<10} {p['fs']:<14} {p['hint']}")

    print("\n  [1] 清空整个磁盘\n  [2] 与现有系统共存\n")
    while True:
        choice = input("请选择 [1/2]: ").strip()
        if choice == '1':
            confirm = input(f"⚠️  确认清空 {device.device_info.path} 上的所有数据？输入 YES 继续: ").strip()
            if confirm == 'YES':
                return True
            print("已取消，重新选择。")
        elif choice == '2':
            return False
        else:
            print("请输入 1 或 2")


# ── 主流程 ───────────────────────────────────────────────────────────────────

def main() -> None:
    setup_cli_logging()
    print("=== ElvaraOS 安装程序 ===\n")

    if os.getuid() != 0:
        error("安装程序需要 root 权限运行")
        sys.exit(1)

    devices = device_handler.devices
    if not devices:
        error("未找到可用的存储设备")
        sys.exit(1)

    print("\n=== 磁盘选择 ===")
    for i, dev in enumerate(devices):
        model = dev.device_info.model or "Unknown"
        size_str = dev.device_info.total_size.format_highest()
        print(f"  {i + 1}. {model} ({size_str}) - {dev.device_info.path}")

    disk_index = int(get_input("选择磁盘编号", "1")) - 1
    if not (0 <= disk_index < len(devices)):
        error("无效的磁盘编号")
        sys.exit(1)

    selected_disk = devices[disk_index]
    uefi = SysInfo.has_uefi()
    print(f"\n启动模式：{'UEFI' if uefi else 'BIOS'}")

    wipe = ask_coexist_or_wipe(selected_disk)
    if wipe:
        from archinstall.lib.models.device import Size, Unit
        total_gib = selected_disk.device_info.total_size.convert(Unit.GiB).value
        separate_home = False
        if total_gib >= 64:
            ans = input("是否单独划分 /home 分区？(y/n) [y]: ").strip().lower()
            separate_home = ans != 'n'
        disk_layout_config = build_disk_layout(selected_disk, uefi, separate_home=separate_home)
    else:
        try:
            # 用新的分析逻辑
            from install.disk import analyze_coexist_partitions
            from archinstall.lib.models.device import Size, Unit
            analysis = analyze_coexist_partitions(selected_disk)
            free_parts = analysis['free_parts']
            sector_size = selected_disk.device_info.sector_size
            usable_regions = [
                r for r in analysis['free_regions']
                if Size(r.get_length(Unit.sectors), Unit.sectors, sector_size) >= Size(8, Unit.GiB, sector_size)
            ]

            target_part = None
            alloc_gb = 20

            if len(free_parts) == 1:
                target_part = free_parts[0]['part_info']
                print(f"将安装到空闲分区：{free_parts[0]['path']} ({free_parts[0]['size']})")
            elif len(free_parts) > 1:
                print("\n检测到多个可用分区：")
                for i, p in enumerate(free_parts):
                    print(f"  {i+1}. {p['path']}  {p['size']}  ({p['fs']})")
                idx = int(get_input("选择目标分区编号", "1")) - 1
                target_part = free_parts[idx]['part_info']
            elif usable_regions:
                alloc_gb = int(get_input("为 ElvaraOS 分配多少 GB 空间", "20"))
            else:
                error("磁盘上没有可用的空闲分区或未分配空间（至少需要 8 GiB）")
                sys.exit(1)

            disk_layout_config = build_disk_layout_coexist(
                selected_disk, uefi,
                target_part_info=target_part,
                alloc_gb=alloc_gb,
            )
        except ValueError as e:
            error(str(e))
            sys.exit(1)

    hostname      = get_input("主机名", "elvaraos")
    timezone      = get_input("时区", "Asia/Shanghai")
    locale_config = LocaleConfiguration(
        sys_lang=get_input("系统语言", "zh_CN.UTF-8"),
        sys_enc="UTF-8",
        kb_layout=get_input("键盘布局", "us"),
    )
    user = create_user_interactive()

    perform_installation(
        disk_layout_config=disk_layout_config,
        hostname=hostname,
        timezone=timezone,
        locale_config=locale_config,
        user=user,
    )

    input("按 Enter 重启系统...")
    os.execv('/usr/bin/reboot', ['reboot'])


if __name__ == "__main__":
    main()
