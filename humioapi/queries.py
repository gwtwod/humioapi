import json
import textwrap


def _(string):
    """Dedent and strip the provided string"""
    return textwrap.dedent(string).strip()


class SearchDomains():
    """
    A collection of predefined GraphQL queries and mutations related to views,
    repositories ("searchdomains")
    """

    @staticmethod
    def searchDomainsSimple():
        return _("""
            query {
                searchDomains {
                    name: name
                    domaintype: __typename
                    description: description
                    isStarred: isStarred
                }
            }
        """)

    @staticmethod
    def searchDomains():
        return _("""
            query {
                searchDomains {
                    name: name
                    domaintype: __typename
                    description: description
                    isStarred: isStarred

                    read: isActionAllowed(action: ReadEvents)
                    administerDashboards: isActionAllowed(action: ChangeDashboards)
                    administerQueries: isActionAllowed(action: ChangeSavedQueries)
                    administerAlerts: isActionAllowed(action: ChangeTriggersAndActions)
                    administerParsers: isActionAllowed(action: ChangeParsers)
                    administerFiles: isActionAllowed(action: ChangeFiles)
                    administerDataSources: isActionAllowed(action: DeleteDataSources)
                    administerEvents: isActionAllowed(action: DeleteEvents)
                    administerIngestTokens: isActionAllowed(action: ChangeIngestTokens)

                    ... on SearchDomain {
                        groups {
                            displayName: displayName
                        }
                    }

                    ... on Repository {
                        timeOfLatestIngest: timeOfLatestIngest
                        compressedByteSizeOfMerged: compressedByteSizeOfMerged
                        uncompressedByteSizeOfMerged: uncompressedByteSizeOfMerged
                        compressedByteSize: compressedByteSize
                        uncompressedByteSize: uncompressedByteSize
                    }
                }
            }
        """)


class Parsers():

    @staticmethod
    def getParser(repo, parser):
        return _(f"""
            query {{
                repository(name: {json.dumps(repo)}) {{
                    name
                    parser(name: {json.dumps(parser)}) {{
                        id
                        name
                        isBuiltIn
                        tagFields
                        description
                        sourceCode
                        testData
                        }}
                    administerParsers: isActionAllowed(action: ChangeParsers)
                }}
            }}
        """)

    @staticmethod
    def createParser(repo, parser, source, testdata=None, tagfields=None):
        innerPayload = f"sourceCode: {json.dumps(source)}"
        if testdata:
            innerPayload += f"testData: {json.dumps(testdata)}"
        if tagfields:
            innerPayload += f"tagFields: {json.dumps(tagfields)}"

        return _(f"""
            mutation {{
                createParser(input: {{
                    repositoryName: {json.dumps(repo)},
                    id: {json.dumps(parser)},
                    name: {json.dumps(parser)},
                    {innerPayload}
                }}) {{
                    __typename
                }}
            }}
        """)

    @staticmethod
    def updateParser(repo, parser, source, testdata=None, tagfields=None):
        innerPayload = f"sourceCode: {json.dumps(source)}"
        if testdata:
            innerPayload += f"testData: {json.dumps(testdata)}"
        if tagfields:
            innerPayload += f"tagFields: {json.dumps(tagfields)}"

        return _(f"""
            mutation {{
                updateParser(
                    input: {{
                        repositoryName: {json.dumps(repo)},
                        id: {json.dumps(parser)},
                        name: {json.dumps(parser)},
                        {innerPayload}
                    }}
                ) {{
                __typename
                }}
            }}
        """)
