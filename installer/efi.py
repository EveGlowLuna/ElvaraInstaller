import subprocess
import json
from installer import disk

EFI_GUID = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"

def get_efi_part(selected_disk_index: int):
    childrens = disk.get_disk_children(selected_disk_index)
    for child in childrens:
        if child['parttype'] == EFI_GUID:
            return f"/dev/{child['name']}"
    return None

def get_boot_mode():
    res = subprocess.run(['sudo', 'cat', '/sys/firmware/efi/fw_platform_size'],
                         capture_output=True,
                         text=True)
    if res.returncode != 0:
        return "boot"
    res_enc = res.stdout.strip()
    if res_enc == "64":
        return "uefi"
    else:
        return "uefi32"