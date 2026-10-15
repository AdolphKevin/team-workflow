#!/usr/bin/env python3
"""Offline contract peer; responses and files are supplied through the environment."""
import base64
import json
import os
from pathlib import Path
import sys
import time


def main():
    operation, *arguments = sys.argv[1:]
    invocation = 0
    if os.environ.get('TW_PLATFORM_LOG'):
        log = Path(os.environ['TW_PLATFORM_LOG'])
        if log.exists():
            invocation = sum(json.loads(line)['operation'] == operation for line in log.read_text().splitlines())
        with log.open('a') as stream:
            stream.write(json.dumps({'operation': operation, 'arguments': arguments, 'cwd': os.getcwd()}) + '\n')
    time.sleep(float(os.environ.get('TW_PLATFORM_DELAY', '0')))
    if os.environ.get('TW_PLATFORM_EXIT'):
        print(os.environ.get('TW_PLATFORM_STDERR', ''), file=sys.stderr)
        return int(os.environ['TW_PLATFORM_EXIT'])
    if operation == 'ci-result' and os.environ.get('TW_PLATFORM_ARCHIVE'):
        output = Path(arguments[arguments.index('--output') + 1])
        (output / 'result.zip').write_bytes(base64.b64decode(os.environ['TW_PLATFORM_ARCHIVE']))
    response = os.environ.get('TW_PLATFORM_STDOUT')
    if response is None:
        values = json.loads(os.environ['TW_PLATFORM_RESPONSES'])
        sequence = json.loads(os.environ.get('TW_PLATFORM_SEQUENCE', '{}')).get(operation)
        response = json.dumps(sequence[min(invocation, len(sequence) - 1)] if sequence else values[operation])
    print(response)
    return 0


if __name__ == '__main__':
    sys.exit(main())
