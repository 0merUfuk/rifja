"""Synthetic genuine Zstandard frames; no external binary or provider data.

Fixtures use Python 3.14's documented compression.zstd.compress/ZstdCompressor.
API source: CPython Lib/compression/zstd/__init__.py and _zstd extension docstrings.
https://docs.python.org/3.14/library/compression.zstd.html
"""

from __future__ import annotations

import hashlib
import io
import json
import unittest
from compression import zstd
from unittest.mock import patch

from session_visualizer import compressed


class ShortReads(io.BytesIO):
    def __init__(self, value: bytes, size: int = 1):
        super().__init__(value)
        self.size = size
        self.requests: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.requests.append(size)
        if size < 0:
            raise AssertionError("The decoder must never request an unbounded read")
        return super().read(min(size, self.size))


class ZstdLineTests(unittest.TestCase):
    def collect(self, encoded: bytes, **limits: int) -> list[tuple[int, bytes | None, str | None]]:
        return list(compressed.iter_zstd_lines(io.BytesIO(encoded), **limits))

    def test_unicode_and_exact_bytes_preserved_without_mutating_or_closing_input(self) -> None:
        values = [
            {"type": "session_meta", "payload": {"id": "synthetic", "cwd": "/synthetic"}},
            {"text": "Görev: Unicode sınırlarını doğrula. 日本語 🙂"},
        ]
        lines = [(json.dumps(value, ensure_ascii=False) + "\n").encode() for value in values]
        encoded = zstd.compress(b"".join(lines))
        source = io.BytesIO(encoded)
        before = hashlib.sha256(source.getvalue()).hexdigest()
        self.assertEqual(
            list(compressed.iter_zstd_lines(source)),
            [(index, line, None) for index, line in enumerate(lines, 1)],
        )
        self.assertFalse(source.closed)
        self.assertEqual(hashlib.sha256(source.getvalue()).hexdigest(), before)

    def test_multiframe_stream_and_line_crossing_frame_boundary(self) -> None:
        encoded = zstd.compress(b"one\ntw") + zstd.compress(b"o\n") + zstd.compress(b"three\n")
        self.assertEqual(
            self.collect(encoded), [(1, b"one\n", None), (2, b"two\n", None), (3, b"three\n", None)]
        )

    def test_small_reads_frame_boundaries_and_unicode_bytes(self) -> None:
        raw = "İlk 🙂\nikinci 日本語\n".encode()
        encoded = zstd.compress(raw[:8]) + zstd.compress(raw[8:])
        source = ShortReads(encoded)
        self.assertEqual(
            list(compressed.iter_zstd_lines(source)),
            [(1, "İlk 🙂\n".encode(), None), (2, "ikinci 日本語\n".encode(), None)],
        )
        self.assertTrue(source.requests)
        self.assertLessEqual(max(source.requests), compressed.INPUT_CHUNK_BYTES)

    def test_complete_empty_frame_and_empty_lines(self) -> None:
        self.assertEqual(self.collect(zstd.compress(b"")), [])
        self.assertEqual(
            self.collect(zstd.compress(b"\n\r\n")), [(1, b"\n", None), (2, b"\r\n", None)]
        )

    def test_empty_source_is_not_a_valid_frame(self) -> None:
        self.assertEqual(self.collect(b""), [(1, None, "zstd_truncated_stream")])

    def test_truncated_frame_is_reported_after_prior_complete_frames(self) -> None:
        encoded = zstd.compress(b"one\n") + zstd.compress(b"two\n")[:-2]
        result = self.collect(encoded)
        self.assertEqual(result[0], (1, b"one\n", None))
        self.assertEqual(result[-1][1:], (None, "zstd_truncated_stream"))

    def test_partial_header_is_reported(self) -> None:
        for length in (1, 2, 3, 4, 5):
            with self.subTest(length=length):
                self.assertEqual(
                    self.collect(zstd.compress(b"one\n")[:length])[-1][2], "zstd_truncated_stream"
                )

    def test_corrupt_stream_and_trailing_garbage_are_reported(self) -> None:
        for encoded in (b"not zstandard", zstd.compress(b"one\n") + b"bad trailing bytes"):
            with self.subTest(encoded=encoded[:4]):
                self.assertEqual(self.collect(encoded)[-1][1:], (None, "zstd_decompression_error"))

    def test_trailing_partial_frame_is_not_ignored(self) -> None:
        encoded = zstd.compress(b"one\n") + zstd.compress(b"two\n")[:3]
        self.assertEqual(
            self.collect(encoded), [(1, b"one\n", None), (2, None, "zstd_truncated_stream")]
        )

    def test_checksum_corruption_is_reported(self) -> None:
        encoded = bytearray(
            zstd.compress(b"one\n", options={zstd.CompressionParameter.checksum_flag: 1})
        )
        encoded[-1] ^= 0x40
        self.assertEqual(self.collect(bytes(encoded))[-1][2], "zstd_decompression_error")

    def test_oversized_line_is_skipped_and_next_record_survives(self) -> None:
        with patch.object(compressed, "OUTPUT_CHUNK_BYTES", 3):
            result = self.collect(zstd.compress(b"a" * 100 + b"\ngood\n"), max_record_bytes=5)
        self.assertEqual(result, [(1, None, "record_size_limit"), (2, b"good\n", None)])

    def test_record_limit_includes_newline(self) -> None:
        self.assertEqual(
            self.collect(zstd.compress(b"abcd\nabcde\n"), max_record_bytes=5),
            [(1, b"abcd\n", None), (2, None, "record_size_limit")],
        )

    def test_incomplete_tail_and_oversized_incomplete_tail(self) -> None:
        self.assertEqual(
            self.collect(zstd.compress(b"good\ntail")),
            [(1, b"good\n", None), (2, None, "incomplete_tail")],
        )
        self.assertEqual(
            self.collect(zstd.compress(b"too large"), max_record_bytes=3),
            [(1, None, "oversized_incomplete_tail")],
        )

    def test_total_limit_preserves_only_complete_permitted_lines(self) -> None:
        self.assertEqual(
            self.collect(zstd.compress(b"one\ntwo\n"), max_total_bytes=6),
            [(1, b"one\n", None), (2, None, "zstd_output_limit")],
        )
        self.assertEqual(
            self.collect(zstd.compress(b"one\ntwo\n"), max_total_bytes=8),
            [(1, b"one\n", None), (2, b"two\n", None)],
        )

    def test_high_expansion_output_is_bounded(self) -> None:
        encoded = zstd.compress(b"x" * (4 * 1024 * 1024) + b"\n")
        result = self.collect(encoded, max_total_bytes=1024)
        self.assertEqual(result, [(1, None, "zstd_output_limit")])

    def test_decoder_window_limit_is_effective(self) -> None:
        compressor = zstd.ZstdCompressor(
            options={
                zstd.CompressionParameter.window_log: 20,
                zstd.CompressionParameter.content_size_flag: 0,
            }
        )
        encoded = compressor.compress(b"x" * 4096 + b"\n") + compressor.flush()
        with patch.object(compressed, "MAX_WINDOW_LOG", 10):
            result = self.collect(encoded)
        self.assertEqual(result, [(1, None, "zstd_decompression_error")])

    def test_input_limit_includes_empty_frames(self) -> None:
        encoded = zstd.compress(b"") * 100
        with patch.object(compressed, "MAX_COMPRESSED_BYTES", 20):
            result = self.collect(encoded)
        self.assertEqual(result[-1][2], "zstd_input_limit")

    def test_empty_frame_count_is_bounded(self) -> None:
        with patch.object(compressed, "MAX_FRAMES", 2):
            result = self.collect(zstd.compress(b"") * 3)
        self.assertEqual(result, [(1, None, "zstd_frame_limit")])

    def test_decode_steps_are_bounded(self) -> None:
        with patch.object(compressed, "MAX_DECODER_STEPS", 2):
            result = list(compressed.iter_zstd_lines(ShortReads(zstd.compress(b"one\n"))))
        self.assertEqual(result[-1][2], "zstd_step_limit")

    def test_elapsed_limit_is_checked(self) -> None:
        with patch.object(compressed.time, "monotonic", side_effect=[0, 31]):
            result = self.collect(zstd.compress(b"one\n"))
        self.assertEqual(result, [(1, None, "zstd_time_limit")])

    def test_read_errors_have_fixed_diagnostic_without_details(self) -> None:
        class FailedRead(io.BytesIO):
            def read(self, size: int = -1) -> bytes:
                raise OSError("sensitive synthetic content")

        self.assertEqual(
            list(compressed.iter_zstd_lines(FailedRead())), [(1, None, "zstd_read_error")]
        )

    def test_invalid_limits_are_rejected(self) -> None:
        for limits in (
            {"max_record_bytes": 0},
            {"max_total_bytes": -1},
            {"max_record_bytes": True},
        ):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                self.collect(zstd.compress(b"one\n"), **limits)


if __name__ == "__main__":
    unittest.main()
