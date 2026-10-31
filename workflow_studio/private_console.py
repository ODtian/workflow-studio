"""Capture workflow thread output while marimo replaces the global streams."""
from contextlib import contextmanager, ExitStack, redirect_stderr, redirect_stdout
import io
import sys
import threading


_output = threading.local()


def capture_marimo_streams():
    from marimo._messaging.streams import ThreadSafeStderr, ThreadSafeStdout

    for stream_type in (ThreadSafeStdout, ThreadSafeStderr):
        original = stream_type._write_with_mimetype
        if getattr(original, '_private_console', False):
            continue

        def write(stream, data, mimetype, original=original):
            target = getattr(_output, 'target', None)
            if target is not None:
                return target.write(data)
            return original(stream, data, mimetype)

        write._private_console = True
        stream_type._write_with_mimetype = write


@contextmanager
def capture_output():
    from marimo._messaging.streams import ThreadSafeStderr, ThreadSafeStdout

    capture_marimo_streams()
    previous = getattr(_output, 'target', None)
    output = io.StringIO()
    _output.target = output
    try:
        with ExitStack() as stack:
            if not isinstance(sys.stdout, ThreadSafeStdout):
                stack.enter_context(redirect_stdout(output))
            if not isinstance(sys.stderr, ThreadSafeStderr):
                stack.enter_context(redirect_stderr(output))
            yield output
    finally:
        _output.target = previous
