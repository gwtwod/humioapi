"""
Collection of misc utility functions
"""

import warnings
import functools
import re
import urllib
import pendulum
import snaptime
import datetime
import tzlocal
from .exceptions import HumioTimestampException
from requests.exceptions import HTTPError
import structlog

logger = structlog.getLogger(__name__)


def ignore_warning(message="", category=Warning, module=""):
    """
    Decorator to ignore matching warnings during method execution.
    """

    def inner(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=Warning, module="")
                return func(*args, **kwargs)
        return wrapper
    return inner


@ignore_warning(message=".*pytz-deprecation-shim.*", module="pendulum")  # tzlocal prefers zoneinfo over pytz
def parse_ts(timestamp, stdlib=False):
    """
    Parses a provided timestamp string in either a millisecond-epoch, a
    relative snaptime token ("Splunk relative time modifier"), or a common
    timestring (ISO8601 and similar, supported by pendulum.parse).
    Returns a timezone-aware Pendulum DateTime object. Uses the local timezone
    unless the provided timestamp already provides a timezone.
    Millisecond-epochs are assumed to always be in UTC.

    Notes
    -----
    See `https://github.com/zartstrom/snaptime` for snaptime implementation.

    Parameters
    ----------
    timestamp:
        A timestamp in millisecond-epoch, a relative snaptime string, or a
        common timestring (ISO8601 and similar, supported by pendulum.parse).
    stdlib:
        If True, returns a stdlib datetime.datetime object rather than a
        pendulum.datetime object. See pendulum_to_stdlib() for details.

    Returns
    -------
    datetime: A timezone-aware pendulum or stdlib datetime object.
    """

    tz = tzlocal.get_localzone()
    if timestamp is None:
        timestamp = ""
    timestamp = str(timestamp)
    if timestamp.lower().startswith("now"):
        timestamp = ""

    try:
        timestamp = snaptime.snap_tz(datetime.datetime.now().astimezone(tz), timestamp, timezone=tz)
        if stdlib:
            return timestamp
        else:
            return pendulum.instance(timestamp)
    except snaptime.main.SnapParseError:
        # Not a valid snaptime token
        pass

    try:
        timestamp = pendulum.parse(timestamp, tz=tz)
        if stdlib:
            return pendulum_to_stdlib(timestamp)
        else:
            return timestamp
    except (pendulum.exceptions.ParserError, ValueError):
        # Not a known valid timestring
        pass

    try:
        timestamp = pendulum.from_format(timestamp, fmt="x", tz="utc")
        if stdlib:
            return pendulum_to_stdlib(timestamp.astimezone(tz=tz))
        else:
            return timestamp.astimezone(tz=tz)
    except (ValueError):
        # Not a valid millisecond-epoch
        pass

    raise HumioTimestampException(
        f"Could not understand the provided timestamp ({timestamp}). Try something less ambigous?"
    )


def pendulum_to_stdlib(pendulum_datetime):
    """
    Helper function to convert Pendulum.datetime to stdlib datetime.datetime
    since Pandas doesn't play well with Pendulum.
    See: https://github.com/sdispater/pendulum/pull/485 and
         https://github.com/pandas-dev/pandas/issues/15986
    """

    return datetime.datetime.fromisoformat(pendulum_datetime.isoformat())


def detailed_raise_for_status(res, truncate=400):
    """
    Take a requests response object and expand the raise_for_status method
    to return more helpful errors containing the response body.

    Beware that any sensitive details in the response body will be leaked.

    By default response bodies are truncated to 400 characters.
    """

    try:
        res.raise_for_status()
    except HTTPError as exc:
        if hasattr(res, "text") and res.text:
            details = f"Response body: {str(res.text)}"
            details = (details[:truncate] + "..") if len(details) > truncate else details
            # Raise <exception> from None means we don't get the extra context from raising
            # a new exception inside the try-except block
            raise HTTPError(f"{exc}. {details}") from None
        else:
            raise exc


def parse_humio_url(url):
    """
    Parses a Humio search URL and returns the components needed to create a
    similar search using the Humio API

    Returns
    -------
    Tuple
        (query : str,
        repo : str,
        start : DateTime,
        stop : DateTime)
    """

    parsed = urllib.parse.urlparse(url)
    querystring = urllib.parse.parse_qs(parsed.query)

    query = querystring.get("query", [""])[0]
    repo = parsed.path.split("/")[1]

    start = querystring.get("start", ["24h"])[0]
    if start.isdigit():
        start = parse_ts(start)
    else:
        # Humio doesnt use signed relative time modifiers. Unlike Splunk's
        # relative time modifiers, Humio's are are always in the past
        start = parse_ts(f"-{start}")

    stop = querystring.get("end", ["now"])[0]
    stop = parse_ts(stop)

    return (query, repo, start, stop)


def create_humio_url(base_url, repo, query, start, stop, scheme="https"):
    """Returns a Humio search URL built from the provided components"""

    start = int(parse_ts(start).timestamp() * 1000)
    stop = int(parse_ts(stop).timestamp() * 1000)

    query = {"query": query, "start": start, "end": stop}

    url = urllib.parse.ParseResult(
        scheme=scheme,
        netloc=urllib.parse.urlsplit(base_url).netloc,
        path=f"/{repo}/search",
        params=None,
        query=urllib.parse.urlencode(query, quote_via=urllib.parse.quote),
        fragment=None,
    )

    url = urllib.parse.urlunparse(url)
    return url


def tstrip(timestamp):
    """
    Returns a more succinct shortened timestring by stripping off trailing
    zeros and timezone information. Also works on pd.Timedelta.
    """

    components = re.compile(r"[T\s:]00$|[\.,]0+$|([\.,]\d+)0+$|\+\d+:\d+$|^0 days ")
    timestamp = str(timestamp)

    while True:
        output = components.sub(r"\1", timestamp)
        if output == timestamp:
            return output
        timestamp = output
