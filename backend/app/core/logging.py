import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        standard_attrs = set(vars(logging.makeLogRecord({})).keys())

        extra_fields = {
            key: value for key, value in record.__dict__.items() if key not in standard_attrs
        }

        if extra_fields:
            log_data["extra"] = extra_fields

        return json.dumps(log_data)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JSONFormatter()
        if logging.getLogger().handlers
        else logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)

    for name in ("sqlalchemy", "alembic"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


if __name__ == "__main__":
    configure_logging()
    logger = get_logger(__name__)
    logger.info("Logging configured successfully")
    logger.warning("This is a warning")
    logger.error("This is an error")
    logger.critical("This is a critical error")
    logger.debug("This is a debug message")
