# Changelog

## [Unreleased]

### Added

### Changed

### Fixed

### Deprecated

### Removed

## [0.8.2] - 2021-02-18

### Fixed

- Add back `dry` and `soft_limit` to `ingest_unstructured()`

## [0.8.1] - 2021-02-17

### Fixed

- Add humiolib dependency to pyproject.toml.


## [0.8.0] - 2021-02-17

From this release, this is merely a wrapper around the official humiolib to provide some opiniated helpers and APIs,
mainly improved timestamp parsing and `env` based config.

This also means all HTTP requests are now done through `requests` rather than `httpx`, since thats what `humiolib` uses.

### Changed

- Renamed `loadenv` to `humio_loadenv`, and added a more general `humio_loadenv`.
- `loadenv` and `humio_loadenv` can now accept multiple prefixes and config files.
- Streaming search now only allows one repo. Use `humio-search-all` or a `view` if you need more repos at once.

### Removed

- Asyncronous APIs, since `requests` only has syncronous support.
- All timeout options for all APIs, but you can pass stuff to `requests` directly through `kwargs`.


## [0.7.0] - 2021-01-31

### Changed

- Changed all syncronous requests through `httpx` to use urllib3 as networking backend rather than `httpcore` as a
temporary solution, since the humio-search-all and graphql endpoints started giving random HTTP 502s since Humio 1.18.
Will probably revert in the future when I can figure out whats up.
- Changed the `humioapi.loadenv()` helper to accept iterables of envs and prefixes as well as the old strings.


## [0.6.2] - 2020-12-17

### Changed

- Renamed `async_streaming_tasks` to `async_streaming_search` and reworked the API to make it easier to setup multiple
queries with different properties by passing queries as a list of dicts.
- Bumped dependency versions

### Fixed

Some README typos


## [0.6.1] - 2020-09-24

### Fixed

- Added color style to TRACE logging level in console renderer logging helper, since httpx defines that level (5).


## [0.6.0] - 2020-09-23

### Added

- Optional timeout parameters to search APIs. By default 30 seconds. Can be an integer og a httpx.Timeout.

### Changed

- Refactored logging helpers with a new function `humioapi.initialize_logging` providing sane structlog JSON (default) or Human readable logs depending on the chosen format.
- QueryJob now takes a client instance instead of a token and base_url
- Bumped dependency versions

### Fixed

- Use context manager with all `httpx` requests so connections are closed properly.

### Removed

- `humioapi.setup_excellent_logging` removed in favor of `humioapi.initialize_logging`


## [0.5.1] - 2020-08-29

### Fixed

- Renamed `end` to `start` in a few forgotten places (url util functions)
- Strip trailing slash in base urls instead of stupidy failing


## [0.5.0] - 2020-08-28

This release renames the module and repository to humioapi to better
communicate what this python module actually is.

### Added

- The `humioapi.async_streaming_tasks` function which constructs asyncronous HTTP streaming search tasks in the form of asyncronous generators.
- The `humioapi.consume_async` helper function which can be used to consume the asyncronous streaming tasks from a non-asyncronous context as if they were a ordinary python generator.

### Changed

- Removed `requests` in favor of `httpx`
- All `start` and `stop` parameters now accept multiple timestamps, which will be parsed with `humioapi.parse_ts`. In other words they can be `millisecond-epochs` (as Humio likes it), relative Splunk-style `snaptime tokens`, `iso8601 time strings` (or any other time format supported by `pendulum.parse`).
- Renamed `end` to `stop` in all API functions, since `start/stop` sound better to me than `start/end`, plus this has the bonus effect that the fields are sorted near each other in logging output :)
- Made `pandas` optional (its only used in the POC/playground timeseries after all)
- All time parsing that previously resulted in a `pandas.Timestamp` now use `pendulum.Datetime` instead.

### Fixed

- Better defaults in `humioapi.QueryJob`

### Removed

- Renamed `humiocore` to `humioapi`.


## [0.4.0] - 2019-11-29

### Added

- API functions to create and poll queryjobs living in Humio. This API allows real live searches.
- A helper class QueryJob to manage searches using queryjobs

### Fixed

- Internal handling of HTTP error status codes previously lost exception details,
  these details should now be available again on the exception object.

### Removed

- Removed the deprecated async_search API



## [0.3.0] - 2019-09-26

### Changed

- The repositories API function will now return views as well
- Removed filtering logic from repositories API
- Signature of streaming_search() changed.
  - Live option has been removed since it should be a separate API. Humio only allows their internal "relative time" strings for live searches.
  - Start and End are now optional


## [0.2.0] - 2019-09-24

### Added

- A Changelog! :)

### Changed

- Bumped project dependencies

### Deprecated

- The async_search API. Use the streaming_search API instead since it yields a generator to stream results and is generally more "stable".

### Removed

- Various noisy logging output
