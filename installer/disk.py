import json
import subprocess
import re

_log_callback = None


def set_log_callback(cb):
    global _log_callback
    _log_callback = cb


def _run(args: list, **kwargs) -> None:
    if _log_callback:
        _log_callback(f'$ {" ".join(str(a) for a in args)}')
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if result.stdout and _log_callback:
        _log_callback(result.stdout.strip())
    if result.stderr and _log_callback:
        _log_callback(result.stderr.strip())
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)


def get_partition_path(disk: str, num: int) -> str:
    if re.search(r'nvme\d+n\d+', disk):
        return f"{disk}p{num}"
    return f"{disk}{num}"


def get_disk_data() -> dict:
    result = subprocess.run(
        ['lsblk', '-J', '-o', 'NAME,TYPE,SIZE,MOUNTPOINT,FSTYPE,LABEL,MODEL,PARTFLAGS,PARTTYPE,PARTLABEL'],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def get_disk_children(selected_disk_index: int) -> list:
    disks = get_disk_data()
    return disks['blockdevices'][selected_disk_index].get('children', [])


def mount_disk(root: str, efi: str | None) -> None:
    _run(['sudo', 'mount', root, '/mnt'])
    if efi is not None:
        _run(['sudo', 'mount', '--mkdir', efi, '/mnt/boot'])


def create_filesystem(target: str, fs_type: str = 'ext4') -> None:
    args = ['sudo', f'mkfs.{fs_type}']
    if fs_type == 'fat':
        args.append('-F32')
    args.append(target)
    _run(args)


def create_label(target: str) -> None:
    _run(['sudo', 'parted', '-s', target, 'mklabel', 'gpt'])


def create_part(target_disk: str, part_label: str, start_size: str, end_size: str,
                fs_type: str = 'ext4', is_efi: bool = False) -> None:
    _run(['sudo', 'parted', '-s', target_disk, 'mkpart', part_label, fs_type, start_size, end_size])
    if is_efi:
        _run(['sudo', 'parted', '-s', target_disk, 'set', '1', 'esp', 'on'])


def get_last_part_end(disk_path: str) -> str:
    """返回磁盘最后一个分区的结束位置（MiB 字符串），找不到返回 '1MiB'"""
    try:
        result = subprocess.run(
            ['sudo', 'parted', '-s', '-m', disk_path, 'unit', 'MiB', 'print'],
            capture_output=True, text=True,
        )
        last_end = '1MiB'
        for line in result.stdout.splitlines():
            parts = line.rstrip(';').split(':')
            if len(parts) >= 3 and parts[0].strip().isdigit():
                last_end = parts[2].strip()
        return last_end
    except Exception:
        return '1MiB'


def get_unallocated_gb(disk_path: str) -> float:
    """用 parted 查询磁盘未分配空间总量，返回 GiB，查询失败返回 0"""
    try:
        result = subprocess.run(
            ['sudo', 'parted', '-s', '-m', disk_path, 'unit', 'B', 'print', 'free'],
            capture_output=True, text=True,
        )
        total = 0
        for line in result.stdout.splitlines():
            parts = line.rstrip(';').split(':')
            if len(parts) >= 4 and parts[3] == 'free':
                try:
                    total += int(parts[2].rstrip('B'))
                except ValueError:
                    pass
        return total / (1024 ** 3)
    except Exception:
        return 0.0
