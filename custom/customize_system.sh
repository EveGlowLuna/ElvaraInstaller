#!/usr/bin/env bash

sed -i 's/#ParallelDownloads/ParallelDownloads/' /etc/pacman.conf
sed -i 's/#Color/Color/' /etc/pacman.conf

reflector --latest 10 --protocol https --sort rate --save /etc/pacman.d/mirrorlist

mkdir -p /build/go-cache
chmod 777 /build/go-cache

cd /tmp
git clone https://aur.archlinux.org/yay.git
chown -R nobody:nobody yay
cd yay
# 自动检测国家，中国大陆使用 goproxy.cn 镜像
_country=$(curl -sf --max-time 5 "https://ipapi.co/country_code" 2>/dev/null || true)
if [[ "$_country" == "CN" ]]; then
    sudo -u nobody env GOPROXY=https://goproxy.cn,direct GOCACHE=/build/go-cache GOPATH=/build/go-cache makepkg --noconfirm
else
    sudo -u nobody env GOCACHE=/build/go-cache GOPATH=/build/go-cache makepkg --noconfirm
fi
pacman -U --noconfirm yay-*.pkg.tar.zst
cd ..
rm -rf yay

systemctl enable earlyoom
systemctl enable NetworkManager
systemctl enable bluetooth

git clone https://github.com/EveGlowLuna/ElvaraOS.git ElvaraCustom
cd ElvaraCustom/airootfs
cp etc/default/* /etc/default/
cp etc/profile.d/fcitx5.sh /etc/profile.d/
cp -a etc/skel/.config /etc/skel
rm  /etc/skel/.config/systemd/user/trust-installer-desktop.service

username=$(find /home -maxdepth 1 -mindepth 1 -type d -printf "%f\n" -quit)
target_dir="/home/${username}/.local/"
mkdir -p "$target_dir"
cp -a etc/skel/.local/ "$target_dir"
chown -R "${username}:${username}" "/home/${username}"

rm /etc/os-release
cp etc/os-release /etc/os-release

cp -a usr/local/share/applications/* /usr/local/share/applications/
cp -a usr/local/share/pixmaps/* /usr/local/share/pixmaps/

cd ../..

# 编译并安装 ElvaraOSTools
if ! command -v dotnet >/dev/null 2>&1; then
    pacman -Sy --needed --noconfirm dotnet-sdk || { echo "Install dotnet-sdk failed"; exit 1; }
fi
temp_tools_dir=$(mktemp -d)
cd "$temp_tools_dir"
git clone --depth 1 https://github.com/EveGlowLuna/ElvaraOS-Toolbox.git || { echo "clone ElvaraOS-Toolbox failed"; exit 1; }
cd ElvaraOS-Toolbox
dotnet publish ElvaraOSTools/ElvaraOSTools.csproj -c Release -r linux-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:PublishReadyToRun=true -p:PublishTrimmed=true -o publish || { echo "dotnet publish 失败"; exit 1; }
cp publish/ElvaraOSTools /usr/local/bin/ElvaraOSTools
chmod +x /usr/local/bin/ElvaraOSTools
cd /
rm -rf "$temp_tools_dir"

rm -rf ElvaraCustom

exit 0