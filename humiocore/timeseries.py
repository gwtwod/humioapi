"""
This module provides a helper object to manage an updateable timechart search
through the export API which doesn't support aggregated live searches.

NOTE: IF you stumbled upon this, know that this is pretty much just a POC/playground.
"""

import json
from threading import Lock

import pandas as pd
import structlog

from snaptime import snap

from .utils import humio_to_timeseries, parse_ts

logger = structlog.getLogger(__name__)


class WindowedTimeseries:
    """
    Define an aggregated search for timeseries data in the spesified time
    window which may be static or moving (with relative timestamps).

    Parameters
    ----------
    api : humiocore.HumioAPI
        An API instance for interacting with Humio
    query : string
        A Humio query string to execute
    repos : list
        A list of repositories to search against
    start : string
        A snaptime-token (-1h@h) or timestring to search after
    end : string
        A snaptime-token (@h) or timestring to search before
    freq : str
        A pandas frequency string to use when calculating missing buckets.
        This *must* correspond to the frequency used in the Humio search.
    timefield : str, optional
        The name of the timestamp field in the search result, by default "_bucket"
    datafields : list, optional
        A list of all data fields ("columns") in the search result, by default None
        which means all fields remaining after groupby are used.
    groupby : list, optional
        A list of all groupby fields ("series") in the search result, by default None
        which means no grouping is performed.
    title : str, optional
        A title identifying this search - use however you like, by default ""
    cutoff_start : str, optional
        An unsigned snaptime-token to cutoff the head of the final DataFrame, by default "0m"
    cutoff_end : str, optional
        An unsigned snaptime-token to cutoff the tail of the final DataFrame, by default "0m"
    trusted_pickle : string, optional
        A path to a trusted pickle-file to save/load the DataFrame, by default None
    """

    def __init__(
        self,
        api,
        query,
        repos,
        start,
        end,
        freq,
        timefield="_bucket",
        datafields=None,
        groupby=None,
        title="",
        cutoff_start="0m",
        cutoff_end="0m",
        trusted_pickle=None,
    ):
        self.api = api
        self.query = query
        self.repos = repos
        self.start = start
        self.end = end

        self.freq = freq
        self.timefield = timefield
        self.datafields = datafields
        self.groupby = groupby
        self.title = title
        self.cutoff_start = cutoff_start
        self.cutoff_end = cutoff_end

        self.data = pd.DataFrame()
        self.trusted_pickle = trusted_pickle
        self._metadata = {}
        self.lock = Lock()

        if self.trusted_pickle:
            self.load_df()

        logger.debug(
            "Initialized search object definition",
            start=self.start,
            end=self.end,
            event_count=len(self.data),
        )

    def copyable_attributes(self, ignore=None):
        """
        Provieds all instance attributes that can be considered copyable

        Parameters
        ----------
        ignore : list, optional
            A list of attributes to ignore, by default all non-copyable keys

        Returns
        -------
        dict
            A dictionary of all copyable keys
        """
        if ignore is None:
            ignore = ["api", "data", "trusted_pickle", "lock", "_metadata"]
        return {k: v for k, v in self.__dict__.items() if k not in ignore}

    def sanity_check(self):
        # Check that the searchstring span is equal to the pandas freq
        pass

    def load_df(self):
        """Loads and unpickles a trusted pickled pd.DataFrame"""

        try:
            with open(self.trusted_pickle + ".meta", "r") as metafile:
                meta = json.load(metafile)

                for key, value in self.copyable_attributes().items():
                    if key in meta and value != meta[key]:
                        logger.info(
                            "Search has changed since DataFrame was pickled",
                            parameter=key,
                            stored_value=meta[key],
                            current_value=value,
                        )
                        self.data = pd.DataFrame()
                        return

            self.data = pd.read_pickle(self.trusted_pickle + ".pkl")
            logger.debug(
                "Loaded pickled data from file",
                event_count=len(self.data),
                pickle=self.trusted_pickle + ".pkl",
            )
        except FileNotFoundError:
            pass

    def save_df(self):
        """Saves a pickled `pd.DataFrame` to file"""
        with open(self.trusted_pickle + ".meta", "w") as metafile:
            json.dump(self.copyable_attributes(), metafile)
        self.data.to_pickle(self.trusted_pickle + ".pkl")
        logger.debug(
            "Saved pickled data to file",
            event_count=len(self.data),
            pickle=self.trusted_pickle + ".pkl",
        )

    def current_refresh_window(self):
        """Returns the smallest possible search window required to update missing data

        Returns:
            (`pd.Timestamp`, `pd.Timestamp`)
        """

        # Shrink the search window according to the cutoffs and generate all buckets
        # that should appear in the current DataFrame
        wanted_buckets = pd.date_range(
            snap(parse_ts(self.start), "+" + self.cutoff_start),
            snap(parse_ts(self.end), "-" + self.cutoff_end),
            freq=self.freq,
            closed="left",
        )
        missing = wanted_buckets.difference(self.data.index.dropna(how="all").unique())

        if missing.empty:
            logger.debug(
                "Calculated minimum required search range and found no missing buckets",
                current_start=self.data.index.min(),
                current_stop=self.data.index.max(),
                wanted_start=wanted_buckets.min(),
                wanted_stop=wanted_buckets.max(),
            )
            return None, None

        # Expand the search window again according to the cutoffs
        start = snap(missing.min(), "-" + self.cutoff_start)
        end = snap(missing.max() + pd.Timedelta(self.freq), "+" + self.cutoff_end)

        logger.debug(
            "Calculated minimum required search range",
            current_start=self.data.index.min(),
            current_stop=self.data.index.max(),
            wanted_start=wanted_buckets.min(),
            wanted_stop=wanted_buckets.max(),
            next_start=start,
            next_stop=end,
        )
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
                    new_data = list(self.api.streaming_search(self.query, self.repos, start, end))

                    if new_data:
                        logger.info("Search returned new data", events=len(new_data))
                        data = humio_to_timeseries(
                            new_data,
                            timefield=self.timefield,
                            datafields=self.datafields,
                            groupby=self.groupby,
                        )
                        self.data = data.combine_first(self.data)

                    else:
                        logger.warn("Search didnt return any data")
                else:
                    logger.info("Data is already current. Not fetching new data.")

                # Clean up data outside the current search window, adjusted with the cutoffs
                self.data = self.data[
                    (self.data.index >= str(snap(parse_ts(self.start), "+" + self.cutoff_start)))
                    & (self.data.index < str(snap(parse_ts(self.end), "-" + self.cutoff_end)))
                ]

                if self.trusted_pickle:
                    self.save_df()
            finally:
                self.lock.release()
        else:
            logger.info("Data update already in progress in another thread", lock=self.lock)
