import os
from pathlib import Path

from dotenv import load_dotenv


def loadenv(env=None, prefix="HUMIO_"):
    """
    Load all environment variables from the specified `env` file into `os.environ`
    and return a dict of the variables matching the provided `prefix`. The key names will be
    lower case with the HUMIO_ prefix stripped for ease of use as kwargs.
    """

    if env is None:
        env = Path.home() / ".config/humio/.env"
    load_dotenv(dotenv_path=env)

    return {key[6:].lower(): os.getenv(key) for key in os.environ.keys() if key.startswith(prefix)}
