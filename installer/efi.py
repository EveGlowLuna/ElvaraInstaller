import subprocess
from installer import disk

EFI_GUID = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"


def get_efi_part(selected_disk_index: int) -> str | None:
    children = disk.get_disk_children(selected_disk_index)
    for child in children:
        if child.get('parttype') == EFI_GUID:
            return f"/dev/{child['name']}"
    return None


def get_boot_mode() -> str:
    try:
        with open('/sys/firmware/efi/fw_platform_size') as f:
            val = f.read().strip()
        return 'uefi' if val == '64' else 'uefi32'
    except OSError:
        return 'boot'
