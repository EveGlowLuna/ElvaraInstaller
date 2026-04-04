#!/usr/bin/env bash

source ./.venv/bin/activate

pyinstaller --onefile \
    --icon=elvara.png \
    --exclude-module custom \
    --add-data "installer:installer" \
    main.py

mv dist/main dist/ElvaraInstaller