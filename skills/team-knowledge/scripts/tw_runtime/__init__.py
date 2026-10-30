"""Project knowledge runtime. Python 3.10+, standard library only."""

VERSION = '1.0.1'
FORMAT = 'channelwill/team-workflow'
DATA_VERSION = 1
KB = '.tw'


class Invalid(Exception):
    """A user-facing error: the command cannot continue as requested."""


def require(condition, message):
    if not condition:
        raise Invalid(message)
