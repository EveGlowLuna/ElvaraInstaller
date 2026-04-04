import json
import subprocess
import re

def get_partition_path(disk, num):
    if re.search(r'nvme\d+n\d+$', disk):
        return f"{disk}p{num}"
    return f"{disk}{num}"

def get_disk_data():
    result = subprocess.run(
        ['lsblk', '-J', '-o', "NAME,TYPE,SIZE,MOUNTPOINT,FSTYPE,LABEL,MODEL,PARTFLAGS,PARTTYPE,PARTLABEL"],
        capture_output=True,
        text=True
    )
    return json.loads(result.stdout)

def get_disk_children(selected_disk_index: int):
    disks = get_disk_data()
    if not 'children' in disks['blockdevices'][selected_disk_index]:
        return []
    else:
        return disks['blockdevices'][selected_disk_index]['children']

def mount_disk(root: str, efi: str):
    subprocess.run(['sudo', 'mount', root, '/mnt'])
    subprocess.run(['sudo', 'mount', '--mkdir', efi, '/mnt/boot'])

def create_filesystem(target: str, fs_type: str = 'ext4'):
    args = [f'mkfs.{fs_type}']
    if fs_type == 'fat':
        args.append('-F32')
    args.append(target)
    subprocess.run(args)

def create_label(target: str):
    subprocess.run(['parted', '-s', target, 'mklabel', 'gpt'])

def create_part(target_disk: str, part_label: str, start_size: str, end_size: str, fs_type: str = 'ext4', is_efi: bool = False):
    subprocess.run(['sudo', 'parted', '-s', target_disk, 'mkpart', part_label, fs_type, start_size, end_size])
    if is_efi:
        subprocess.run(['sudo', 'parted', '-s', target_disk, 'set', '1', 'esp', 'on'])

