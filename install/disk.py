"""磁盘检测与分区布局构建"""
import subprocess
import time
from pathlib import Path

from loguru import logger

from archinstall.lib.disk.device_handler import device_handler
from archinstall.lib.models.device import (
    DeviceModification,
    DiskLayoutConfiguration,
    DiskLayoutType,
    FilesystemType,
    ModificationStatus,
    PartitionFlag,
    PartitionModification,
    PartitionType,
    SectorSize,
    Size,
    Unit,
)


def detect_existing_systems(device) -> list[dict]:
    """扫描设备上已有的分区，识别可能的操作系统"""
    fs_os_hints = {
        'ntfs':        'Windows',
        'fat32':       'EFI/Windows',
        'fat16':       'EFI/Windows',
        'ext4':        'Linux',
        'ext3':        'Linux',
        'ext2':        'Linux',
        'btrfs':       'Linux (Btrfs)',
        'xfs':         'Linux (XFS)',
        'f2fs':        'Linux (F2FS)',
        'crypto_LUKS': 'Linux (加密)',
        'linux-swap':  'Linux Swap',
    }
    result = []
    for part_info in device.partition_infos:
        if part_info.fs_type is None:
            continue
        fs_name = part_info.fs_type.value
        result.append({
            'part_info': part_info,
            'hint':      fs_os_hints.get(fs_name, fs_name),
            'size':      part_info.length.format_highest(),
            'path':      str(part_info.path),
            'fs':        fs_name,
        })
    return result


# 被认为是"系统分区"（EFI、swap、BIOS boot）的文件系统类型，不算作可用分区
_SYSTEM_FS = {'fat32', 'fat16', 'fat12', 'linux-swap', 'swap'}
# 被认为含有操作系统的文件系统类型
_OS_FS = {'ntfs', 'ext4', 'ext3', 'ext2', 'btrfs', 'xfs', 'f2fs', 'crypto_LUKS'}


def analyze_coexist_partitions(device) -> dict:
    """
    分析磁盘分区，为共存安装提供决策数据。

    返回字典：
      - 'efi': _PartitionInfo | None  — 已有 EFI 分区
      - 'os_parts': list[dict]        — 含有操作系统的分区
      - 'free_parts': list[dict]      — 空闲/未知分区（可直接安装）
      - 'free_regions': list          — 未分配的空闲区域
    """
    efi = None
    os_parts = []
    free_parts = []

    for part_info in device.partition_infos:
        fs = part_info.fs_type.value if part_info.fs_type else None
        flags = part_info.flags

        # 识别 EFI 分区
        if fs in ('fat32', 'fat16', 'fat12'):
            if PartitionFlag.ESP in flags or PartitionFlag.BOOT in flags:
                efi = part_info
                continue

        # 跳过 swap 等纯系统分区
        if fs in _SYSTEM_FS:
            continue

        if fs in _OS_FS:
            os_parts.append({
                'part_info': part_info,
                'path':      str(part_info.path),
                'size':      part_info.length.format_highest(),
                'fs':        fs,
            })
        else:
            # fs 为 None 或未知类型，视为空闲可用
            free_parts.append({
                'part_info': part_info,
                'path':      str(part_info.path),
                'size':      part_info.length.format_highest(),
                'fs':        fs or '未知',
            })

    return {
        'efi':         efi,
        'os_parts':    os_parts,
        'free_parts':  free_parts,
        'free_regions': device.device_info.free_space_regions,
    }


def build_disk_layout(selected_disk, uefi: bool) -> DiskLayoutConfiguration:
    """清空全盘模式：按 UEFI/BIOS 创建标准分区布局"""
    sector_size: SectorSize = selected_disk.device_info.sector_size
    total_size: Size = selected_disk.device_info.total_size

    using_gpt = device_handler.partition_table.is_gpt()
    available_space = total_size.gpt_end().align() if using_gpt else total_size.align()

    device_mod = DeviceModification(device=selected_disk, wipe=True)

    if uefi:
        efi_start = Size(1, Unit.MiB, sector_size)
        efi_length = Size(512, Unit.MiB, sector_size)
        efi_part = PartitionModification(
            status=ModificationStatus.Create,
            type=PartitionType.Primary,
            start=efi_start,
            length=efi_length,
            fs_type=FilesystemType.Fat32,
            mountpoint=Path('/boot'),
            flags=[PartitionFlag.ESP, PartitionFlag.BOOT],
        )
        device_mod.add_partition(efi_part)
        root_start = efi_part.start + efi_part.length
        root_length = available_space - root_start
    else:
        root_start = Size(1, Unit.MiB, sector_size)
        root_length = available_space - root_start

    root_part = PartitionModification(
        status=ModificationStatus.Create,
        type=PartitionType.Primary,
        start=root_start,
        length=root_length,
        fs_type=FilesystemType.Ext4,
        mountpoint=Path('/'),
        flags=[] if uefi else [PartitionFlag.BOOT],
    )
    device_mod.add_partition(root_part)

    return DiskLayoutConfiguration(
        config_type=DiskLayoutType.Default,
        device_modifications=[device_mod],
    )


