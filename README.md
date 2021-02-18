# Humio API (unofficial lib)

> 💡 This project requires `Python>=3.6.1`

> 💡 This is not the official Humio library. It can be found [here: humiolib](https://github.com/humio/python-humio).

This is an unofficial library for interacting with [Humio](https://www.humio.com/)'s API. This library mostly exists now because the official library was too basic back in 2019 when I first needed this. Currently this library is just a wrapper around `humiolib` to implement some convenient and opinionated helpers.

## Installation

```bash
pip install humioapi
```

## Main features/extensions

* CLI companion tool `hc` available at [humiocli](https://github.com/gwtwod/humiocli).
* Monkeypatched QueryJobs with a `poll_safe` method that can return or raise warnings.
* Relative time modifiers similar to Splunk (`-7d@d` to start at midnight 7 days ago). Can also be chained (`-1d@h-30m`). [Source](https://github.com/zartstrom/snaptime).
* List repository details (*NOTE*: normal Humio users cannot see repos without read permission).
* Easy env-variable based configuration.
* Create and update parsers.

## Usage

For convenience your Humio URL and tokens should be set in the environment variables `HUMIO_BASE_URL` and `HUMIO_TOKEN`.
These can be set in `~/.config/humio/.env` and loaded through `humioapi.humio_loadenv()`, which loads all `HUMIO_`-prefixed
variables found in the env-file.

## Query repositories

Create an instance of HumioAPI to get started

```python
import humioapi
import logging
humioapi.initialize_logging(level=logging.INFO, fmt="human")

api = humioapi.HumioAPI(**humioapi.humio_loadenv())
repositories = api.repositories()
```

## Iterate over syncronous streaming searches sequentially

```python
import humioapi
import logging
humioapi.initialize_logging(level=logging.INFO, fmt="human")

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
import logging
humioapi.initialize_logging(level=logging.INFO, fmt="human")

api = humioapi.HumioAPI(**humioapi.humio_loadenv())
qj = api.create_queryjob(query="", repo="sandbox", start="-7d@d")

result = qj.poll_safe(raise_warnings=False)
if result.warnings:
    print("Oh no!", result.warnings)
print(result.metadata)
```

## Jupyter Notebook

```python
pew new --python=python36 humioapi
# run the following commands inside the virtualenv
pip install git+https://github.com/gwtwod/humioapi.git
pip install ipykernel seaborn matplotlib
python -m ipykernel install --user --name 'python36-humioapi' --display-name 'Python 3.6 (venv humioapi)'
```

Start the notebook by running `jupyter-notebook` and choose the newly created kernel when creating a new notebook.

Run this code to get started:

```python
import humioapi
import logging
humioapi.initialize_logging(level=logging.INFO, fmt="human")

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

## SSL and proxies

All HTTP traffic is done through `humiolib` which currently uses `requests` internally. You can probably use custom certificates with the env variable `REQUESTS_CA_BUNDLE`, or pass extra argument as `kwargs` to the various API functions.
