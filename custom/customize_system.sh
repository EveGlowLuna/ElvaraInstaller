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

mkdir -p /usr/local/share/pixmaps
[ -d usr/local/share/pixmaps ] && cp -a usr/local/share/pixmaps/. /usr/local/share/pixmaps/ || true

cp usr/local/bin/ElvaraOSTools /usr/local/bin/ElvaraOSTools
chmod +x /usr/local/bin/ElvaraOSTools

mkdir -p /usr/local/share/applications
[ -d usr/local/share/applications ] && cp -a usr/local/share/applications/. /usr/local/share/applications/ || true

cd /tmp
rm -rf ElvaraCustom