def build_disk_layout_coexist(
    selected_disk,
    uefi: bool,
    target_part_info=None,   # 指定安装到某个已有分区（格式化它）
    alloc_gb: int = 20,      # 从空闲区域划分时分配的 GB 数
) -> DiskLayoutConfiguration:
    """
    共存模式：
    - target_part_info 不为 None：格式化该分区作为根分区
    - target_part_info 为 None：在最大空闲区域划分 alloc_gb 大小
    复用已有 EFI 分区（如果存在）。
    """
    sector_size: SectorSize = selected_disk.device_info.sector_size
    device_mod = DeviceModification(device=selected_disk, wipe=False)

    # 处理 EFI
    analysis = analyze_coexist_partitions(selected_disk)
    existing_efi = analysis['efi']

    if uefi:
        if existing_efi is not None:
            efi_mod = PartitionModification.from_existing_partition(existing_efi)
            efi_mod.mountpoint = Path('/boot')
            device_mod.add_partition(efi_mod)
        else:
            # 需要在空闲区域头部新建 EFI，这里简化处理：
            # 如果有 target_part_info，EFI 从空闲区域另找；
            # 实际上共存时没有 EFI 分区比较罕见，给出警告
            logger.warning('未找到已有 EFI 分区，将尝试在空闲区域创建')

    if target_part_info is not None:
        # 格式化指定分区
        root_mod = PartitionModification.from_existing_partition(target_part_info)
        root_mod.wipe = True
        root_mod.fs_type = FilesystemType.Ext4
        root_mod.mountpoint = Path('/')
        root_mod.status = ModificationStatus.Modify
        device_mod.add_partition(root_mod)
    else:
        # 从空闲区域划分
        min_size = Size(8, Unit.GiB, sector_size)
        free_regions = selected_disk.device_info.free_space_regions
        usable = [
            r for r in free_regions
            if Size(r.get_length(Unit.sectors), Unit.sectors, sector_size) >= min_size
        ]
        if not usable:
            raise ValueError('磁盘剩余空间不足（需要至少 8 GiB 连续空闲空间）。')

        best = max(usable, key=lambda r: r.get_length(Unit.sectors))
        free_start = Size(best.start, Unit.sectors, sector_size).align()
        free_end   = Size(best.end,   Unit.sectors, sector_size).align()

        alloc_size = Size(alloc_gb, Unit.GiB, sector_size)
        root_length = min(alloc_size, free_end - free_start)

        # 如果 UEFI 且没有 EFI 分区，在头部划出 512 MiB 给 EFI
        root_start = free_start
        if uefi and existing_efi is None:
            efi_length = Size(512, Unit.MiB, sector_size)
            efi_part = PartitionModification(
                status=ModificationStatus.Create,
                type=PartitionType.Primary,
                start=free_start,
                length=efi_length,
                fs_type=FilesystemType.Fat32,
                mountpoint=Path('/boot'),
                flags=[PartitionFlag.ESP, PartitionFlag.BOOT],
            )
            device_mod.add_partition(efi_part)
            root_start = free_start + efi_length
            root_length = min(alloc_size, free_end - root_start)

        root_part = PartitionModification(
            status=ModificationStatus.Create,
            type=PartitionType.Primary,
            start=root_start,
            length=root_length,
            fs_type=FilesystemType.Ext4,
            mountpoint=Path('/'),
            flags=[],
        )
        device_mod.add_partition(root_part)

    return DiskLayoutConfiguration(
        config_type=DiskLayoutType.Manual,
        device_modifications=[device_mod],
    )


def umount_target(mountpoint: Path) -> None:
    """强制递归卸载挂载点"""
    if not mountpoint.exists():
        return
    result = subprocess.run(
        ['umount', '-R', '--lazy', str(mountpoint)],
        capture_output=True, check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode().strip()
        if 'not mounted' not in stderr and 'no mount point' not in stderr.lower():
            logger.warning(f'卸载 {mountpoint} 时出现警告: {stderr}')
    else:
        logger.info(f'已卸载 {mountpoint} 下的残留挂载')
    time.sleep(1)
    subprocess.run(['partprobe'], capture_output=True, check=False)
    time.sleep(1)
