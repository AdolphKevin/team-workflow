"""Project knowledge and team workflow runtime. Python 3.10+, standard library only."""

VERSION = '0.9.0-dev'
FORMAT = 'channelwill/team-workflow'
DATA_VERSION = 1
KB = '.tw'


class Invalid(Exception):
    """A user-facing error: the command cannot continue as requested."""


def require(condition, message):
    if not condition:
        raise Invalid(message)
