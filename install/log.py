"""日志配置 — 基于 loguru，同时接管 archinstall 的输出和子进程 stdout"""
import logging
import sys
from typing import Callable

from loguru import logger

logger.remove()


def setup_cli_logging() -> None:
    """CLI 模式：彩色输出到 stderr"""
    logger.add(
        sys.stderr,
        colorize=True,
        format='<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}',
        level='DEBUG',
    )


def setup_gui_logging(callback: Callable[[str], None]) -> None:
    """
    GUI 模式：每次调用前先清除旧 sink，避免重复安装时日志重复输出。
    """
    logger.remove()
    logger.add(
        callback,
        format='{time:HH:mm:ss} [{level}] {message}',
        level='DEBUG',
        colorize=False,
    )
    logger.add(
        '/tmp/elvara-install.log',
        rotation='10 MB',
        level='DEBUG',
        encoding='utf-8',
    )

    _patch_archinstall_output()
    _patch_pacman_ask()
    _redirect_stdout(callback)


# ── archinstall output monkey-patch ─────────────────────────────────────────

def _patch_archinstall_output() -> None:
    """
    替换 archinstall.lib.output.log()，把所有 info/warn/error/debug 调用
    转发到 loguru，而不是直接 print()。
    """
    import archinstall.lib.output as _out

    _level_map = {
        logging.DEBUG:   logger.debug,
        logging.INFO:    logger.info,
        logging.WARNING: logger.warning,
        logging.ERROR:   logger.error,
        logging.CRITICAL: logger.critical,
    }

    def _patched_log(*msgs: str, level: int = logging.INFO, **kwargs) -> None:
        text = ' '.join(str(m) for m in msgs)
        _level_map.get(level, logger.info)(text)

    _out.log = _patched_log
    # info/warn/error/debug 都是 log() 的薄包装，直接替换底层即可


# ── stdout 重定向 ────────────────────────────────────────────────────────────

class _LoguruStream:
    """
    替换 sys.stdout，把 SysCommandWorker.peak() 写入的子进程输出
    逐行转发给 loguru（进而到 GUI 日志面板）。
    """
    def __init__(self, callback: Callable[[str], None]) -> None:
        self._callback = callback
        self._buf = ''
        self._original = sys.__stdout__

    def write(self, data: str) -> int:
        self._buf += data
        while '\n' in self._buf:
            line, self._buf = self._buf.split('\n', 1)
            line = line.strip()
            if line:
                logger.debug(line)
        return len(data)

    def flush(self) -> None:
        if self._buf.strip():
            logger.debug(self._buf.strip())
            self._buf = ''

    def fileno(self) -> int:
        # 某些底层代码会调用 fileno()，返回原始 stdout 的 fd 保证兼容
        return self._original.fileno()

    def isatty(self) -> bool:
        return False


def _redirect_stdout(callback: Callable[[str], None]) -> None:
    sys.stdout = _LoguruStream(callback)  # type: ignore[assignment]


# ── pacman 重试 patch ────────────────────────────────────────────────────────

def _patch_pacman_ask(retries: int = 3) -> None:
    """
    GUI 模式下没有终端，无法响应 input()。
    替换 Pacman.ask()，遇到下载失败自动重试最多 retries 次，
    超过次数再抛异常让 GUI 显示错误。
    """
    from archinstall.lib.pacman.pacman import Pacman
    from archinstall.lib.exceptions import RequirementError
    from typing import Callable as _Callable

    def _auto_retry_ask(
        self,
        error_message: str,
        bail_message: str,
        func: _Callable,
        *args,
        **kwargs,
    ) -> None:
        for attempt in range(1, retries + 1):
            try:
                func(*args, **kwargs)
                return
            except Exception as err:
                logger.warning(f'{error_message}: {err}')
                if attempt < retries:
                    logger.info(f'下载失败，自动重试 ({attempt}/{retries})...')
                else:
                    raise RequirementError(f'{bail_message}: {err}')

    Pacman.ask = _auto_retry_ask  # type: ignore[method-assign]
