# Changelog

## [Unreleased]

### Added

### Changed

### Fixed

- Renamed `end` to `start` in a few forgotten places (url util functions)

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
