"""
This module provides a helper object to manage long-lived queryjobs
"""

import json
import structlog
from .api import HumioAPI
from .utils import humio_to_timeseries, parse_ts
from requests.exceptions import HTTPError

logger = structlog.getLogger(__name__)


class QueryJob:
    """Defines a pollable long-lived queryjob.

    Parameters
    ----------
    query : string
        The query string to execute
    repo : string
        A repository or view name
    start : pd.Timestamp (or any valid Humio format if literal_time=True), optional
        Pandas tz-aware Timestamp to start searches from. Default None meaning all time
    end : pd.Timestamp (or any valid Humio format if literal_time=True), optional
        Pandas tz-aware Timestamp to search until. Default None meaning now
    live : bool, optional
        Mark the search as live in Humio, by default False
    literal_time : bool, optional
        If True, disable all parsing of the provided start and end times, by default False
    job_id : str, optional
        Job ID for an existing queryjob, by default None
    token : str
        Your personal *secret* Humio token
    base_url : str
        The base URL for your Humio instance, for example https://cloud.humio.com
    """

    def __init__(
        self,
        token,
        base_url,
        query,
        repo,
        start=None,
        end=None,
        live=False,
        literal_time=False,
        job_id=None,
    ):

        self.client = HumioAPI(token=token, base_url=base_url)
        self.query = query
        self.repo = repo
        self.start = start
        self.end = end
        self.live = live
        self.literal_time = literal_time
        self.job_id = job_id
        self.events = None
        self.metadata = None
        self.warnings = None

    def __str__(self):
        return json.dumps(
            {
                "query": self.query,
                "repo": self.repo,
                "start": self.start,
                "end": self.end,
                "live": self.live,
                "literal_time": self.literal_time,
                "job_id": self.job_id,
                "event_count": len(self.events),
                "metadata": self.metadata,
                "warnings": self.warnings,
            },
            ensure_ascii=False,
        )

    def poll(self):
        """
        Poll Humio for the latest data for the provided queryjob. If there is
        already a known job ID for this search, that job ID will be polled.
        Otherwise a new queryjob will be started.

        Successful polling will update the events, metadata and warnings attributes.

        Raises
        ------
        requests.exceptions.HTTPError
            Raises HTTPError on HTTP error status codes from Humio.

        Returns
        -------
        list
            A list of dictionaries of event fields
        """

        if self.job_id:
            try:
                job_state = self.client.consume_queryjob(self.repo, self.job_id, quiet=True)
                self.events = job_state.get("events", [])
                self.metadata = job_state.get("metaData", {})
                self.warnings = self.metadata.get("warnings", [])
                if self.metadata.get("extraData", {}).get("hasMoreEvents", "") == "true":
                    self.warnings.append(
                        "The search results exceeded the limit for this API. There are more results available than shown here."
                    )
            except HTTPError as exc:
                if exc.response.status_code == 404 and exc.response.text.startswith(
                    "No query with id"
                ):
                    logger.debug(
                        f"No existing query found with the provided job ID. Perhaps it was reaped due to inactivity?",
                        job_id=self.job_id,
                    )
                    self.job_id = None
                    self.poll()
                else:
                    raise exc
        else:
            job = self.client.create_queryjob(
                query=self.query,
                repo=self.repo,
                start=self.start,
                end=self.end,
                live=self.live,
                literal_time=self.literal_time,
            )
            self.job_id = job["id"]
            logger.info("Started new queryjob", job_id=self.job_id)
            self.poll()
        return self.events

    def delete(self):
        """Deletes (stops) the current job ID from Humio"""

        if self.job_id:
            job = self.client.delete_queryjob(repo=self.repo, job_id=self.job_id)
            logger.info("Deleted queryjob", job_id=self.job_id)
            return job
