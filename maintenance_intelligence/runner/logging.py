from loguru import logger
import sys
import time
import uuid


def setup_logger(level: str = "INFO"):
    logger.remove()
    logger.add(sys.stdout, level=level, serialize=False)


def get_logger(name: str = None):
    return logger.bind(logger_name=name) if name else logger


def run_id() -> str:
    return str(uuid.uuid4())


def timed(fn):
    def _wrap(*a, **k):
        t0 = time.time()
        try:
            return fn(*a, **k)
        finally:
            logger.info(
                {"event": "timing", "fn": fn.__name__, "ms": int((time.time() - t0) * 1000)}
            )

    return _wrap
