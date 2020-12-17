"""
Collection of misc utility functions
"""

import re
import urllib
import pendulum
import snaptime
import datetime
import tzlocal
import asyncio
from dateutil.tz import gettz
from httpx import HTTPStatusError
from .exceptions import TimestampException
import structlog

logger = structlog.getLogger(__name__)


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

    raise TimestampException(f"Could not understand the provided timestamp ({timestamp}). Try something less ambigous?")


def pendulum_to_stdlib(pendulum_datetime):
    """
    Helper function to convert Pendulum.datetime to stdlib datetime.datetime
    since Pandas doesn't play well with Pendulum.
    See: https://github.com/sdispater/pendulum/pull and
         https://github.com/pandas-dev/pandas/issues/15986
    """

    # Could just use C-optimized .fromisoformat() and .isoformat() in py3.7
    tzinfo = gettz(pendulum_datetime.tzinfo.name)
    return datetime.datetime(
        year=pendulum_datetime.year,
        month=pendulum_datetime.month,
        day=pendulum_datetime.day,
        hour=pendulum_datetime.hour,
        minute=pendulum_datetime.minute,
        second=pendulum_datetime.second,
        microsecond=pendulum_datetime.microsecond,
        tzinfo=pendulum_datetime.tzinfo,
    ).astimezone(tzinfo)


def consume_async(async_generator, loop):
    """
    Iterates the provided async generator by running it in the provided
    eventloop, yielding the results back as soon as they become available.
    It is your responsibility to create and eventually close the loop.

    Example
    -------
    queries = [{
        "query": "chad index.html | select(@timestamp)",
        "repo": "sandbox",
        "start": "-7d@d",
        "stop": "-4d@d",
        }, {
        "query": "chad index.html | select(@rawstring)",
        "repo": "sandbox",
        "start": "-4d@d",
        "stop": "now",
    }]

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        tasks = api.async_streaming_search(queries, loop=loop, concurrent_limit=10)
        for item in humioapi.consume_async(tasks, loop):
            print(item)
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    Yields
    ------
        Whatever the provided async generators decide to yield
    """

    def iter_over_async(coro, loop):
        coro = coro.__aiter__()

        async def get_next():
            try:
                obj = await coro.__anext__()
                return False, obj
            except StopAsyncIteration:
                return True, None

        while True:
            done, obj = loop.run_until_complete(get_next())
            if done:
                break
            yield obj

    for item in iter_over_async(async_generator, loop):
        yield item


def detailed_raise_for_status(res, truncate=400):
    """
    Take a httpx response object and expand the raise_for_status method
    to return more helpful errors containing the response body. Beware that
    any sensitive details contained in the response body will be leaked.

    By default response bodies are truncated to 400 characters.
    """

    try:
        res.raise_for_status()
    except HTTPStatusError as exc:
        if hasattr(res, "text") and res.text:
            details = f"Response body: {str(res.text)}"
            details = (details[:truncate] + "..") if len(details) > truncate else details
            # Raise <exception> from None means we don't get the extra context clutter
            # from raising a new exception inside the try-except block
            raise HTTPStatusError(f"{exc}. {details}", request=res.request, response=res) from None
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
