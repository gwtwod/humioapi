# Humio API (unofficial lib)

> 💡 This project requires `Python>=3.8`

> 💡 This is not the official Humio library. It can be found [here: humiolib](https://github.com/humio/python-humio).

This is an unofficial library for interacting with [Humio](https://www.humio.com/)'s API. This library mostly exists now because the official library was too basic back in 2019 when I first needed this. Currently this library is just a wrapper around `humiolib` to implement some convenient and opinionated helpers.

## Installation

```bash
pip install humioapi
```

## Main features/extensions

* CLI companion tool `hc` available at [humiocli](https://github.com/gwtwod/humiocli).
* Monkeypatched QueryJobs with a different approach.
    * The `poll` method is now a generator yielding the current result until the query completes, with optional progress information and warnings.
    * The `poll_until_done` method now simply returns the final result of the `poll` method in an efficient manner, which solves the problem the original poll method has with getting stuck forever in some cases.
* Relative time modifiers similar to Splunk (`-7d@d` to start at midnight 7 days ago). Can also be chained (`-1d@h-30m`). [Source](https://github.com/zartstrom/snaptime).
* List repository details (*NOTE*: normal Humio users cannot see repos without read permission).
* Easy env-variable based configuration.
* Create and update parsers.

## Usage

For convenience your Humio URL and tokens should be set in the environment variables `HUMIO_BASE_URL` and `HUMIO_TOKEN`.
These can be set in `~/.config/humio/.env` and loaded through `humioapi.humio_loadenv()`, which loads all `HUMIO_`-prefixed
variables found in the env-file.

## Query available repositories

Create an instance of HumioAPI to get started

```python
import humioapi

api = humioapi.HumioAPI(**humioapi.humio_loadenv())
repositories = api.repositories()
```

## Iterate over syncronous streaming searches sequentially

```python
import humioapi

api = humioapi.HumioAPI(**humioapi.humio_loadenv())
stream = api.streaming_search(
    query="",
    repo='sandbox',
    start="-1week@day",
    stop="now"
)
for event in stream:
    print(event)
```

## Create a pollable QueryJob with results, metadata and warnings (raised by default)

```python
import humioapi

api = humioapi.HumioAPI(**humioapi.humio_loadenv())
qj = api.create_queryjob(query="", repo="sandbox", start="-7d@d")

# Poll the QueryJob and get its final results
result = qj.poll_until_done(warn=False)
if result.warnings:
    print("Oh no, a problem has occured!", result.warnings)
print(result.metadata)

# Or manually iterate the current results until the QueryJob has completed
for current_result in qj.poll(warn=False):
    pass
if current_result.warnings:
    print("Oh no, a problem has occured!", current_result.warnings)
print(current_result.metadata)
```

## Jupyter Notebook

```python
pew new --python=python38 humioapi
# run the following commands inside the virtualenv
pip install git+https://github.com/gwtwod/humioapi.git
pip install ipykernel seaborn matplotlib
python -m ipykernel install --user --name 'python38-humioapi' --display-name 'Python 3.8 (venv humioapi)'
```

Start the notebook by running `jupyter-notebook` and choose the newly created kernel when creating a new notebook.

Run this code to get started:

```python
import humioapi

api = humioapi.HumioAPI(**humioapi.humio_loadenv())
results = api.streaming_search(query="", repo="sandbox", start="@d", stop="now")
for i in results:
    print(i)
```

To get a list of all readable repositories with names starting with 'frontend':

```python
repos = sorted([k for k,v in api.repositories().items() if v['read_permission'] and k.startswith('frontend')])
```

Making a timechart (lineplot):

```python
%matplotlib inline
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

sns.set(color_codes=True)
sns.set_style('darkgrid')

results = api.streaming_search(query=" | timechart()", repos=["sandbox"], start=start, stop=stop)
df = pd.DataFrame(results)
df['_count'] = df['_count'].astype(float)

df['_bucket'] = pd.to_datetime(df['_bucket'], unit='ms', origin='unix', utc=True)
df.set_index('_bucket', inplace=True)

df.index = df.index.tz_convert('Europe/Oslo')
df = df.pivot(columns='metric', values='_count')

sns.lineplot(data=df)
```

## Logging

This library uses the excellent structlog library. If you're want pretty formatted logs but are too lazy to configure it yourself, you can use the included helper to configure it.

This helper also installs an exception hook to log all unhandled exceptions through structlog.

```python
import logging

humioapi.initialize_logging(level=logging.INFO, fmt="human")  # or fmt="json"
```

## SSL and proxies

All HTTP traffic is done through `humiolib` which currently uses `requests` internally. You can probably use custom certificates with the env variable `REQUESTS_CA_BUNDLE`, or pass extra argument as `kwargs` to the various API functions.
