import warnings
from collections import deque
from tqdm.auto import tqdm
from .exceptions import HumioMaxResultsExceededWarning, HumioBackendWarning


def warning_on_one_line(message, category, filename, lineno, file=None, line=None):
    return "%s:%s: %s: %s\n" % (filename, lineno, category.__name__, message)


def inspect_result_warnings(result, warn=True):
    seen_warnings = set()

    for message in result.metadata.get("warnings", []):
        seen_warnings.add(message)
        if warn:
            warnings.warn(message, HumioBackendWarning, stacklevel=0)

    if result.metadata.get("extraData", {}).get("hasMoreEvents", "") == "true":
        message = (
            "The search results exceeded the limits for this API."
            " There are more results available in the backend than available here."
            " Possible workaround: pipe to head() or tail() with limit=n."
        )
        seen_warnings.add(message)
        if warn:
            warnings.warn(message, HumioMaxResultsExceededWarning, stacklevel=0)

    return list(seen_warnings)


def poll(self, warn=True, progress=True, **kwargs):
    """
    A generator for polling the current result from the QueryJob.

    Also adds an extra attribute `warnings` to the resulting PollResult
    containing a list of any returned warning strings.

    Parameters
    ----------
    warn : bool, optional
        Raises warnings each time a warning is encountered, by default True

    Warns
    -----
    Warnings can be disabled by passing raise_warnings=False, or individually:
    >>> import warnings
    >>> warnings.simplefilter('ignore', humioapi.HumioBackendWarning)
    >>> warnings.simplefilter('ignore', humioapi.HumioMaxResultsExceededWarning)

    HumioBackendWarning
        When the Humio backend has returned a warning.
    MaxResultsExceededWarning
        When the QueryJob has returned a partial result due to pagination.

    Returns
    -------
    PollResult
        A humiolib poll result object with events, metadata and warnings.
    """

    link = "dataspaces/{}/queryjobs/{}".format(self.repository, self.query_id)

    headers = self._default_user_headers
    headers.update(kwargs.pop("headers", {}))

    with tqdm(total=0, unit="segment", disable=not progress) as bar:
        result = self._fetch_next_segment(link, headers, **kwargs)
        result.warnings = inspect_result_warnings(result, warn)

        bar.total = result.metadata["totalWork"]
        bar.refresh()
        bar.update(result.metadata["workDone"] - bar.n)
        yield result

        # Keep polling until the queryjob is completed
        while not self.segment_is_done:
            result = self._fetch_next_segment(link, headers, **kwargs)
            result.warnings = inspect_result_warnings(result, warn)
            bar.total = result.metadata["totalWork"]
            bar.refresh()
            bar.update(result.metadata["workDone"] - bar.n)
            yield result


def poll_until_done(self, warn=True, progress=True, **kwargs):
    """
    Polls the QueryJob continously until it has completed and returns the
    final result of the generator in an efficient manner.
    """

    return deque(self.poll(warn=warn, progress=progress, **kwargs), maxlen=1).pop()
