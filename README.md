# Humio API (unofficial lib)

> This project requires `Python>=3.6.1`

This is an unofficial library for interacting with [Humio](https://www.humio.com/)'s API. If you're looking for the official Python Humio library it can be found [here: humiolib](https://github.com/humio/python-humio). This library mostly exists because the official library was very basic back in 2019 when I first needed this.

## Installation

    pip install humioapi

## Main features

* Untested and poorly documented code
* CLI companion tool available at [humiocli](https://github.com/gwtwod/humiocli).
* Asyncronous and syncronous streaming queries supported by `httpx`.
* QueryJobs which can be polled once, or until completed.
* Chainable relative time modifiers (similar to Splunk e.g. `-1d@h-30m`).
* List repository details (*NOTE*: normal Humio users cannot see repos without read permission).
* Easy env-variable based configuration.
* Ingest data to Humio, although you probably want to use Filebeat for anything other than one-off things to your sandbox.
* Create and update parsers.

## Usage

For convenience your Humio URL and token should be set in the environment variables `HUMIO_BASE_URL` and `HUMIO_TOKEN`. These can be set in `~/.config/humio/.env` and loaded by `humioapi.loadenv()`.

## Query repositories

Create an instance of HumioAPI to get started

```python
import humioapi
import logging
humioapi.initialize_logging(level=logging.INFO, fmt="human")

api = humioapi.HumioAPI(**humioapi.loadenv())
repositories = api.repositories()
```

## Iterate over syncronous streaming searches sequentially

```python
import humioapi
import logging
humioapi.initialize_logging(level=logging.INFO, fmt="human")

api = humioapi.HumioAPI(**humioapi.loadenv())
stream = api.streaming_search(
    query="log_type=trace user=someone",
    repos=['frontend', 'backend', 'integration'],
    start="-1week@day",
    stop="now"
)
for event in stream:
    print(event)
```

## Itreate over asyncronous streaming searches in parallell, from a syncronous context

```python
import asyncio
import humioapi
import logging

humioapi.initialize_logging(level=logging.INFO, fmt="human")
api = humioapi.HumioAPI(**humioapi.loadenv())

queries = [{
    "query": "chad index.html | select(@timestamp)",
    "repo": "sandbox",
    "start": "-7d@d",
    "stop": "-4d@d",
    }, {
    "query": "chad index.html | select(@rawstring)",
    "repo": "sandbox",
    "start": "-4d@d",
    "stop": "now",
}]

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

try:
    tasks = api.async_streaming_search(queries, loop=loop, concurrent_limit=10)
    for item in humioapi.consume_async(tasks, loop):
        print(item)
finally:
    loop.close()
    asyncio.set_event_loop(None)
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

api = humioapi.HumioAPI(**humioapi.loadenv())
results = api.streaming_search(query='log_type=trace user=someone', repos=['frontend', 'backend'], start="@d", stop="now")
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

results = api.streaming_search(query='log_type=stats | timechart(series=metric)', repos=['frontend'], start=start, stop=stop)
df = pd.DataFrame(results)
df['_count'] = df['_count'].astype(float)

df['_bucket'] = pd.to_datetime(df['_bucket'], unit='ms', origin='unix', utc=True)
df.set_index('_bucket', inplace=True)

df.index = df.index.tz_convert('Europe/Oslo')
df = df.pivot(columns='metric', values='_count')

sns.lineplot(data=df)
```

## SSL and proxies

All HTTP traffic is done through `httpx`, which allows customizing SSL and proxy behaviour through environment variables. See [httpx docs](https://www.python-httpx.org/environment_variables/) for details.
