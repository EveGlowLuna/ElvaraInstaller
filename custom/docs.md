# custom/custom.py 开发文档

## 概述

`custom/custom.py` 是安装程序的定制化入口，框架会在安装流程的特定阶段自动调用它。你只需实现 `CustomInstaller` 类，无需修改主程序文件。

## 调用时机

```
安装流程
  ├── 分区 / 格式化
  ├── 挂载
  ├── 安装基础系统 (pacstrap)
  ├── 配置系统 (locale / hostname / 用户 / initramfs)
  ├── 安装引导程序 (GRUB)
  ├── [主线程] CustomInstaller.pre_run()   ← 可选，GUI 交互在此进行
  └── [worker 线程 / CLI] CustomInstaller.run(mount_point)
```

## 接口说明

### `run(mount_point: str)`

**必须实现。** 在安装完成后、卸载文件系统之前调用。

- `mount_point`：目标系统的挂载点，通常为 `/mnt`
- 在 GUI 模式下运行于 worker 线程，**不可在此方法内操作任何 Qt GUI 对象**
- 在 CLI 模式下运行于主线程

```python
def run(self, mount_point: str):
    # 在此执行 chroot 操作、复制文件、写入配置等
    pass
```

### `pre_run()` （可选）

在主线程、启动 worker 之前调用。适合需要 GUI 交互的预处理，例如弹出对话框让用户做选择。

- 仅在 `CustomInstaller` 定义了此方法时才会被调用（通过 `hasattr` 检测）
- GUI 和 CLI 模式下均会调用
- 结果建议存储为实例属性，供 `run()` 使用

```python
def pre_run(self):
    # 在主线程弹窗、读取配置等
    self._my_choice = self._ask_user()

def run(self, mount_point: str):
    choice = getattr(self, '_my_choice', 'default')
    # 使用 choice 执行安装逻辑
```

## 最小模板

```python
import os


class CustomInstaller:
    def run(self, mount_point: str):
        pass
```

## 带 GUI 交互的模板

```python
import os


class CustomInstaller:
    def pre_run(self):
        """在主线程弹出选择对话框。"""
        from installer import system
        if system.is_linux_tty_or_non_desktop():
            self._choice = input('请输入选项: ').strip()
        else:
            self._choice = self._show_dialog()

    def _show_dialog(self) -> str:
        from PySide6.QtWidgets import QApplication, QInputDialog
        app = QApplication.instance() or QApplication([])
        text, ok = QInputDialog.getText(None, '选项', '请输入:')
        return text if ok else ''

    def run(self, mount_point: str):
        choice = getattr(self, '_choice', '')
        # 根据 choice 执行安装逻辑
```

## 注意事项

- `run()` 在 GUI 模式下运行于 **worker 线程**，严禁在此创建或操作任何 `QWidget` / `QDialog`，否则会导致随机崩溃
- 需要 GUI 交互的逻辑一律放在 `pre_run()` 中
- `pre_run()` 是可选的，不需要 GUI 交互时无需实现
- 可以使用 `installer.system.arch_chroot(mount_point, [...])` 在目标系统内执行命令
