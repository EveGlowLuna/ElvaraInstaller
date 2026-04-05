#!/usr/bin/env bash

# pacman 基础优化
sed -i 's/#ParallelDownloads/ParallelDownloads/' /etc/pacman.conf
sed -i 's/#Color/Color/' /etc/pacman.conf

# 换源
reflector --country China --latest 10 --protocol https --sort rate --save /etc/pacman.d/mirrorlist

# 安装 yay（shorin 脚本依赖它）
mkdir -p /build/go-cache
chmod 777 /build/go-cache

cd /tmp
git clone https://aur.archlinux.org/yay.git
chown -R nobody:nobody yay
cd yay
sudo -u nobody env GOPROXY=https://goproxy.cn,direct GOCACHE=/build/go-cache GOPATH=/build/go-cache makepkg --noconfirm
pacman -U --noconfirm yay-*.pkg.tar.zst
cd ..
rm -rf yay
rm -rf /build

# 拉取 ElvaraOS 仓库，复制系统标识和特色工具
cd /tmp
git clone https://github.com/EveGlowLuna/ElvaraOS.git ElvaraCustom
cd ElvaraCustom/airootfs

# 系统标识
rm -f /etc/os-release
cp etc/os-release /etc/os-release

# 系统图标
cp -a usr/local/share/pixmaps/* /usr/local/share/pixmaps/

# ElvaraOSTools
cp usr/local/bin/ElvaraOSTools /usr/local/bin/ElvaraOSTools
chmod +x /usr/local/bin/ElvaraOSTools
cp -a usr/local/share/applications/* /usr/local/share/applications/

cd /tmp
rm -rf ElvaraCustom

exit 0
