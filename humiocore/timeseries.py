"""
This module provides helper objects to manage searches
"""

from threading import Lock

from .utils import humio_to_timeseries, parse_ts
import pandas as pd
import structlog

logger = structlog.getLogger(__name__)


class WindowedTimeseries:
    """Define an aggregated search for timeseries data in an optionally moving
    time window.

    On first update all data for the requested window is fetched. New updates
    will trigger a new search backwards based on the refresh_window.

    Example:
            `start='-60m@m'`, `end='-1m@m'`, `refresh_window='2m'`
            This will look back 2 minutes from the end when updating and
            overwrite with new data for the overlapping window.
    """

    def __init__(
        self,
        api,
        query,
        repo,
        start,
        end,
        freq,
        timefield="_bucket",
        title="",
        trusted_pickle=None,
    ):
        self.api = api
        self.query = query
        self.repo = repo
        self.start = start
        self.end = end

        self.freq = freq
        self.timefield = timefield
        self.title = title

        self.data = pd.DataFrame()
        self.performance = []
        self.trusted_pickle = trusted_pickle

        self.lock = Lock()

        if self.trusted_pickle:
            self.load_df()

        logger.debug(
            "Initialized search object definition",
            start=self.start,
            end=self.end,
            event_count=len(self.data),
        )

    def sanity_check(self):
        # Check that the searchstring span is equal to the pandas freq
        pass

    def load_df(self):
        """Loads and unpickles a trusted pickled pd.DataFrame"""
        try:
            self.data = pd.read_pickle(self.trusted_pickle)
            logger.debug("Loaded pickled data from file", event_count=len(self.data))
        except FileNotFoundError:
            pass

    def save_df(self):
        """Saves a pickled `pd.DataFrame` to file"""
        self.data.to_pickle(self.trusted_pickle)
        logger.debug("Saved pickled data to file", event_count=len(self.data))

    def current_refresh_window(self):
        """Returns the smallest possible search window required to update missing data

        Returns:
            (`pd.Timestamp`, `pd.Timestamp`)
        """

        wanted_buckets = pd.date_range(
            parse_ts(self.start), parse_ts(self.end), freq=self.freq, closed="left"
        )
        missing = wanted_buckets.difference(self.data.index.dropna(how="all").unique())
        if missing.empty:
            return None, None

        start = missing.min()
        end = missing.max() + pd.Timedelta(self.freq)
        return start, end

    def update(self):
        """
        Find and update missing data in the current `pd.DataFrame` according
        to the start and end timestamps. Optionally load and save a pickled
        `pd.DataFrame` to file.

        Concurrent calls will return non-blocking until the first call
        has completed its update request.

        Returns: None
        """

        if self.trusted_pickle:
            self.load_df()

        if self.lock.acquire(blocking=False):
            try:
                start, end = self.current_refresh_window()
                if all([start, end]):
                    new_data = list(self.api.streaming_search(self.query, self.repo, start, end))

                    if new_data:
                        data = humio_to_timeseries(new_data, self.timefield, freq=self.freq)
                        # TODO: consider dropping existing data and warn if columns differ?
                        self.data = data.combine_first(self.data)
                    else:
                        logger.error("Update failed.")
                else:
                    logger.info("Data is already current. Not fetching new data.")

                # Remove data outside the current search window
                self.data = self.data[
                    (self.data.index >= str(parse_ts(self.start)))
                    & (self.data.index < str(parse_ts(self.end)))
                ]

                if self.trusted_pickle:
                    self.save_df()
            finally:
                self.lock.release()
        else:
            logger.info("Data update already in progress in another thread")
