import structlog

logger = structlog.get_logger()
logger.info("Logging with structlog")
