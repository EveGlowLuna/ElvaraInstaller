#!/usr/bin/env bash

rm dist.iso

source ./.venv/bin/activate

pyinstaller --onefile \
    --icon=elvara.png \
    --exclude-module custom \
    --add-data "installer:installer" \
    --hidden-import installer_cli \
    main.py

mv dist/main dist/ElvaraInstaller
chmod +x dist/ElvaraInstaller

pyinstaller --onefile \
    --distpath dist/custom \
    custom/desktop_picker.py

cp -r custom/* dist/custom
chmod +x dist/custom/desktop_picker

mkisofs -o dist.iso -J -R ./dist/