"""
Collection of misc utility functions
"""

import re
import urllib
import pandas as pd
import snaptime
import structlog
import tzlocal
from requests.exceptions import HTTPError

logger = structlog.getLogger(__name__)


def parse_ts(timestring):
    """
    Parses a snapstring or common timestamp (ISO8859 and similar) and
    returns a timezone-aware pandas timestamp using the local timezone.
    """
    if timestring.lower().startswith("now"):
        timestring = ""

    try:
        return snaptime.snap(pd.Timestamp.now(tz=tzlocal.get_localzone()), timestring)
    except snaptime.main.SnapParseError:
        pass

    try:
        timestamp = pd.to_datetime(timestring, utc=False)
        if timestamp.tzinfo:
            return timestamp
        else:
            return timestamp.tz_localize(tz=tzlocal.get_localzone())
    except (ValueError, OverflowError):
        pass

    try:
        timestamp = pd.to_datetime(timestring, unit="ms", utc=True)
        return timestamp.tz_convert(tz=tzlocal.get_localzone())
    except (ValueError, pd.errors.OutOfBoundsDatetime):
        pass

    raise ValueError(
        f"Could not understand the provided timestring ({timestring}). Try something less ambigous?"
    )


def detailed_raise_for_status(res):
    """
    Take a "requests" response object and expand the raise_for_status method to return more helpful errors
    Beware that this could potentially leak sensitive details from the response-body.
    """

    try:
        res.raise_for_status()
    except HTTPError as err:
        if hasattr(res, "text") and res.text:
            # Raise <exception> from None means we don't get the extra context from raising
            # a new exception inside the try-except block
            raise HTTPError(f"{err}. Response body: {str(res.text)}") from None
        else:
            raise err


def humio_to_timeseries(
    events, timefield="_bucket", datafields=None, groupby=None, fill=None, sep="@"
):
    """Convert a list of Humio event dicts to a datetime-indexed pandas dataframe
    """

    df = pd.DataFrame.from_records(events)
    df = df.apply(pd.to_numeric, errors="coerce")

    df[timefield] = pd.to_datetime(df[timefield], unit="ms", utc=True)
    df = pd.pivot_table(df, index=timefield, values=datafields, columns=groupby, fill_value=fill)
    df = df.tz_convert(tzlocal.get_localzone())

    # Make column headers more human friendly if we're working with a multiindex
    if isinstance(df.columns, pd.MultiIndex):
        if len(df.columns.levels) == 2:
            df.columns = [sep.join(col).strip() for col in df.columns.values]
        elif len(df.columns.levels) > 2:
            df.columns = [sep.join(col).strip() for col in df.columns.values]

    # pandas bug https://github.com/pandas-dev/pandas/issues/25439
    import warnings  # noqa

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = df.sort_index()

    return df


def parse_humio_url(url):
    """
    Parses a Humio search URL and returns the components needed to create a
    similar search using the Humio API

    Returns
    -------
    tuple
        query : str
        repo : str
        start : pd.Timestamp
        end : pd.Timestamp
    """

    parsed = urllib.parse.urlparse(url)
    querystring = urllib.parse.parse_qs(parsed.query)

    query = querystring.get("query", [""])[0]
    repo = parsed.path.split("/")[1]

    start = querystring.get("start", ["24h"])[0]
    if start.isdigit():
        start = parse_ts(start)
    else:
        # Humio doesnt use signed relative time modifiers
        start = parse_ts(f"-{start}")

    end = querystring.get("end", ["now"])[0]
    end = parse_ts(end)

    return (query, repo, start, end)


def create_humio_url(base_url, repo, query, start, end, scheme="https"):
    """Returns a Humio search URL built from the provided components"""

    start = int(start.timestamp() * 1000)
    end = int(end.timestamp() * 1000)

    query = {"query": query, "start": start, "end": end}

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
    Returns a shortened and more imprecise timestring by stripping off
    trailing zeros and timezone information. Also works on pd.Timedelta.
    """

    components = re.compile(r"[T\s:]00$|[\.,]0+$|([\.,]\d+)0+$|\+\d+:\d+$|^0 days ")
    timestamp = str(timestamp)

    while True:
        output = components.sub(r"\1", timestamp)
        if output == timestamp:
            return output
        timestamp = output
