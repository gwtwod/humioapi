"""
This module provides a helper object to manage pollable long-lived queryjobs
"""

import warnings
import json
import structlog
from .exceptions import MaxResultsExceededWarning, HumioBackendWarning
from httpx import HTTPStatusError

logger = structlog.getLogger(__name__)


class QueryJob:
    """Defines a pollable long-lived queryjob.

    Parameters
    ----------
    client : humioapi.api.HumioAPI
        An instance of HumioAPI to use with this Queryjob.
    query : string
        The query string to execute
    repo : string
        A repository or view name
    start : Timestring (or any valid Humio format if literal_time=True), optional
        Timestring to start at, see humioapi.parse_ts() for details. Default -2d@d.
    stop : Timestring (or any valid Humio format if literal_time=True), optional
        Timestring to stop at, see humioapi.parse_ts() for details. Default now.
    live : bool, optional
        Mark the search as live in Humio, by default False
    literal_time : bool, optional
        If True, disable all parsing of the provided start and stop times, by default False
    job_id : str, optional
        Job ID for an existing queryjob, by default None
    """

    def __init__(self, client, query, repo, start="-2d@d", stop="now", live=False, literal_time=False, job_id=None):
        self.client = client
        self.query = query
        self.repo = repo
        self.start = start
        self.stop = stop
        self.live = live
        self.literal_time = literal_time
        self.job_id = job_id
        self.events = []
        self.done = False
        self.cancelled = False
        self.metadata = {}
        self.warnings = []

    def __str__(self):
        return json.dumps(
            {
                "query": self.query,
                "repo": self.repo,
                "start": self.start,
                "stop": self.stop,
                "live": self.live,
                "literal_time": self.literal_time,
                "job_id": self.job_id,
                "event_count": len(self.events),
                "done": self.done,
                "cancelled": self.cancelled,
                "metadata": self.metadata,
                "warnings": self.warnings,
            },
            ensure_ascii=False,
        )

    def poll(self, until_done=True, quiet=True, warn=True):
        """
        Poll Humio for the latest data for the provided queryjob. If there is already a known job ID for this search,
        that job ID will be polled. Otherwise a new queryjob will be started.

        If the provided job ID cannot be found on the Humio server, for example because it has been reaped, a new
        queryjob will be started.

        Successful polling will update the events, metadata and warnings attributes.

        Parameters
        ----------
        until_done: boolean, optional
            Polls continously until job is marked as done before returning if True. Default True.
        quiet: boolean, optional
            Show queryjob progress if False. Default True.
        warn: boolean, optional
            Issus warnings if the `warning` property contains warnings. Default True.

        Warns
        -----
        HumioBackendWarning
            When the Humio backend has returned a warning.
        MaxResultsExceededWarning
            When the queryjob has returned a partial result due to pagination.

        >>> import warnings
        >>> warnings.simplefilter('ignore', humioapi.HumioBackendWarning)
        >>> warnings.simplefilter('ignore', humioapi.MaxResultsExceededWarning)

        Raises
        ------
        httpx.HTTPStatusError
            Raises HTTPStatusError on HTTP error status codes from Humio

        Returns
        -------
        list
            A list of dictionaries containing the event fields and values
        """

        if self.job_id:
            try:
                if until_done:
                    job_state = self.client.consume_queryjob(self.repo, self.job_id, quiet=quiet)
                else:
                    job_state = self.client.check_queryjob(self.repo, self.job_id)

                self.events = job_state.get("events", [])
                self.done = job_state.get("done", False)
                self.cancelled = job_state.get("cancelled", False)
                self.metadata = job_state.get("metaData", {})

                self.warnings = self.metadata.get("warnings", [])
                if warn and self.warnings:
                    for message in self.warnings:
                        warnings.warn(message, HumioBackendWarning, stacklevel=2)

                # Humio doesn't warn when result is partial since the client is expected to paginate
                # Since we dont support pagination we create our own warning instead.
                if self.metadata.get("extraData", {}).get("hasMoreEvents", "") == "true":
                    message = (
                        "The search results exceeded the limits for this API."
                        " There are more results available in the backend than available here."
                        " Possible workaround: pipe to head() or tail() with limit=n."
                    )
                    self.warnings.append(message)
                    if warn:
                        warnings.warn(message, MaxResultsExceededWarning, stacklevel=2)

            except HTTPStatusError as exc:
                if exc.response.status_code == 404 and exc.response.text.startswith("No query with id"):
                    logger.debug(
                        "No existing query found with the provided job ID. Perhaps it was reaped due to inactivity?",
                        job_id=self.job_id,
                    )
                    self.job_id = None
                    self.poll(until_done=until_done, quiet=quiet, warn=warn)
                else:
                    raise exc
        else:
            job = self.client.create_queryjob(
                query=self.query,
                repo=self.repo,
                start=self.start,
                stop=self.stop,
                live=self.live,
                literal_time=self.literal_time,
            )
            self.job_id = job["id"]
            logger.info("Started new queryjob", job_id=self.job_id)
            self.poll(until_done=until_done, quiet=quiet, warn=warn)
        return self.events

    def delete(self):
        """Deletes (stops) the current job ID from Humio"""

        if self.job_id:
            job = self.client.delete_queryjob(repo=self.repo, job_id=self.job_id)
            logger.info("Deleted queryjob", job_id=self.job_id)
            return job
