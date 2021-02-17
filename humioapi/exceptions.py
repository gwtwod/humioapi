from humiolib.HumioExceptions import HumioException


class HumioTimestampException(HumioException):
    """Error raised when all possible timestamp parsing strategies have failed"""

    pass


class HumioBackendWarning(UserWarning, HumioException):
    """Warning raised when the Humio backend has returned a warning"""

    pass


class HumioMaxResultsExceededWarning(UserWarning, HumioException):
    """Warning raised when a Humio query has returned partial results, for example due to pagination"""

    pass
