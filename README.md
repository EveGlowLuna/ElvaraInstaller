# ElvaraInstaller

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Arch%20Linux-1793d1.svg)](https://archlinux.org/)
[![License](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)

基于 Python 的 Arch Linux 安装程序，支持自定义。

## 直接使用

在非 ElvaraOS livecd 中，支持 TTY 终端，**只支持 Arch 系 Linux**

```bash
curl -fsSL https://elvaraos-install.eveglowsite.top/ | bash
```

## 作为模板使用

1. 点击`Use this template`创建属于自己的仓库
2. 修改 `custom/` 目录下的文件：
   - `custom.py`：编写自定义安装逻辑
   - `packages.txt`：添加需要的包
3. 运行安装程序

## 开发

```bash
python3 -m venv .venv
source ./.venv/bin/activate
pip install -r requirements.txt
```

## 自定义说明

- 修改 `custom/custom.py` 中的 `CustomInstaller.run()` 方法实现自定义安装逻辑
- 在 `custom/packages.txt` 中添加需要安装的包（每行一个）
- 有关 `custom.py` 的更多信息请查看custom/docs.md