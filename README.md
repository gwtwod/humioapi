# Humio API (unofficial lib)

This is an unofficial library for interacting with [Humio](https://www.humio.com/)'s API. If you're looking for the official Python Humio library it can be found [here: humiolib](https://github.com/humio/python-humio). This library mostly exists because the official library was incredibly basic back in 2019 when I needed this.

## Main features

* Asyncronous and syncronous streaming queries supported by `httpx`
* Queryjobs which can be polled once, or until completed.
* Chainable relative time modifiers (similar to Splunk e.g. `-1d@h-30m`)
* List repository details (*NOTE*: normal Humio users cannot see repos without read permission)
* Easy env-variable based configuration
* Ingest data to Humio, although you probably want to use Filebeat for anything other than one-off things to your sandbox.
* (*Work in progress*) Create and update parsers.
* (*Work in progress*) An updateable timeseries, which can follow a moving timewindow using relative modifiers, optionally querying only the changed timewindow since previous update.

## Usage

For convenience your Humio URL and token should be set in the environment variables `HUMIO_BASE_URL` and `HUMIO_TOKEN`. These can be set in `~/.config/humio/.env` and loaded by `humioapi.loadenv()`.

## Query repositories

Create an instance of HumioAPI to get started

```python
import humioapi
humioapi.setup_excellent_logging('INFO')
api = humioapi.HumioAPI(**humioapi.loadenv())
repositories = api.repositories()
```

## Iterate over syncronouys streaming searches sequentially

```python
import humioapi
humioapi.setup_excellent_logging('INFO')
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
humioapi.setup_excellent_logging('INFO')
api = humioapi.HumioAPI(**humioapi.loadenv())
loop = asyncio.new_event_loop()

try:
    asyncio.set_event_loop(loop)
    tasks = api.async_streaming_tasks(
        loop,
        query="log_type=trace user=someone",
        repos=['frontend', 'backend', 'integration'],
        start="-1week@day",
        stop="now",
        concurrent_limit=10,
    )

    for event in humioapi.consume_async(loop, tasks):
        print(event)
finally:
    try:
        loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        asyncio.set_event_loop(None)
        loop.close()
```

## Jupyter Notebook

```python
pew new --python=python36 humioapi
# run the following commands inside the virtualenv
pip install git+https://github.com/gwtwod/humio-api.git
pip install ipykernel seaborn matplotlib
python -m ipykernel install --user --name 'python36-humioapi' --display-name 'Python 3.6 (venv humioapi)'
```

Start the notebook by running `jupyter-notebook` and choose the newly created kernel when creating a new notebook.

Run this code to get started:

```python
import humioapi
humioapi.setup_excellent_logging('INFO')
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

results = api.streaming_search(query='log_type=stats | timechart(series=metric)', repos=['frontend'], start=start, end=end)
df = pd.DataFrame(results)
df['_count'] = df['_count'].astype(float)

df['_bucket'] = pd.to_datetime(df['_bucket'], unit='ms', origin='unix', utc=True)
df.set_index('_bucket', inplace=True)

df.index = df.index.tz_convert('Europe/Oslo')
df = df.pivot(columns='metric', values='_count')

sns.lineplot(data=df)
```
