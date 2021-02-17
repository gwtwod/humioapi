import os
from pathlib import PurePath, Path
from dotenv import load_dotenv


def loadenv(env=None, prefix=None):
    """
    Load all environment variables from the specified `env` file into `os.environ`
    and return a dict of the variables matching the provided `prefix`.

    The key names will be lower case with the prefix stripped for ease of use as kwargs.
    The env file can have comments, and allows variables prefixed with `soruce`, which
    will be ignored but allow easily sourcing the file in your shell.

    Bare variables like `$HOME` are not expanded, but `${HOME}` will be.

    Parameters
    ----------
    env: string or list of strings
        Path to env file(s) to load.
    prefix: string or list of strings
        Prefix of env variables to load from the env files.

    Returns
    -------
        A dict with all relevant env variables loaded.
    """

    config = {}

    if env is None or isinstance(env, (str, PurePath)):
        env = [env]

    if prefix is None or isinstance(prefix, str):
        prefix = [prefix]

    # source all env variables
    for env_file in env:
        expanded_path = Path(env_file).expanduser()
        load_dotenv(dotenv_path=expanded_path)

    # find all relevant sourced env variables
    for key in os.environ.keys():
        for p in prefix:
            if key.startswith(p):
                normalized_key = removeprefix(key, p).lower()
                config[normalized_key] = os.getenv(key)

    return config


def humio_loadenv(env="~/.config/humio/.env", prefix="HUMIO_"):
    """Call loadenv with the default config file and default env prefix"""
    return loadenv(env=env, prefix=prefix)


def removeprefix(s, prefix):
    if s.startswith(prefix):
        return s[len(prefix) :]
    return s
