class HumioAPIException(Exception):
    """Base class for all HumioAPI exceptions."""

    pass


class TimestampException(HumioAPIException):
    """Error raised when all possible timestamp parsing strategies have failed"""

    pass


class HumioBackendWarning(UserWarning, HumioAPIException):
    """Warning raised when the Humio backend has returned a warning"""

    pass


class MaxResultsExceededWarning(UserWarning, HumioAPIException):
    """Warning raised when a Humio query has returned partial results, for example due to pagination"""

    pass
