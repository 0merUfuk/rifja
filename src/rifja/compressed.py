"""Bounded streaming lines from Python 3.14's standard-library Zstandard decoder.

API evidence: CPython Lib/compression/zstd/__init__.py and the 3.14 docs:
https://docs.python.org/3.14/library/compression.zstd.html#compression.zstd.ZstdDecompressor
ZstdDecompressor handles one frame; eof/unused_data delimit concatenated frames,
needs_input controls draining, and max_length bounds each returned output chunk.
DecompressionParameter.window_log_max limits the decoder's history window.

The caller must open an authorized regular file; this reader neither opens paths
nor closes its input. It emits bytes, not decoded text, and creates no plaintext
files. Complete lines emitted before a later frame error remain provisional:
the caller must preserve the accompanying partial-coverage diagnostic.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import BinaryIO

INPUT_CHUNK_BYTES = 64 * 1024
OUTPUT_CHUNK_BYTES = 64 * 1024
MAX_COMPRESSED_BYTES = 256 * 1024 * 1024
MAX_WINDOW_LOG = 23  # 8 MiB history window, plus bounded decoder working storage.
MAX_FRAMES = 10_000
MAX_DECODER_STEPS = 1_000_000
MAX_ELAPSED_SECONDS = 30.0


def iter_zstd_lines(
    stream: BinaryIO,
    max_record_bytes: int = 1_048_576,
    max_total_bytes: int = 268_435_456,
) -> Iterator[tuple[int, bytes | None, str | None]]:
    """Yield one-based logical line numbers, raw complete lines or diagnostic codes.

    Limits include newline bytes. Oversized complete lines are discarded and the
    following line is still processed. Input/output/step/frame/time limits stop
    the source with one diagnostic. A valid final frame with an unterminated line
    reports incomplete_tail; an unfinished frame reports zstd_truncated_stream.
    Invalid frames, checksum errors, required dictionaries and oversized decoder
    windows report zstd_decompression_error without exposing decoder messages.

    Elapsed time is checked between bounded reads/decoder calls and includes
    consumer time between yields. This is a cooperative deadline, not a hard OS
    interruption guarantee for a stalled filesystem or a single decoder call.
    """
    if (
        not isinstance(max_record_bytes, int)
        or isinstance(max_record_bytes, bool)
        or not isinstance(max_total_bytes, int)
        or isinstance(max_total_bytes, bool)
        or max_record_bytes < 1
        or max_total_bytes < 1
    ):
        raise ValueError("zstd_limits_must_be_positive_integers")
    try:
        from compression import zstd
    except ImportError:
        yield 1, None, "zstd_unavailable"
        return

    started = time.monotonic()
    line_number = 1
    buffered = bytearray()
    oversized = False
    input_bytes = 0
    output_bytes = 0
    steps = 0
    frames = 0
    decoder = None
    pending = b""
    try:
        while True:
            if time.monotonic() - started >= MAX_ELAPSED_SECONDS:
                yield line_number, None, "zstd_time_limit"
                return
            if not pending and (decoder is None or decoder.needs_input):
                read_size = min(INPUT_CHUNK_BYTES, MAX_COMPRESSED_BYTES - input_bytes + 1)
                pending = stream.read(read_size)
                if not isinstance(pending, bytes) or len(pending) > read_size:
                    yield line_number, None, "zstd_invalid_input_stream"
                    return
                input_bytes += len(pending)
                if input_bytes > MAX_COMPRESSED_BYTES:
                    yield line_number, None, "zstd_input_limit"
                    return
                if not pending:
                    if decoder is not None or frames == 0:
                        yield line_number, None, "zstd_truncated_stream"
                    elif oversized:
                        yield line_number, None, "oversized_incomplete_tail"
                    elif buffered:
                        yield line_number, None, "incomplete_tail"
                    return
            if decoder is None:
                if frames >= MAX_FRAMES:
                    yield line_number, None, "zstd_frame_limit"
                    return
                decoder = zstd.ZstdDecompressor(
                    options={zstd.DecompressionParameter.window_log_max: MAX_WINDOW_LOG}
                )
                frames += 1
            if steps >= MAX_DECODER_STEPS:
                yield line_number, None, "zstd_step_limit"
                return
            steps += 1
            output = decoder.decompress(
                pending, max_length=min(OUTPUT_CHUNK_BYTES, max_total_bytes - output_bytes + 1)
            )
            pending = b""
            over_total = output_bytes + len(output) > max_total_bytes
            if over_total:
                output = output[: max_total_bytes - output_bytes]
            output_bytes += len(output)
            cursor = 0
            while cursor < len(output):
                newline = output.find(b"\n", cursor)
                end = newline + 1 if newline >= 0 else len(output)
                if not oversized:
                    if len(buffered) + end - cursor > max_record_bytes:
                        buffered.clear()
                        oversized = True
                    else:
                        buffered.extend(output[cursor:end])
                cursor = end
                if newline >= 0:
                    if oversized:
                        yield line_number, None, "record_size_limit"
                    else:
                        yield line_number, bytes(buffered), None
                    line_number += 1
                    buffered.clear()
                    oversized = False
            if over_total:
                yield line_number, None, "zstd_output_limit"
                return
            if decoder.eof:
                pending = decoder.unused_data
                decoder = None
    except zstd.ZstdError:
        yield line_number, None, "zstd_decompression_error"
    except OSError:
        yield line_number, None, "zstd_read_error"
