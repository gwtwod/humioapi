"""
This module implements an API object for interacting with the Humio API
"""

import asyncio
import json
import time
import tzlocal
import httpx
from httpx._models import Headers
import structlog
from tqdm import tqdm
from .utils import detailed_raise_for_status, parse_ts
from .exceptions import HumioAPIException

logger = structlog.getLogger(__name__)


class HumioAPI:
    def __init__(self, token=None, ingest_token=None, base_url="https://cloud.humio.com", **kwargs):
        self.base_url = base_url
        self.api_version = "v1"
        self.token = token
        self.ingest_token = ingest_token
        self._base_headers = Headers({"content-type": "application/json", "accept": "application/json"})

    def headers(self, overrides=None):
        """Returns a base JSON header with optional overrides from kwargs"""

        if overrides is None:
            overrides = {}

        headers = self._base_headers.copy()
        headers.update(overrides)

        if "authorization" not in headers:
            raise HumioAPIException("No token provided in authorization header")
        elif not headers["authorization"].startswith("Bearer"):
            headers["authorization"] = "Bearer " + headers["authorization"]
        return headers

    def create_queryjob(
        self,
        query,
        repo,
        start="-2d@d",
        stop="now",
        live=False,
        tz_offset=0,
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
        start : Timestring (or any valid Humio format if literal_time=True), optional
            Timestring to start at, see humioapi.parse_ts() for details. Default -2d@d.
        stop : Timestring (or any valid Humio format if literal_time=True), optional
            Timestring to stop at, see humioapi.parse_ts() for details. Default now.
        live : boolean
            Create a live queryjob. If True, literal_time must also be True,
            start must be a Humio relative time string and stop must be now.
        tz_offset : int, optional
            Timezone offset in minutes, see Humio documentation. By default 0
        literal_time : bool, optional
            If True, disable all parsing of the provided start and end times, by default False

        Returns
        -------
        dict
            A dictionary with the job id and other metadata
        """

        headers = self.headers({"authorization": self.token, "accept": "application/json"})
        url = f"{self.base_url}/api/{self.api_version}/repositories/{repo}/queryjobs"

        payload = {"queryString": query, "isLive": live, "timeZoneOffsetMinutes": tz_offset}

        if live:
            if literal_time is not True:
                raise ValueError("The literal_time parameter must be True for live searches")
            stop = "now"

        start = start if literal_time else parse_ts(start)
        stop = stop if literal_time else parse_ts(stop)

        payload = {
            "queryString": query,
            "isLive": live,
            "timeZoneOffsetMinutes": tz_offset,
            "start": start if literal_time else int(start.timestamp() * 1000),
            "end": stop if literal_time else int(stop.timestamp() * 1000),
        }

        logger.debug(
            "Creating new queryjob",
            json_payload=(json.dumps(payload)),
            repo=repo,
            start=start if literal_time else start.in_timezone(tzlocal.get_localzone()).isoformat(),
            stop=stop if literal_time else stop.in_timezone(tzlocal.get_localzone()).isoformat(),
            span="N/A" if literal_time else (stop - start).as_interval().in_words(),
        )

        queryjob = httpx.post(url, json=payload, headers=headers)
        detailed_raise_for_status(queryjob)
        return queryjob.json()

    def consume_queryjob(self, repo, job_id, minwait=0.1, quiet=True, async_client=None):
        """
        Continously checks an existing remote queryjob and returns all its
        properties on completion.

        NOTE: Queryjobs can return at most 200 results for filter searches
              and 1500 results for aggregated searches (unless you're sneaky
              and add a `tail(10000)`).

        Returns:
            dict: The job's complete JSON structure with events and metadata
        """

        logger.debug("Polling queryjob until done", repo=repo, job_id=job_id)
        job = self.check_queryjob(repo, job_id, async_client=async_client)
        done = job["done"]

        with tqdm(total=job["metaData"]["totalWork"], leave=True, disable=quiet) as bar:
            while not done:
                wait = float(job["metaData"]["pollAfter"]) / 1000
                if wait < minwait:
                    wait = minwait
                time.sleep(wait)

                job = self.check_queryjob(repo, job_id, async_client=async_client)
                done = job["done"]
                bar.update(job["metaData"]["workDone"] - bar.n)
            bar.update(bar.n)
            bar.close()
        logger.debug("Queryjob completed", meta=json.dumps(job["metaData"]))
        return job

    def check_queryjob(self, repo, job_id, async_client=None):
        """Checks a remote queryjob once and outputs its data

        Returns:
            dict: The job's JSON metadata
        """

        headers = self.headers({"authorization": self.token, "accept": "application/json"})
        url = f"{self.base_url}/api/{self.api_version}/repositories/{repo}/queryjobs/{job_id}"

        queryjob = httpx.get(url, headers=headers)
        detailed_raise_for_status(queryjob)
        return queryjob.json()

    def delete_queryjob(self, repo, job_id, async_client=None):
        """Stops and deletes a remote queryjob

        Returns:
            str: The returned status code
        """

        headers = self.headers({"authorization": self.token, "accept": "application/json"})
        url = f"{self.base_url}/api/{self.api_version}/repositories/{repo}/queryjobs/{job_id}"

        queryjob = httpx.delete(url, headers=headers)
        detailed_raise_for_status(queryjob)
        return queryjob.status_code

    def streaming_search(self, query, repos, start="-2d@d", stop="now", tz_offset=0, literal_time=False):
        """
        Execute syncronous streaming queries for all the requested repositories.

        Parameters
        ----------
        query : string
            The query string to execute against each repository
        repos : list
            List of repository names (strings) to query
        start : Timestring (or any valid Humio format if literal_time=True), optional
            Timestring to start at, see humioapi.parse_ts() for details. Default -2d@d.
        stop : Timestring (or any valid Humio format if literal_time=True), optional
            Timestring to stop at, see humioapi.parse_ts() for details. Default now.
        tz_offset : int, optional
            Timezone offset in minutes, see Humio documentation. Default 0
        literal_time : bool, optional
            If True, disable all parsing of the provided start and end times. Default False

        Yields:
            dict: The event fields
        """

        headers = self.headers({"authorization": self.token, "accept": "application/x-ndjson"})
        urls = [f"{self.base_url}/api/{self.api_version}/repositories/{repo}/query" for repo in repos]

        start = start if literal_time else parse_ts(start)
        stop = stop if literal_time else parse_ts(stop)

        payload = {
            "queryString": query,
            "isLive": False,
            "timeZoneOffsetMinutes": tz_offset,
            "start": start if literal_time else int(start.timestamp() * 1000),
            "end": stop if literal_time else int(stop.timestamp() * 1000),
        }

        logger.debug(
            "Creating new streaming search",
            json_payload=(json.dumps(payload)),
            repos=repos,
            start=start if literal_time else start.in_timezone(tzlocal.get_localzone()).isoformat(),
            stop=stop if literal_time else stop.in_timezone(tzlocal.get_localzone()).isoformat(),
            span="N/A" if literal_time else (stop - start).as_interval().in_words(),
        )

        with httpx.Client(headers=headers, timeout=httpx.Timeout(None)) as client:
            for url in urls:
                with client.stream("POST", url=url, json=payload,) as r:
                    # Humio doesn't set the charset, and httpx fails to detect it properly
                    r.headers.update({"content-type": "application/x-ndjson; charset=UTF-8"})
                    r.raise_for_status()

                    try:
                        for event in r.iter_lines():
                            yield json.loads(event)
                    except RemoteProtocolError:
                        # Humio doesn't necessarily have any more data to send when the query has completed
                        r.close()

    def async_streaming_tasks(
        self, loop, query, repos, start="-2d@d", stop="now", tz_offset=0, literal_time=False, concurrent_limit=10
    ):
        """
        Prepare and return an awaitable list of async streaming search tasks,
        each task being an asyncronous generator. Creates one task for each
        repository using the provided asyncio eventloop.

        Parameters
        ----------
        loop : asyncio.AbstractEventLoop
            An asyncio eventloop to schedule the tasks in. Required semaphore assignment.
        query : string
            The query string to execute against each repository
        repos : list
            List of repository names (strings) to query
        start : Timestring (or any valid Humio format if literal_time=True), optional
            Timestring to start at, see humioapi.parse_ts() for details. Default -2d@d.
        stop : Timestring (or any valid Humio format if literal_time=True), optional
            Timestring to stop at, see humioapi.parse_ts() for details. Default now.
        tz_offset : int, optional
            Timezone offset in minutes, see Humio documentation. Default 0
        literal_time : bool, optional
            If True, disable all parsing of the provided start and end times. Default False
        concurrent_limit : int, optional
            Number of streaming tasks to allow running concurrently.

        Returns:
            list: An awaitable providing a list of async generator tasks
        """

        headers = self.headers({"authorization": self.token, "accept": "application/x-ndjson"})
        urls = [f"{self.base_url}/api/{self.api_version}/repositories/{repo}/query" for repo in repos]

        timeout = httpx.Timeout(None)
        concurrent_limiter = asyncio.Semaphore(concurrent_limit, loop=loop)

        start = start if literal_time else parse_ts(start)
        stop = stop if literal_time else parse_ts(stop)

        payload = {
            "queryString": query,
            "isLive": False,
            "timeZoneOffsetMinutes": tz_offset,
            "start": start if literal_time else int(start.timestamp() * 1000),
            "end": stop if literal_time else int(stop.timestamp() * 1000),
        }

        logger.debug(
            "Preparing new asyncronous streaming tasks",
            json_payload=(json.dumps(payload)),
            repos=repos,
            start=start if literal_time else start.in_timezone(tzlocal.get_localzone()).isoformat(),
            stop=stop if literal_time else stop.in_timezone(tzlocal.get_localzone()).isoformat(),
            span="N/A" if literal_time else (stop - start).as_interval().in_words(),
        )

        async def stream(async_client, url, payload):
            async with concurrent_limiter:
                async with async_client.stream("POST", url=url, json=payload,) as ar:
                    # Humio doesn't set the charset, and httpx fails to detect it properly
                    ar.headers.update({"content-type": "application/x-ndjson; charset=UTF-8"})
                    ar.raise_for_status()
                    try:
                        async for line in ar.aiter_lines():
                            yield json.loads(line)
                    except httpx.RemoteProtocolError as e:
                        # Humio doesn't necessarily have any more data to send when the query has completed
                        logger.debug("Humio closed the connection prematurely", message=str(e))
                        await ar.aclose()

        async def prepare_streaming_tasks(urls, headers, payload, timeout):
            async with httpx.AsyncClient(headers=headers, timeout=timeout) as async_client:
                tasks = [stream(async_client, url, payload) for url in urls]
                return tasks

        return prepare_streaming_tasks(urls, headers=headers, payload=payload, timeout=timeout)

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
                    req = httpx.post(url, json=payload, headers=headers)
                    detailed_raise_for_status(req)

        pending = []
        for event in events:
            if len("".join(pending)) >= soft_limit:
                logger.warn(
                    "An event exceeds the soft limit", length=len("".join(pending)), soft_limit=soft_limit,
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
                            uncompressedByteSize,
                            timeOfLatestIngest
                            groups {
                                displayName
                            }
                        }
                        permissions {
                            administerAlerts, administerDashboards,  administerFiles,
                            administerMembers, administerParsers, administerQueries, read, write
                        }
                    }
                }"""
        req = httpx.post(url, json={"query": query}, headers=headers)
        detailed_raise_for_status(req)

        if not req.json():
            logger.error("No repositories or views found, verify that your token is valid")

        raw_repositories = [raw_repo for raw_repo in req.json()["data"]["searchDomains"]]

        repositories = dict()
        for repo in raw_repositories:
            try:
                repositories[repo["name"]] = {
                    "type": repo["__typename"].lower(),
                    "last_ingest": parse_ts(repo["timeOfLatestIngest"]) if "timeOfLatestIngest" in repo else None,
                    "read_permission": repo["permissions"]["read"],
                    "write_permission": repo["permissions"]["write"],
                    "queryadmin_permission": repo["permissions"]["administerQueries"],
                    "dashboardadmin_permission": repo["permissions"]["administerDashboards"],
                    "parseradmin_permission": repo["permissions"]["administerParsers"],
                    "fileadmin_permission": repo["permissions"]["administerFiles"],
                    "alertadmin_permission": repo["permissions"]["administerAlerts"],
                    "roles": [role["displayName"] for role in repo.get("groups", [])],
                    "uncompressed_bytes": repo["uncompressedByteSize"] if "uncompressedByteSize" in repo else 0,
                    "favourite": repo["isStarred"],
                }
            except (KeyError, AttributeError) as exc:
                logger.exception(
                    "Couldn't map repository/view object", repo=repo.get("name"), error_message=exc,
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

            req = httpx.post(url, json={"query": get}, headers=headers)
            detailed_raise_for_status(req)

            existing_repo = req.json().get("data")
            if not existing_repo:
                logger.error(
                    "Did not find a repo with the given name, verify its existence and your access", repo=repo,
                )
                result["failed"].append(repo)
                continue

            existing_parser = existing_repo["repository"].get("parser")
            if not existing_parser:
                logger.info("Creating new parser", repo=repo, parser=parser)
                req = httpx.post(url, json={"query": create}, headers=headers)
                detailed_raise_for_status(req)
                response = req.json()
                if response.get("errors"):
                    logger.error(
                        "Failed to create new parser", repo=repo, parser=parser, json_payload=(json.dumps(response)),
                    )
                    result["failed"].append(repo)
                    continue
                else:
                    result["created"].append(repo)
            else:
                old_source = existing_parser.get("sourceCode")
                if old_source != source:
                    logger.info("Updating existing parser", repo=repo, parser=parser)
                    req = httpx.post(url, json={"query": update}, headers=headers)
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
