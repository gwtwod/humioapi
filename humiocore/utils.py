"""
Collection of misc utility functions
"""

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
        logger.debug(
            "Could not parse the provided timestring with snaptime", timestring=timestring
        )

    try:
        timestamp = pd.to_datetime(timestring, utc=False)
        if timestamp.tzinfo:
            return timestamp
        else:
            return timestamp.tz_localize(tz=tzlocal.get_localzone())
    except ValueError:
        logger.debug("Could not parse the provided timestring with pandas", timestring=timestring)

    raise ValueError(
        f"Could understand the provided timestring ({timestring}). Try something less ambigous?"
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


def humio_to_timeseries(events, timefield='_bucket', datafields=None, groupby=None, fill=None, sep='@'):
    '''Convert a list of Humio event dicts to a datetime-indexed pandas dataframe
    '''

    df = pd.DataFrame.from_records(events)
    df = df.apply(pd.to_numeric, errors='ignore')

    df[timefield] = pd.to_datetime(df[timefield], unit='ms', utc=True)
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
