import logging

def create_logger(log_dir):
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("astroforge")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    for handler in (logging.FileHandler(log_dir / "astroforge.log", encoding="utf-8"), logging.StreamHandler()):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger
