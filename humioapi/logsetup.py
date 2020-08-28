import logging
import logging.config
import sys
import threading
import structlog
import structlog_pretty

logger = structlog.getLogger("unknown_origin:%s" % __name__)


def _add_thread_info(_, __, event_dict):
    event_dict["thread"] = threading.current_thread().name
    return event_dict


def _filter_payloads(_, __, event_dict):
    """Filter out known verbose fields"""
    return {k: v for k, v in event_dict.items() if k not in ["payload", "json_payload", "raw", "raw_response"]}


def setup_excellent_logging(level=logging.INFO, verbose_fields=True):
    levels = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET']

    if str(level).isdigit():
        if level < len(levels):
            level = levels[max(level, 0)]
        else:
            level = levels[-1]
    elif level not in levels:
        raise ValueError("Logging level must be one of %s when using named levels" % levels)

    timestamper = structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S")
    pre_chain = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _add_thread_info,
        timestamper,
    ]

    if not verbose_fields:
        pre_chain.append(_filter_payloads)

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "colored": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processor": structlog.dev.ConsoleRenderer(colors=True),
                    "foreign_pre_chain": pre_chain,
                }
            },
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "colored"}
            },
            "loggers": {
                "": {
                    "handlers": ["console"],
                    "level": level,
                    "propagate": True,
                },
                "parso": {
                    "handlers": ["console"],
                    "level": logging.INFO,
                    "propagate": False,
                },  # Bugfix for https://github.com/ipython/ipython/issues/10946
                'urllib3.connectionpool':  {
                    'handlers': ['console'],
                    'level': logging.WARNING,
                }
            },
        }
    )

    structlog.configure(
        processors=pre_chain
        + [
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog_pretty.JSONPrettifier(["json", "json_payload", "meta"]),
            structlog_pretty.SyntaxHighlighter(
                {"json": "json", "json_payload": "json", "meta": "json"}
            ),
            structlog_pretty.MultilinePrinter(["raw", "raw_response"]),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    def logwrap_exception(exc_type, exc_value, exc_traceback):
        """
        Causes all uncaught exceptions to be logged through structlog.
        The real origin/logger will not be available, so the traceback is
        necessary to find the actual cause of the error.
        """

        # Ignore Ctrl-C interrupts
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logger.critical(
            "Uncaught exception",
            payload=repr(exc_value),
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    sys.excepthook = logwrap_exception
