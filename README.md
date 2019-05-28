# Humiocore

An unofficial library for interacting with the Humio API

For convenience your humio url and token should be set in the environment variables `HUMIO_BASE_URL` and `HUMIO_TOKEN`. These can be set in `~/.config/humio/.env` and loaded by `humiocore.loadenv()`.

Create an instance of HumioAPI to get started

    import humiocore
    humiocore.setup_excellent_logging('INFO')
    client = humiocore.HumioAPI(**humiocore.loadenv())
    repositories = client.repositories()

## Jupyter Notebook

    pew new --python=python36 humiocore
    # run the following commands inside the virtualenv
    pip install git+https://github.com/gwtwod/py3humiocore.git
    pip install ipykernel seaborn matplotlib
    python -m ipykernel install --user --name 'python36-humiocore' --display-name 'Python 3.6 (venv humiocore)'

> Jupyter doesn't play nice with asyncio, so use streaming_search() instead of async_search()

Exit the virtual environment and run `pipsi install notebook` if you
haven't already. Start the notebook by running `jupyter-notebook` and choose the
newly created kernel when creating a new notebook.

Run this code to get started:

    import humiocore
    humiocore.setup_excellent_logging('INFO')
    client = humiocore.HumioAPI(**humiocore.loadenv())

    start = humiocore.utils.parse_ts('@d')
    end = humiocore.utils.parse_ts('@m')
    results = client.streaming_search(query='log_type=trace user=someone', repos=['frontend', 'backend'], start=start, end=end)

To get a list of all readable repositories with names starting with 'frontend':

    repos = sorted([k for k,v in client.repositories().items() if v['read_permission'] and k.startswith('frontend')])

Making a timechart (lineplot):

    %matplotlib inline
    import matplotlib.pyplot as plt
    import seaborn as sns
    import pandas as pd

    sns.set(color_codes=True)
    sns.set_style('darkgrid')

    results = client.streaming_search(query='log_type=stats | timechart(series=metric)', repos=['frontend'], start=start, end=end)
    df = pd.DataFrame(results)
    df['_count'] = df['_count'].astype(float)

    df['_bucket'] = pd.to_datetime(df['_bucket'], unit='ms', origin='unix', utc=True)
    df.set_index('_bucket', inplace=True)

    df.index = df.index.tz_convert('Europe/Oslo')
    df = df.pivot(columns='metric', values='_count')

    sns.lineplot(data=df)
