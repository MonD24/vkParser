"""
logger.py — цветной логгер для всего проекта
"""
import logging
import colorlog
import os

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Консольный обработчик с цветом
    ch = colorlog.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s[%(asctime)s] %(name)s %(levelname)s%(reset)s: %(message)s",
        datefmt="%H:%M:%S",
        log_colors={
            "DEBUG":    "cyan",
            "INFO":     "green",
            "WARNING":  "yellow",
            "ERROR":    "red",
            "CRITICAL": "bold_red",
        }
    ))

    # Файловый обработчик
    fh = logging.FileHandler(
        os.path.join(LOG_DIR, f"{name}.log"), encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "[%(asctime)s] %(name)s %(levelname)s: %(message)s"
    ))

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger
