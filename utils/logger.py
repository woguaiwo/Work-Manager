"""
Logging setup for Work Manager

Provides:
  - file + stderr dual output
  - daily rotating log files (keeps 7 days)
  - per-module named loggers
  - global crash hooks (sys.excepthook, threading.excepthook, Qt message handler)
"""

import logging
import logging.handlers
import os
import sys
import threading
import traceback
import faulthandler
import signal
from datetime import datetime

# Log directory: same level as data.db (project root)
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FORMAT = "[%(asctime)s] [%(levelname)-7s] [%(name)-12s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class _QtMessageHandler:
    """Bridge Qt messages (qDebug/qWarning/qCritical) into Python logging."""

    def __init__(self):
        self._log = logging.getLogger("qt")

    def __call__(self, mode, context, message):
        # PyQt6 qInstallMessageHandler signature: (QtMsgType, QMessageLogContext, str)
        msg = message.strip()
        if mode == 0:      # QtDebugMsg
            self._log.debug(msg)
        elif mode == 1:    # QtWarningMsg
            self._log.warning(msg)
        elif mode == 2:    # QtCriticalMsg
            self._log.error(msg)
        elif mode == 3:    # QtFatalMsg
            self._log.critical(msg)
        else:
            self._log.info(msg)


def _setup_excepthook():
    """Intercept all uncaught Python exceptions (main thread + background threads)."""

    original_excepthook = sys.excepthook
    log = logging.getLogger("crash")

    def _custom_excepthook(exc_type, exc_value, exc_tb):
        log.critical(
            "UNCAUGHT EXCEPTION in main thread\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )
        # Also print to stderr so console users see it immediately
        original_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _custom_excepthook

    # Python 3.8+ threading exception hook
    if hasattr(threading, "excepthook"):
        original_threading_excepthook = threading.excepthook

        def _custom_threading_excepthook(args):
            log.critical(
                "UNCAUGHT EXCEPTION in thread %s\n%s",
                args.thread.name if args.thread else "<unknown>",
                "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
            )
            if original_threading_excepthook:
                original_threading_excepthook(args)

        threading.excepthook = _custom_threading_excepthook


def _setup_faulthandler():
    """Enable faulthandler to catch C-level crashes (SEGV, etc.) and write to log file."""
    log_path = os.path.join(LOG_DIR, f"workmanager_{datetime.now().strftime('%Y-%m-%d')}.log")
    # Open in append mode; faulthandler writes raw bytes directly to the fd
    _fh_file = open(log_path, "ab")
    faulthandler.enable(_fh_file)
    # Register SIGUSR1 for manual dump (Unix only; harmless on Windows)
    try:
        faulthandler.register(signal.SIGUSR1, all_threads=True)
    except Exception:
        pass


def _setup_qt_handler():
    """Bridge Qt messages into Python logging."""
    try:
        from PyQt6.QtCore import qInstallMessageHandler
        qInstallMessageHandler(_QtMessageHandler())
    except Exception:
        pass


def setup_logging(level: int = logging.INFO) -> None:
    """
    Call once at application startup (before QApplication).
    Configures root logger, daily rotating files, stderr output,
    and global crash interceptors.
    """
    # Ensure log directory exists
    os.makedirs(LOG_DIR, exist_ok=True)

    # Root logger configuration
    root = logging.getLogger()
    root.setLevel(level)

    # Remove any existing handlers to avoid duplication on reload
    for h in list(root.handlers):
        root.removeHandler(h)

    # Daily rotating file handler (keeps 7 days)
    log_path = os.path.join(LOG_DIR, f"workmanager_{datetime.now().strftime('%Y-%m-%d')}.log")
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_path,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(file_handler)

    # Console (stderr) handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(console_handler)

    # Crash handlers
    _setup_excepthook()
    _setup_faulthandler()
    _setup_qt_handler()

    logging.getLogger("workmanager").info("Logging initialized | level=%s | log_dir=%s", logging.getLevelName(level), LOG_DIR)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger under the 'wm' namespace."""
    return logging.getLogger(f"wm.{name}")
