import logging
import logging.config
import sys
import os
import re
import tzlocal
import datetime as dt
import inspect
import structlog
import colorama

logger = structlog.getLogger("unhandled_exception:%s" % __name__)
LOGGED_TZ = tz = tzlocal.get_localzone()
SECRETS = re.compile(r"\bpassword\b|\bpassord\b|\bsecret\b|\btoken\b|\bsst\b|\bapi.key\b", flags=re.IGNORECASE)

SORT_ORDER = {
    k: v
    for v, k in enumerate(
        [
            "timestamp",
            "log_level",
            "thread",
            "logger",
            "logger_function",
            "logger_file",
            "event",
        ]
    )
}


def _order_logging_keys(logger, method_name, event_dict):  # pylint: disable=unused-argument
    """
    Returns an OrderedDict with a spesific key order.
    Unnamed keys are alphabetically sorted at the end.
    """
    keys = len(SORT_ORDER)
    return dict(sorted(event_dict.items(), key=lambda i: SORT_ORDER.get(i[0], keys)))


def stringify_dict(dictionary, scrub=True, mask="**CENSORED**"):
    """
    Recursively attempts to stringify dict values while censoring
    possible secrets based on known secret key names, e.g. `sst`, `password`
    """

    if not isinstance(dictionary, dict):
        return dictionary

    stringified_dict = {}
    for key, value in dictionary.items():
        if isinstance(value, dict):
            stringify_dict(value)
        else:
            if isinstance(key, str) and SECRETS.search(key):
                stringified_dict[key] = mask
            elif isinstance(value, (int, str, bool)):
                stringified_dict[key] = value
            elif isinstance(value, dt.datetime):
                stringified_dict[key] = value.isoformat()
            else:
                try:
                    stringified_dict[key] = str(value)
                except Exception:
                    stringified_dict[key] = value
    return stringified_dict


def _stringify_payloads(logger, method_name, event_dict):
    """Attempts to stringify payloads and censor possible passwords/secrets"""
    payload = event_dict.pop("payload_dict", None)
    if payload:
        if "payload" not in event_dict.keys():
            event_dict["payload"] = stringify_dict(payload)
        else:
            event_dict["payload_dict"] = stringify_dict(payload)
    return event_dict


def _add_timestamp(logger, method_name, event_dict):
    event_dict["timestamp"] = dt.datetime.now(tz=LOGGED_TZ).isoformat(timespec="milliseconds")
    return event_dict


def _add_logger_source_info(_logger, _method_name, event_dict):
    record = event_dict.get("_record")
    if record:
        event_dict["logger_function"] = record.funcName
        event_dict["logger_file"] = f"{record.filename}:{record.lineno}"
    else:
        frame, _module_str = structlog._frames._find_first_app_frame_and_name(additional_ignores=[__name__])
        frame_info = inspect.getframeinfo(frame)
        event_dict["logger_function"] = frame_info.function
        event_dict["logger_file"] = f"{os.path.basename(frame_info.filename)}:{frame_info.lineno}"
    return event_dict


def initialize_logging(configure_once=True, fmt="json", level=20, logger_overrides=None):
    """
    Configures stdlib logging and Structlog logging with the provided format
    and level on the root logger, and adds an exception hook automatically
    logging all uncaught exceptions (except from KeyboardInterrupt).

    Parameters
    ----------
    configure_once : bool, optional
        Do nothing and return if Structlog has already been configured. By default True
    fmt: string, optional
        Formatter name to use with the console handler. Can be json or human.
    logger_overrides : dict, optional
        Loggers dict to override the default DictConfig.loggers with. By default None

    Returns
    -------
    The logging DictConfig used to configure stdlib logging
    """

    # Log processor chains that apply to both Stdlib and Structlog events
    pre_processor_chain = [
        _add_timestamp,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.format_exc_info,  # render exc_info under "exception", if any
        structlog.processors.StackInfoRenderer(),  # render stacktrace under "stack", if any
        _add_logger_source_info,
        _stringify_payloads,
        _order_logging_keys,
    ]

    # Log processor chains that apply to only Structlog events
    processor_chain = pre_processor_chain + [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.PositionalArgumentsFormatter(),  # insert positional arguments like stdlib
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        # structlog.processors.ExceptionPrettyPrinter(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,  # This processor must come last in the chain
    ]

    loggers = {
        "": {
            "handlers": ["console"],
            "level": level,
        },
        "parso": {  # Bugfix for https://github.com/ipython/ipython/issues/10946
            "handlers": ["console"],
            "level": logging.INFO,
            "propagate": False,
        },
        "urllib3.connectionpool": {
            "handlers": ["console"],
            "level": logging.WARNING,
            "propagate": False,
        },
    }

    if logger_overrides is not None:
        loggers = {**loggers, **logger_overrides}

    level_styles = structlog.dev.ConsoleRenderer.get_default_level_styles()
    level_styles["trace"] = colorama.Fore.CYAN
    level_styles["success"] = colorama.Fore.GREEN

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.processors.JSONRenderer(ensure_ascii=False),
                "foreign_pre_chain": pre_processor_chain,
            },
            "human": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.dev.ConsoleRenderer(colors=True, level_styles=level_styles, pad_event=40),
                "foreign_pre_chain": pre_processor_chain,
            },
        },
        "handlers": {
            "console": {"class": "logging.StreamHandler", "formatter": fmt},
            "null": {"class": "logging.NullHandler"},
        },
        "loggers": loggers,
    }

    if configure_once and structlog.is_configured():
        return config

    logging.config.dictConfig(config)
    structlog.configure(
        processors=processor_chain,
        context_class=structlog.threadlocal.wrap_dict(dict),
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    sys.excepthook = logwrap_exception

    return config


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
