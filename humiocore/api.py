"""
This module implements an API object for interacting with the Humio API
"""

import asyncio
import json
import re
import time
from itertools import chain

import aiohttp
import pandas as pd
import requests
import structlog
import tzlocal
from tqdm import tqdm

from .utils import detailed_raise_for_status, tstrip

logger = structlog.getLogger(__name__)


class HumioAPI:
    def __init__(
        self, token=None, ingest_token=None, base_url="https://cloud.humio.com", **kwargs
    ):
        self.base_url = base_url
        self.api_version = "v1"
        self.token = token
        self.ingest_token = ingest_token
        self._base_headers = {"Content-Type": "application/json", "Accept": "application/json"}

    def headers(self, overrides=None):
        """Returns a base JSON header with optional overrides from kwargs"""

        if overrides is None:
            overrides = {}

        headers = {**self._base_headers, **overrides}
        if "authorization" not in set(k.lower() for k in headers) or not headers["authorization"]:
            logger.error("No token provided in Authorization header")
        elif not headers["authorization"].startswith("Bearer"):
            headers["authorization"] = "Bearer " + headers["authorization"]
        return headers

    def create_queryjob(
        self,
        query,
        repo,
        start=None,
        end=None,
        live=False,
        tz_offset=0,
        timeout=30,
        literal_time=False,
    ):
        """
        Creates a remote queryjob and returns its job ID.

        NOTE: Queryjobs can return at most 200 results for filter searches
              and 1500 results for aggregated searches (unless you're sneaky
              and add a `tail(10000)`).

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
        tz_offset : int, optional
            Timezone offset in minutes, see Humio documentation. By default 0
        timeout : int, optional
            Timeout in seconds for HTTP requests before giving up. By default 30
        literal_time : bool, optional
            If True, disable all parsing of the provided start and end times, by default False

        Returns
        -------
        dict
            A dictionary with a job id and other metadata
        """

        headers = self.headers({"authorization": self.token, "accept": "application/json"})
        url = f"{self.base_url}/api/{self.api_version}/repositories/{repo}/queryjobs"

        search_details = {}
        payload = {"queryString": query, "isLive": live, "timeZoneOffsetMinutes": tz_offset}

        if live:
            end = None

        if literal_time:
            if start:
                payload["start"] = start
                search_details["time_start"] = start
            if end:
                payload["end"] = end
                search_details["time_stop"] = end
        else:
            if start:
                payload["start"] = int(start.timestamp() * 1000)
                search_details["time_start"] = start.tz_convert(
                    tzlocal.get_localzone()
                ).isoformat()
            if end:
                payload["end"] = int(end.timestamp() * 1000)
                search_details["time_stop"] = end.tz_convert(tzlocal.get_localzone()).isoformat()
            if start and end and not literal_time:
                search_details["time_span"] = tstrip(end - start)

        logger.info(
            "Creating new queryjob",
            json_payload=(json.dumps(payload)),
            repo=repo,
            **search_details,
        )

        queryjob = requests.post(url, json=payload, headers=headers, timeout=timeout)
        detailed_raise_for_status(queryjob)
        return queryjob.json()

    def consume_queryjob(self, repo, job_id, timeout=30, minwait=0.1, quiet=True):
        """
        Checks an existing remote queryjob continously and returns all its
        properties on completion.

        NOTE: Queryjobs can return at most 200 results for filter searches
              and 1500 results for aggregated searches (unless you're sneaky
              and add a `tail(10000)`).

        Returns:
            dict: The job's complete JSON structure with events and metadata
        """

        job = self.check_queryjob(repo, job_id)
        done = job["done"]

        with tqdm(total=job["metaData"]["totalWork"], leave=True, disable=quiet) as bar:
            while not done:
                wait = float(job["metaData"]["pollAfter"]) / 1000
                if wait < minwait:
                    wait = minwait
                time.sleep(wait)

                job = self.check_queryjob(repo, job_id, timeout=timeout)
                done = job["done"]
                bar.update(job["metaData"]["workDone"] - bar.n)
            bar.update(bar.n)
            bar.close()
        logger.debug("Queryjob completed", meta=json.dumps(job["metaData"]))
        return job

    def check_queryjob(self, repo, job_id, timeout=30):
        """Checks a remote queryjob once

        Returns:
            dict: The job's JSON metadata
        """

        headers = self.headers({"authorization": self.token, "accept": "application/json"})
        url = f"{self.base_url}/api/{self.api_version}/repositories/{repo}/queryjobs/{job_id}"

        job = requests.get(url, headers=headers, timeout=timeout)
        detailed_raise_for_status(job)
        return job.json()

    def delete_queryjob(self, repo, job_id):
        """Stops and deletes a remote queryjob

        Returns:
            str: The returned status code
        """

        headers = self.headers({"authorization": self.token, "accept": "application/json"})
        url = f"{self.base_url}/api/{self.api_version}/repositories/{repo}/queryjobs/{job_id}"

        job = requests.delete(url, headers=headers)
        detailed_raise_for_status(job)
        return job.status_code

    def async_search(self, query, repos, start, end, tz_offset=0, timeout=60, limit=10):
        """
        Execute queries async for all the requested repositories.

        Returns:
            list: The events as a list of dicts with the event fields

        Holds all results in memory, so should not be used for very large results.
        See also :func:`~humiocore.HumioAPI.streaming_search`
        """

        logger.warning(
            "Async search is deprecated and will be removed in the future. Try Streaming search as an alternative."
        )

        headers = self.headers({"authorization": self.token})
        urls = [
            f"{self.base_url}/api/{self.api_version}/dataspaces/{repo}/query" for repo in repos
        ]

        payload = {
            "queryString": query,
            "isLive": False,
            "timeZoneOffsetMinutes": tz_offset,
            "start": int(start.timestamp() * 1000),
            "end": int(end.timestamp() * 1000),
        }

        async def fetch(session, url, headers, payload):
            async with session.post(url, headers=headers, json=payload) as response:
                logger.info("Sent POST request", url=url)

                if response.status >= 400:
                    text = await response.text()
                    logger.error(
                        "Humio returned an error",
                        status=response.status,
                        reason=response.reason,
                        response_body=text,
                    )
                    response.raise_for_status()

                data = await response.json(encoding=response.get_encoding())
                logger.info(
                    "Received POST response",
                    events=len(data),
                    status=response.status,
                    content_type=response.content_type,
                    encoding=response.get_encoding(),
                    url_path=response.url.path,
                )
                return data

        async def dispatch(urls, headers, payload, connector):
            async with aiohttp.ClientSession(connector=connector) as session:
                logger.debug("Established new client session")

                tasks = []
                for url in urls:
                    tasks.append(asyncio.ensure_future(fetch(session, url, headers, payload)))
                logger.info(
                    "Registered all task",
                    json_payload=(json.dumps(payload)),
                    tasks=len(tasks),
                    time_start=start.tz_convert(tzlocal.get_localzone()).isoformat(),
                    time_stop=end.tz_convert(tzlocal.get_localzone()).isoformat(),
                    time_span=tstrip(end - start),
                    repos=repos,
                )
                return await asyncio.gather(*tasks)

        connector = aiohttp.TCPConnector(limit=limit)
        loop = asyncio.get_event_loop()
        future = asyncio.ensure_future(dispatch(urls, headers, payload, connector=connector))
        events = []
        try:
            events = list(chain.from_iterable(loop.run_until_complete(future)))
            logger.info("All tasks completed", total_events=len(events))
        except KeyboardInterrupt:
            pass
        except aiohttp.client_exceptions.ClientResponseError:
            logger.exception("An exception occured while awaiting task completion")
        finally:
            tasks = [t for t in asyncio.Task.all_tasks() if t is not asyncio.Task.current_task()]
            for task in tasks:
                task.cancel()
        return events

    def streaming_search(self, query, repos, start=None, end=None, tz_offset=0, timeout=60):
        """
        Execute syncronous streaming queries for all the requested repositories.

        Parameters
        ----------
        query : string
            The query string to execute against each repository
        repos : list
            List of repository names (strings) to query
        start : pd.Timestamp, optional
            Pandas tz-aware Timestamp to start searches from. Default None meaning all time
        end : pd.Timestamp, optional
            Pandas tz-aware Timestamp to search until. Default None meaning now
        tz_offset : int, optional
            Timezone offset in minutes, see Humio documentation. By default 0
        timeout : int, optional
            Timeout in seconds for HTTP requests before giving up. By default 60

        Yields:
            dict: The event fields
        """

        headers = self.headers({"authorization": self.token, "accept": "application/x-ndjson"})
        urls = [
            f"{self.base_url}/api/{self.api_version}/repositories/{repo}/query" for repo in repos
        ]

        search_details = {}
        payload = {"queryString": query, "isLive": False, "timeZoneOffsetMinutes": tz_offset}

        if start:
            payload["start"] = int(start.timestamp() * 1000)
            search_details["time_start"] = start.tz_convert(tzlocal.get_localzone()).isoformat()
        if end:
            payload["end"] = int(end.timestamp() * 1000)
            search_details["time_stop"] = end.tz_convert(tzlocal.get_localzone()).isoformat()
        if start and end:
            search_details["time_span"] = tstrip(end - start)

        logger.info(
            "Creating new streaming jobs",
            json_payload=(json.dumps(payload)),
            repos=repos,
            **search_details,
        )

        with requests.Session() as session:
            session.headers.update(headers)

            for url in urls:
                job = session.post(url, json=payload, stream=True, timeout=timeout)
                detailed_raise_for_status(job)

                for event in job.iter_lines(decode_unicode=True):
                    yield json.loads(event)

    def ingest_unstructured(self, events=None, fields=None, soft_limit=2 ** 20, dry=False):
        """
        TODO: Doesn't support 'content-encoding': 'gzip' yet

        Send the provided events iterable and fields dict to humio for ingestion.
        Ingestion will be done in batches according to the event length soft limit.
        Events that exceed the limit will still be sent, but will be sent alone and
        throw a warning.
        """

        headers = self.headers({"authorization": self.ingest_token})
        url = f"{self.base_url}/api/v1/ingest/humio-unstructured"

        if dry:
            logger.warn("Running in dry mode, no events will be ingested")

        if events is None:
            events = []
        if fields is None:
            fields = {}

        def _send(headers, url, messages, fields, soft_limit, dry):
            messages_length = len("".join(messages))
            logger.info(
                "Preparing ingestion message",
                events=len(messages),
                events_length=(messages_length),
                soft_limit=soft_limit,
                fields=fields,
            )

            if messages_length > 0:
                payload = [{"messages": messages}]
                if fields:
                    payload[0]["fields"] = fields
                logger.debug("Ingestion request prepared", json_payload=json.dumps(payload))

                if not dry:
                    req = requests.post(url, json=payload, headers=headers)
                    detailed_raise_for_status(req)

        pending = []
        for event in events:
            if len("".join(pending)) >= soft_limit:
                logger.warn(
                    "An event exceeds the soft limit",
                    length=len("".join(pending)),
                    soft_limit=soft_limit,
                )
                _send(headers, url, pending, fields, soft_limit, dry)
                del pending[:]
            elif len("".join(pending)) + len(event) >= soft_limit:
                _send(headers, url, pending, fields, soft_limit, dry)
                del pending[:]
            pending.append(event)
        _send(headers, url, pending, fields, soft_limit, dry)

        logger.info("All ingestions complete")

    def repositories(self):
        """
        Returns a dictionary of repositories and views, except those with
        names matching the ignore pattern
        """

        headers = self.headers({"authorization": self.token})
        url = f"{self.base_url}/graphql"
        query = """
                query {
                    searchDomains {
                        name, isStarred
                        __typename
                        ... on Repository {
                            uncompressedByteSize, timeOfLatestIngest
                        }
                        permissions {
                            administerAlerts, administerDashboards,  administerFiles,
                            administerMembers, administerParsers, administerQueries, read, write
                        }
                        roles {
                            role {
                                name
                            }
                        }
                    }
                }"""
        req = requests.post(url, json={"query": query}, headers=headers)
        detailed_raise_for_status(req)

        if not req.json():
            logger.error("No repositories or views found, verify that your token is valid")

        raw_repositories = [raw_repo for raw_repo in req.json()["data"]["searchDomains"]]

        repositories = dict()
        for repo in raw_repositories:
            try:
                repositories[repo["name"]] = {
                    "type": repo["__typename"].lower(),
                    "last_ingest": pd.to_datetime(repo["timeOfLatestIngest"])
                    if "timeOfLatestIngest" in repo
                    else None,
                    "read_permission": repo["permissions"]["read"],
                    "write_permission": repo["permissions"]["write"],
                    "queryadmin_permission": repo["permissions"]["administerQueries"],
                    "dashboardadmin_permission": repo["permissions"]["administerDashboards"],
                    "parseradmin_permission": repo["permissions"]["administerParsers"],
                    "fileadmin_permission": repo["permissions"]["administerFiles"],
                    "alertadmin_permission": repo["permissions"]["administerAlerts"],
                    "roles": [role["role"]["name"] for role in repo["roles"]],
                    "uncompressed_bytes": repo["uncompressedByteSize"]
                    if "uncompressedByteSize" in repo
                    else 0,
                    "favourite": repo["isStarred"],
                }
            except (KeyError, AttributeError) as exc:
                logger.exception(
                    "Couldn't map repository/view object",
                    repo=repo.get("name"),
                    error_message=exc,
                )
        return repositories

    def create_update_parser(self, repos, parser, source):
        """
        Creates or updates a parser with the given name and source in the specified repo

        Throws an exception on HTTP errors, but reports and continues on GraphQL errors

        Returns:
            A dict of mutation types listing the affected repositories
        """

        headers = self.headers({"authorization": self.token})
        url = f"{self.base_url}/graphql"
        result = {"created": [], "updated": [], "unchanged": [], "failed": []}

        for repo in set(repos):
            get = f"""
                    query {{
                        repository(name: {json.dumps(repo)}) {{
                            name
                            parser(name: {json.dumps(parser)}) {{
                                name
                                isBuiltIn
                                sourceCode
                            }}
                            permissions {{
                                administerParsers
                            }}
                        }}
                    }}"""

            create = f"""
                    mutation {{
                        createParser(input: {{
                            repositoryName: {json.dumps(repo)}, name: {json.dumps(parser)},
                            sourceCode: {json.dumps(source)}, testData: [], tagFields: []
                        }}) {{
                            __typename
                        }}
                    }}"""

            update = f"""
                    mutation {{
                        updateParser(
                            repositoryName: {json.dumps(repo)}, name: {json.dumps(parser)},
                            input: {{
                                sourceCode: {json.dumps(source)}
                            }}
                        ) {{
                        __typename
                        }}
                    }}"""

            req = requests.post(url, json={"query": get}, headers=headers)
            detailed_raise_for_status(req)

            existing_repo = req.json().get("data")
            if not existing_repo:
                logger.error(
                    "Did not find a repo with the given name, verify its existence and your access",
                    repo=repo,
                )
                result["failed"].append(repo)
                continue

            existing_parser = existing_repo["repository"].get("parser")
            if not existing_parser:
                logger.info("Creating new parser", repo=repo, parser=parser)
                req = requests.post(url, json={"query": create}, headers=headers)
                detailed_raise_for_status(req)
                response = req.json()
                if response.get("errors"):
                    logger.error(
                        "Failed to create new parser",
                        repo=repo,
                        parser=parser,
                        json_payload=(json.dumps(response)),
                    )
                    result["failed"].append(repo)
                    continue
                else:
                    result["created"].append(repo)
            else:
                old_source = existing_parser.get("sourceCode")
                if old_source != source:
                    logger.info("Updating existing parser", repo=repo, parser=parser)
                    req = requests.post(url, json={"query": update}, headers=headers)
                    detailed_raise_for_status(req)
                    response = req.json()
                    if response.get("errors"):
                        logger.error(
                            "Failed to create new parser",
                            repo=repo,
                            parser=parser,
                            json_payload=(json.dumps(response)),
                        )
                        result["failed"].append(repo)
                        continue
                    else:
                        result["updated"].append(repo)
                else:
                    logger.info("Existing parser is identical", repo=repo, parser=parser)
                    result["unchanged"].append(repo)

        return result
