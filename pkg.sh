#!/bin/zsh
source .venv/bin/activate

rm -rf dist
rm -rf build

pyinstaller --onefile \
    --icon=elvara.png \
    --add-data "archinstall/locales:archinstall/locales" \
    --hidden-import=archinstall.lib \
    --hidden-import=archinstall.lib.args \
    --hidden-import=archinstall.lib.disk.filesystem \
    --hidden-import=archinstall.lib.disk.device_handler \
    --hidden-import=archinstall.lib.installer \
    --hidden-import=archinstall.lib.models.users \
    --hidden-import=archinstall.lib.translationhandler \
    --hidden-import=archinstall.lib.models.device \
    --hidden-import=archinstall.lib.models.locale \
    --hidden-import=archinstall.lib.bootloader \
    --hidden-import=archinstall.lib.pacman \
    --hidden-import=archinstall.lib.networking \
    --hidden-import=archinstall.lib.hardware \
    --hidden-import=archinstall.lib.output \
    --hidden-import=archinstall.lib.exceptions \
    --hidden-import=archinstall.lib.crypt \
    --hidden-import=archinstall.lib.configuration \
    --hidden-import=archinstall.lib.global_menu \
    --hidden-import=archinstall.lib.plugins \
    --hidden-import=archinstall.lib.version \
    --hidden-import=archinstall.lib.command \
    --hidden-import=archinstall.lib.boot \
    --hidden-import=archinstall.tui \
    --hidden-import=install.disk \
    --hidden-import=install.mirrors \
    --hidden-import=install.customization \
    --hidden-import=install.core \
    --hidden-import=install.log \
    --hidden-import=PySide6 \
    main.py

# mkisofs -o output.iso -J -R ./dist/