"""
This module implements an API object for interacting with the Humio API
"""

import types
import json
import tzlocal
import structlog
from humiolib.HumioClient import HumioClient, HumioIngestClient
from humiolib.QueryJob import StaticQueryJob
from .utils import parse_ts
from .monkeypatch import poll_until_done, poll

logger = structlog.getLogger(__name__)


class HumioAPI:
    def __init__(self, base_url, token=None, ingest_token=None, **kwargs):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.ingest_token = ingest_token

    def create_queryjob(
        self, query, repo, start="-2d@d", stop="now", live=False, tz_offset=0, literal_time=False, **kwargs
    ):
        """
        Creates a remote queryjob.

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
        **kwargs :
            Optional parameters forwarded to the humiolib/requests-call

        Returns
        -------
            A pollable monkey-patched humiolib QueryJob providing `poll()` as a generator function.
        """

        if live:
            if literal_time is not True:
                raise ValueError("The literal_time parameter must be True for live searches")
            stop = "now"

        start = start if literal_time else parse_ts(start)
        stop = stop if literal_time else parse_ts(stop)

        payload = {
            "query_string": query,
            "start": start if literal_time else int(start.timestamp() * 1000),
            "end": stop if literal_time else int(stop.timestamp() * 1000),
            "timezone_offset_minutes": tz_offset,
            "is_live": live,
        }

        logger.debug(
            "Creating new queryjob",
            json_payload=(json.dumps(payload)),
            repo=repo,
            start=start if literal_time else start.in_timezone(tzlocal.get_localzone()).isoformat(),
            stop=stop if literal_time else stop.in_timezone(tzlocal.get_localzone()).isoformat(),
            span="N/A" if literal_time else (stop - start).as_interval().in_words(),
        )

        client = HumioClient(base_url=self.base_url, repository=repo, user_token=self.token)
        queryjob = client.create_queryjob(**{**payload, **kwargs})

        # The original poll() actually polls continously until done, not once as the name might imply.
        # Replace it with a generator instead, polling on each iteration and returning the current result.
        queryjob.poll = types.MethodType(poll, queryjob)

        # The original poll_until_done() can get stuck polling forever (https://github.com/humio/python-humio/issues/14)
        # Replace it with a simple helper method to return the final poll result in an efficient manner.
        queryjob.poll_until_done = types.MethodType(poll_until_done, queryjob)
        return queryjob

    def streaming_search(self, query, repo, start="-2d@d", stop="now", tz_offset=0, literal_time=False, **kwargs):
        """
        Execute a syncronous streaming query against the selected repository.

        Parameters
        ----------
        query : string
            The query string to execute against each repository
        repo : string
            A repository name to query
        start : Timestring (or any valid Humio format if literal_time=True), optional
            Timestring to start at, see humioapi.parse_ts() for details. Default -2d@d.
        stop : Timestring (or any valid Humio format if literal_time=True), optional
            Timestring to stop at, see humioapi.parse_ts() for details. Default now.
        tz_offset : int, optional
            Timezone offset in minutes, see Humio documentation. Default 0
        literal_time : bool, optional
            If True, disable all parsing of the provided start and end times. Default False
        **kwargs :
            Optional parameters forwarded to the humiolib/requests-call

        Yields:
            dict: The event fields
        """

        start = start if literal_time else parse_ts(start)
        stop = stop if literal_time else parse_ts(stop)

        payload = {
            "query_string": query,
            "start": start if literal_time else int(start.timestamp() * 1000),
            "end": stop if literal_time else int(stop.timestamp() * 1000),
            "timezone_offset_minutes": tz_offset,
            "is_live": False,
        }

        logger.debug(
            "Creating new streaming search",
            json_payload=(json.dumps(payload)),
            repo=repo,
            start=start if literal_time else start.in_timezone(tzlocal.get_localzone()).isoformat(),
            stop=stop if literal_time else stop.in_timezone(tzlocal.get_localzone()).isoformat(),
            span="N/A" if literal_time else (stop - start).as_interval().in_words(),
        )

        client = HumioClient(base_url=self.base_url, repository=repo, user_token=self.token)
        for event in client.streaming_query(**{**payload, **kwargs}):
            yield event

    def ingest_unstructured(self, events, parser=None, fields=None, tags=None, soft_limit=2 ** 20, dry=False, **kwargs):
        """
        Send the provided iterable of events to humio for ingestion in batches
        controlled by the soft limit. If an event is too large to fit the soft
        limit it will still be sent (alone) and throw a warning.

        Parameters
        ----------
        events : list
            List of events (strings) to ingest
        parser : str
            Name of a Humio parser to handle the ingested events.
        fields : dict
            Fields to add to each ingested event
        tags : dict
            Tags to add to each ingested event
        soft_limit : int
            A soft limit to use when calculating batch sizes (string length)
        dry : boolean
            If true, no events will actually be sent to Humio
        **kwargs :
            Optional parameters forwarded to the humiolib/requests-call
        """

        if dry:
            logger.warn("Running in dry mode, no events will be ingested")

        def ingest(events, parser=None, fields=None, tags=None, dry=False, **kwargs):
            batch_size = len("".join(events))
            if batch_size >= soft_limit:
                logger.warn("An event exceeds the soft limit", batch_size=batch_size, soft_limit=soft_limit)
            logger.info("Sending", events=len(events), batch_size=batch_size, parser=parser, fields=fields, tags=tags)

            if batch_size > 0 and not dry:
                client.ingest_messages(messages=events, parser=parser, fields=fields, tags=tags, **kwargs)

        client = HumioIngestClient(base_url=self.base_url, ingest_token=self.ingest_token)

        buffer = []
        for event in events:
            if len("".join(buffer)) + len(event) >= soft_limit:
                # if adding the next message would exceed the soft_limit, we can send and clear the buffer
                ingest(events=buffer, parser=parser, fields=fields, tags=tags, dry=dry, **kwargs)
                del buffer[:]
            buffer.append(event)
        ingest(events=buffer, parser=parser, fields=fields, tags=tags, dry=dry, **kwargs)

    def repositories(self, **kwargs):
        """
        Returns a dictionary of repositories and views

        Parameters
        ----------
        **kwargs :
            Optional parameters forwarded to the humiolib/requests-call

        Returns
        ----------
            dict: Metadata for all discovered repositories
        """

        client = HumioClient(base_url=self.base_url, repository="unused", user_token=self.token)
        headers = client._default_user_headers

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

        payload = {
            "query": query,
            "variables": None,
        }

        response = client.webcaller.call_graphql(headers=headers, json=payload, **kwargs)
        if not response.json():
            logger.error("No repositories or views found, verify that your token is valid")

        raw_repositories = [raw_repo for raw_repo in response.json()["data"]["searchDomains"]]

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
                logger.exception("Couldn't map repository/view object", repo=repo.get("name"), error_message=exc)
        return repositories

    def create_update_parser(self, repos, parser, source, **kwargs):
        """
        Creates or updates a parser with the given name and source in the specified repo

        Throws an exception on HTTP errors, but reports and continues on GraphQL errors

        Returns:
            A dict of mutation types listing the affected repositories
        """

        client = HumioClient(base_url=self.base_url, repository="unused", user_token=self.token)
        headers = client._default_user_headers

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

            response = client.webcaller.call_graphql(headers=headers, json={"query": get}, **kwargs)
            existing_repo = response.json().get("data")
            if not existing_repo:
                logger.error("Did not find a repo with the given name, verify its existence/your access", repo=repo)
                result["failed"].append(repo)
                continue

            existing_parser = existing_repo["repository"].get("parser")
            if not existing_parser:
                logger.info("Creating new parser", repo=repo, parser=parser)
                response = client.webcaller.call_graphql(headers=headers, json={"query": create}, **kwargs)
                response = response.json()
                if response.get("errors"):
                    logger.error(
                        "Failed to create new parser", repo=repo, parser=parser, json_payload=(json.dumps(response))
                    )
                    result["failed"].append(repo)
                    continue
                else:
                    result["created"].append(repo)
            else:
                old_source = existing_parser.get("sourceCode")
                if old_source != source:
                    logger.info("Updating existing parser", repo=repo, parser=parser)

                    response = client.webcaller.call_graphql(headers=headers, json={"query": update}, **kwargs)
                    response = response.json()
                    if response.get("errors"):
                        logger.error(
                            "Failed to create new parser", repo=repo, parser=parser, json_payload=(json.dumps(response))
                        )
                        result["failed"].append(repo)
                        continue
                    else:
                        result["updated"].append(repo)
                else:
                    logger.info("Existing parser is identical", repo=repo, parser=parser)
                    result["unchanged"].append(repo)

        return result

