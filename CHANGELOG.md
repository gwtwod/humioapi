# Changelog

## [Unreleased]

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
