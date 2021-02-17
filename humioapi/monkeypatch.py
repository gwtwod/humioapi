import warnings
from .exceptions import HumioMaxResultsExceededWarning, HumioBackendWarning


def warning_on_one_line(message, category, filename, lineno, file=None, line=None):
    return "%s:%s: %s: %s\n" % (filename, lineno, category.__name__, message)


def patched_poll_until_done(self, **kwargs):
    raise NotImplementedError(
        "Method disabled, see humiolib issue #14. Use poll() instead since this method can get stuck polling forever."
    )


def poll_safe(self, raise_warnings=True, **kwargs):
    """
    Calls `poll()` on the queryjob and adds an extra attribute `warnings` to
    the resulting PollResult containing a list of any returned warnings.

    Parameters
    ----------
    warn : bool, optional
        Raises warnings each time a warning is encountered, by default True

    Warns
    -----
    HumioBackendWarning
        When the Humio backend has returned a warning.
    MaxResultsExceededWarning
        When the QueryJob has returned a partial result due to pagination.
    >>> import warnings
    >>> warnings.simplefilter('ignore', humioapi.HumioBackendWarning)
    >>> warnings.simplefilter('ignore', humioapi.HumioMaxResultsExceededWarning)

    Returns
    -------
    PollResult
        A humiolib poll result object with events, metadata and warnings.
    """

    result = self.poll()
    result.warnings = []

    warnings.formatwarning = warning_on_one_line
    for message in result.metadata.get("warnings", []):
        result.warnings.append(message)
        if raise_warnings:
            warnings.warn(message, HumioBackendWarning, stacklevel=0)

    if result.metadata.get("extraData", {}).get("hasMoreEvents", "") == "true":
        message = (
            "The search results exceeded the limits for this API."
            " There are more results available in the backend than available here."
            " Possible workaround: pipe to head() or tail() with limit=n."
        )
        result.warnings.append(message)
        if raise_warnings:
            warnings.warn(message, HumioMaxResultsExceededWarning, stacklevel=0)

    return result
