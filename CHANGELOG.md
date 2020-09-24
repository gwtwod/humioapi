# Changelog

## [Unreleased]

### Added

### Changed

### Fixed

### Deprecated

### Removed


## [0.6.1] - 2020-09-24

### Fixed

- Added color style to TRACE logging level in console renderer logging helper, since httpx defines that level (5).

# Changelog

## [0.6.0] - 2020-09-23

### Added

- Optional timeout parameters to search APIs. By default 30 seconds. Can be an integer og a httpx.Timeout.

### Changed

- Refactored logging helpers with a new function `humioapi.initialize_logging` providing sane structlog JSON (default) or Human readable logs depending on the chosen format.
- QueryJob now takes a client instance instead of a token and base_url
- Bumped dependency versions

### Fixed

- Use context manager with all `httpx` requests so connections are closed properly.

### Deprecated

### Removed

- `humioapi.setup_excellent_logging` removed in favor of `humioapi.initialize_logging`


## [0.5.1] - 2020-08-29

### Added

### Changed

### Fixed

- Renamed `end` to `start` in a few forgotten places (url util functions)
- Strip trailing slash in base urls instead of stupidy failing

### Deprecated

### Removed



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

### Deprecated

### Removed

- Renamed `humiocore` to `humioapi`.



## [0.4.0] - 2019-11-29

### Added

- API functions to create and poll queryjobs living in Humio. This API allows real live searches.
- A helper class QueryJob to manage searches using queryjobs

### Changed

### Fixed

- Internal handling of HTTP error status codes previously lost exception details,
  these details should now be available again on the exception object.

### Deprecated

### Removed

- Removed the deprecated async_search API



## [0.3.0] - 2019-09-26

### Added

### Changed

- The repositories API function will now return views as well
- Removed filtering logic from repositories API
- Signature of streaming_search() changed.
  - Live option has been removed since it should be a separate API. Humio only allows their internal "relative time" strings for live searches.
  - Start and End are now optional

### Deprecated

### Removed


## [0.2.0] - 2019-09-24

### Added

- A Changelog! :)

### Changed

- Bumped project dependencies

### Deprecated

- The async_search API. Use the streaming_search API instead since it yields a generator to stream results and is generally more "stable".

### Removed

- Various noisy logging output
