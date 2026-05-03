"""日志配置，同时捕获子进程 stdout 输出"""
import sys
from typing import Callable

_callback: Callable[[str], None] | None = None
_log_file = open('/tmp/elvara-install.log', 'a', encoding='utf-8')


def _emit(msg: str) -> None:
    _log_file.write(msg + '\n')
    _log_file.flush()
    if _callback:
        _callback(msg)


def log(msg: str) -> None:
    from datetime import datetime
    line = f'{datetime.now().strftime("%H:%M:%S")} [INFO] {msg}'
    _emit(line)
    if _callback is None:
        print(line, file=sys.stderr)


def setup_gui_logging(callback: Callable[[str], None]) -> None:
    global _callback
    _callback = callback
    _redirect_stdout(callback)
    # 同步给 system 和 disk 的日志回调
    from installer import system, disk
    system.set_log_callback(callback)
    disk.set_log_callback(callback)


class _LogStream:
    """把子进程写入 stdout 的内容逐行转发给日志"""
    def __init__(self) -> None:
        self._buf = ''
        self._original = sys.__stdout__

    def write(self, data: str) -> int:
        self._buf += data
        while '\n' in self._buf:
            line, self._buf = self._buf.split('\n', 1)
            line = line.strip()
            if line:
                log(line)
        return len(data)

    def flush(self) -> None:
        if self._buf.strip():
            log(self._buf.strip())
            self._buf = ''

    def fileno(self) -> int:
        return self._original.fileno()

    def isatty(self) -> bool:
        return False


def _redirect_stdout(callback: Callable[[str], None]) -> None:
    sys.stdout = _LogStream()  # type: ignore[assignment]
