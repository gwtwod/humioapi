import os
from pathlib import Path

from dotenv import load_dotenv


def loadenv(env=None, prefix="HUMIO_"):
    """
    Load all environment variables from the specified `env` file into `os.environ`
    and return a dict of the variables matching the provided `prefix`.

    The key names will be lower case with the prefix stripped for ease of use as kwargs.

    The env file can have comments, and allows variables prefixed with `soruce`, which
    will be ignored but allow easily sourcing the file in your shell.

    Bare variables ($HOME) are not expanded, but ${HOME} will be expanded.

    Parameters
    ----------

    env: string or list of strings
        Path to env file(s) to load. Default `~/.config/humio/.env`.
    prefix: string or list of strings
        Prefix of env variables to load from the env files. Default `HUMIO_`.

    Returns:
        A dict with all relevant env variables loaded.
    """

    if prefix is None or isinstance(prefix, str):
        prefix = [prefix]

    if env is None or isinstance(env, str):
        env = [env]

    config = {}

    # source all env variables
    for e in env:
        for p in prefix:
            load(env=e, prefix=p)

    # find all relevant loaded env variables
    for key in os.environ.keys():
        for p in prefix:
            if key.startswith(p):
                normalized_key = removeprefix(key, p).lower()
                config[normalized_key] = os.getenv(key)

    return config


def load(env=None, prefix=None):
    """Loads all variables from an env file"""

    if env is None:
        env = Path.home() / ".config/humio/.env"
    load_dotenv(dotenv_path=env)


def removeprefix(s, prefix):
    if s.startswith(prefix):
        return s[len(prefix):]
    return s

