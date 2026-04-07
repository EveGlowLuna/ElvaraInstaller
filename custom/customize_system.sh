#!/usr/bin/env bash
set -e

# pacman 基础优化
sed -i 's/#ParallelDownloads/ParallelDownloads/' /etc/pacman.conf
sed -i 's/#Color/Color/' /etc/pacman.conf

# 换源（先装 reflector，再换源）
pacman -S --noconfirm --needed reflector
reflector --country China --latest 10 --protocol https --sort rate --save /etc/pacman.d/mirrorlist

# 装 yay 的编译依赖
pacman -S --noconfirm --needed git go base-devel

# 安装 yay
mkdir -p /build/go-cache
chmod 777 /build/go-cache

cd /tmp
git clone https://aur.archlinux.org/yay.git
chown -R nobody:nobody yay
cd yay
sudo -u nobody env GOPROXY=https://goproxy.cn,direct GOCACHE=/build/go-cache GOPATH=/build/go-cache makepkg --noconfirm
pacman -U --noconfirm yay-*.pkg.tar.zst
cd /tmp
rm -rf yay /build

# 拉取 ElvaraOS 仓库，复制系统标识和特色工具
git clone https://github.com/EveGlowLuna/ElvaraOS.git /tmp/ElvaraCustom
cd /tmp/ElvaraCustom/airootfs

rm -f /etc/os-release
cp etc/os-release /etc/os-release

# pixmaps
mkdir -p /usr/share/pixmaps
[ -d usr/share/pixmaps ] && cp -a usr/share/pixmaps/. /usr/share/pixmaps/ || true

# applications
mkdir -p /usr/share/applications
[ -d usr/share/applications ] && cp -a usr/share/applications/. /usr/share/applications/ || true

# 构建并安装 ElvaraOSTools
pacman -S --noconfirm --needed dotnet-sdk
git clone --depth=1 https://github.com/EveGlowLuna/ElvaraOS-Toolbox.git /tmp/ElvaraOSToolbox
cd /tmp/ElvaraOSToolbox/ElvaraOSTools
dotnet publish -c Release -r linux-x64 --self-contained true \
    -p:PublishSingleFile=true \
    -p:IncludeNativeLibrariesForSelfExtract=true \
    -o /tmp/toolbox-out
install -Dm755 /tmp/toolbox-out/ElvaraOSTools /usr/local/bin/ElvaraOSTools

# 创建 .desktop 文件
cat > /usr/share/applications/elvara-os-tools.desktop << 'EOF'
[Desktop Entry]
Name=ElvaraOS Tools
Name[zh_CN]=ElvaraOS 工具箱
Comment=ElvaraOS system toolbox
Comment[zh_CN]=ElvaraOS 系统工具箱
Exec=/usr/local/bin/ElvaraOSTools
Icon=elvara
Terminal=false
Type=Application
Categories=System;Settings;
StartupNotify=true
EOF
cd /tmp
rm -rf ElvaraOSToolbox toolbox-out

cd /tmp
rm -rf ElvaraCustom
