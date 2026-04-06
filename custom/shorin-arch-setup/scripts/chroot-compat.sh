#!/bin/bash

# chroot-compat.sh
# 在 arch-chroot 环境中运行 shorin 脚本前，打上必要的补丁。
# 由安装器在 chroot 外调用，传入挂载点和用户名。
#
# 用法: bash chroot-compat.sh <mount_point> <username> <desktop_env>

MOUNT="$1"
USERNAME="$2"
DESKTOP_ENV="$3"
SCRIPTS="$MOUNT/root/shorin-arch-setup/scripts"

if [[ -z "$MOUNT" || -z "$USERNAME" || -z "$DESKTOP_ENV" ]]; then
    echo "用法: $0 <mount_point> <username> <desktop_env>"
    exit 1
fi

echo "[chroot-compat] 开始适配，挂载点=$MOUNT 用户=$USERNAME 桌面=$DESKTOP_ENV"

# 1. 写入用户名缓存，让 detect_target_user 跳过交互
echo "$USERNAME" > "$MOUNT/tmp/shorin_install_user"

# 2. patch --now：chroot 里 systemctl 不能 start 服务
find "$SCRIPTS" -name "*.sh" -exec sed -i \
    's/systemctl enable --now/systemctl enable/g' {} \;

# 3. patch 03-user.sh：删掉清除用户名缓存的整个 if 块，保留缓存让 detect_target_user 直接读
sed -i '/if \[ -f.*shorin_install_user/,/^fi$/d' "$SCRIPTS/03-user.sh"

# 4. patch wineboot：Wine 初始化需要显示环境，跳过
# 用户首次运行 Wine 程序时会自动初始化
find "$SCRIPTS" -name "*.sh" -exec sed -i \
    '/wineboot/d; /wineserver/d' {} \;

# 5. patch virsh net-start：libvirtd 没运行，跳过
# net-autostart 已设置，重启后自动生效
find "$SCRIPTS" -name "*.sh" -exec sed -i \
    '/virsh net-start/d' {} \;

# 6. patch flatpak install：chroot 里 flatpak 无法安装应用，跳过
find "$SCRIPTS" -name "*.sh" -exec sed -i \
    '/flatpak install/d' {} \;

# 7. 写入主执行脚本
cat > "$MOUNT/root/run-shorin.sh" << SCRIPT
#!/bin/bash
export SHELL=\$(command -v bash)
export DESKTOP_ENV="$DESKTOP_ENV"
export NO_COLOR=1
export TERM=dumb

BASE_DIR="/root/shorin-arch-setup"
SCRIPTS_DIR="\$BASE_DIR/scripts"

source "\$SCRIPTS_DIR/00-utils.sh"

# 预设变量，跳过交互
export SKIP_DM=false
export CN_MIRROR=0
export DEBUG=0

# 先手动装好 yay（chroot 里 archlinuxcn 源已配置）
if ! command -v yay &>/dev/null; then
    echo "[shorin] 安装 yay..."
    pacman -S --noconfirm --needed yay || true
fi

# 给用户配置临时 NOPASSWD，让 yay 能以普通用户身份运行
echo "$USERNAME ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/99_installer_temp
chmod 440 /etc/sudoers.d/99_installer_temp

# 按顺序执行必要模块
for module in 01-base.sh 02-musthave.sh 03-user.sh; do
    echo "[shorin] 执行 \$module ..."
    bash "\$SCRIPTS_DIR/\$module" || { echo "[shorin] \$module 失败"; exit 1; }
done

# 桌面环境
case "\$DESKTOP_ENV" in
    shorinniri)    bash "\$SCRIPTS_DIR/04-niri-setup.sh" ;;
    minimalniri)   bash "\$SCRIPTS_DIR/04j-minimal-niri.sh" ;;
    kde)           bash "\$SCRIPTS_DIR/04b-kdeplasma-setup.sh" ;;
    end4)          bash "\$SCRIPTS_DIR/04e-illogical-impulse-end4-quickshell.sh" ;;
    dms)           bash "\$SCRIPTS_DIR/04c-dms-quickshell.sh" ;;
    shorindmsgit)  export SHORIN_DMS_GIT=1; bash "\$SCRIPTS_DIR/04h-shorindms-quickshell.sh" ;;
    hyprniri)      bash "\$SCRIPTS_DIR/04i-shorin-hyprniri-quickshell.sh" ;;
    shorinnocniri) bash "\$SCRIPTS_DIR/04k-shorin-noctalia-quickshell.sh" ;;
    caelestia)     bash "\$SCRIPTS_DIR/04g-caelestia-quickshell.sh" ;;
    gnome)         bash "\$SCRIPTS_DIR/04d-gnome.sh" ;;
    minimallabwc)  bash "\$SCRIPTS_DIR/04l-minimal-labwc.sh" ;;
    none)          echo "[shorin] 跳过桌面环境安装" ;;
esac

# 清理临时 sudo
rm -f /etc/sudoers.d/99_installer_temp

echo "[shorin] 全部完成"
SCRIPT

chmod +x "$MOUNT/root/run-shorin.sh"
echo "[chroot-compat] 适配完成，可以执行 arch-chroot $MOUNT /root/run-shorin.sh"
