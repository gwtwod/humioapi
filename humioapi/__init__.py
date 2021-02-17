from .api import HumioAPI
from .logsetup import initialize_logging
from .loadenv import humio_loadenv, loadenv
from .utils import parse_ts
from .exceptions import HumioMaxResultsExceededWarning, HumioBackendWarning

# Set default logging handler to avoid "No handler found" warnings.
# https://docs.python.org/3/howto/logging.html#configuring-logging-for-a-library
import logging
from logging import NullHandler

logging.getLogger(__name__).addHandler(NullHandler())
