#!/usr/bin/env bash

sed -i 's/#ParallelDownloads/ParallelDownloads/' /etc/pacman.conf
sed -i 's/#Color/Color/' /etc/pacman.conf

reflector --country China --latest 10 --protocol https --sort rate --save /etc/pacman.d/mirrorlist

mkdir -p /build/go-cache
chmod 777 /build/go-cache

cd /tmp
git clone https://aur.archlinux.org/yay.git
chown -R nobody:nobody yay
cd yay
# 构建
sudo -u nobody env GOPROXY=https://goproxy.cn,direct GOCACHE=/build/go-cache GOPATH=/build/go-cache makepkg --noconfirm
# 安装（用 root，不需要密码）
pacman -U --noconfirm yay-*.pkg.tar.zst
cd ..
rm -rf yay

systemctl enable earlyoom
systemctl enable gdm
systemctl enable NetworkManager
systemctl enable bluetooth

