#!/usr/bin/env python3
"""Detect and remove repeated video segments while preserving unique footage."""
import os
import subprocess
from dataclasses import dataclass

import numpy as np


def _dct_basis(size):
    positions = np.arange(size, dtype=np.float32)
    frequencies = positions[:, None]
    basis = np.cos(
        np.pi * (2 * positions[None, :] + 1) * frequencies / (2 * size)
    ).astype(np.float32)
    basis[0] *= np.sqrt(1 / size)
    basis[1:] *= np.sqrt(2 / size)
    return basis


_DCT32 = _dct_basis(32)


@dataclass
class Repeat:
    """A sequence at [start, end) repeated `offset` seconds later."""

    start: float
    end: float
    offset: float
    diff: float = 0.0

    @property
    def length(self):
        return self.end - self.start

    @property
    def second_start(self):
        return self.start + self.offset

    @property
    def second_end(self):
        return self.end + self.offset

    def __str__(self):
        return (
            f"{self.start:.2f}-{self.end:.2f}s  ==  "
            f"{self.second_start:.2f}-{self.second_end:.2f}s   "
            f"(length {self.length:.1f}s, offset {self.offset:.2f}s, "
            f"diff {self.diff:.1f})"
        )


class VideoDeduper:
    """Find repeated image sequences and cut one copy from the video.

    The default policy keeps the earliest occurrence of each repeated
    sequence. This preserves the original order and any unique footage
    between a play and its replay.
    """

    def __init__(
            self, path: str, ffmpeg_path: str, keep="last", fps=5,
            max_dist=10, min_sec=1.5, min_gap=1.5, max_diff=10, crf=18,
            preset="veryfast", verbose=True, ffprobe_path=None):
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        if keep not in ("first", "last"):
            raise ValueError("keep must be 'first' or 'last'")
        if fps <= 0:
            raise ValueError("fps must be greater than zero")
        if min_sec <= 0 or min_gap < 0:
            raise ValueError("min_sec must be positive and min_gap nonnegative")

        self.path = path
        self.keep = keep
        self.fps = fps
        self.max_dist = max_dist
        self.min_sec = min_sec
        self.min_gap = min_gap
        self.crf = crf
        self.preset = preset
        self.verbose = verbose
        self.max_diff = max_diff
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path or self._sibling_ffprobe(ffmpeg_path)
        self._total = None
        self._audio = None

    @staticmethod
    def _sibling_ffprobe(ffmpeg_path):
        folder, name = os.path.split(ffmpeg_path)
        base, ext = os.path.splitext(name)
        probe = "ffprobe" if base.lower() == "ffmpeg" \
            else base.replace("ffmpeg", "ffprobe")
        return os.path.join(folder, probe + ext)

    def _log(self, msg=""):
        if self.verbose:
            print(msg)

    @staticmethod
    def _run(cmd):
        return subprocess.run(cmd, capture_output=True, check=True)

    @property
    def total(self):
        if self._total is None:
            out = self._run([
                self.ffprobe_path, "-v", "error", "-show_entries",
                "format=duration", "-of", "default=nw=1:nk=1", self.path,
            ]).stdout
            self._total = float(out.decode().strip())
        return self._total

    @property
    def has_audio(self):
        if self._audio is None:
            out = self._run([
                self.ffprobe_path, "-v", "error", "-select_streams", "a",
                "-show_entries", "stream=index", "-of", "csv=p=0", self.path,
            ]).stdout
            self._audio = bool(out.strip())
        return self._audio

    def grab_frames(self, start, length, fps, w, h):
        cmd = [
            self.ffmpeg_path, "-v", "error", "-ss", f"{start:.3f}", "-t",
            f"{length:.3f}", "-i", self.path, "-vf",
            f"fps={fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-",
        ]
        raw = self._run(cmd).stdout
        frame_size = w * h
        frame_count = len(raw) // frame_size
        if not frame_count:
            return np.empty((0, h, w), dtype=np.float32)
        usable = raw[:frame_count * frame_size]
        return np.frombuffer(
            usable, np.uint8
        ).reshape(-1, h, w).astype(np.float32)

    @staticmethod
    def phash(img):
        transformed = _DCT32 @ img @ _DCT32.T
        low_frequency = transformed[:8, :8]
        return (low_frequency > np.median(low_frequency[1:])).ravel()

    def distance_matrix(self):
        """Return pairwise perceptual-hash distances and flat-frame flags."""
        self._log("Sampling frames...")
        frames = self.grab_frames(0, self.total, self.fps, 32, 32)
        count = len(frames)
        self._log(f"  {count} frames at {self.fps} fps "
                  f"({count / self.fps:.1f}s)")
        if not count:
            return np.empty((0, 0), dtype=np.uint8), np.empty(0, dtype=bool)

        hashes = np.stack([self.phash(frame) for frame in frames])
        flat = frames.reshape(count, -1).std(axis=1) < 8
        del frames

        packed = np.packbits(hashes, axis=1)
        distances = np.empty((count, count), dtype=np.uint8)
        popcount = np.array([bin(value).count("1") for value in range(256)],
                            dtype=np.uint8)
        chunk_size = max(1, min(256, 2_000_000 // count))
        for start in range(0, count, chunk_size):
            stop = min(count, start + chunk_size)
            xor = np.bitwise_xor(
                packed[start:stop, None, :],
                packed[None, :, :],
            )
            distances[start:stop] = popcount[xor].sum(axis=2)
        return distances, flat

    def diagonal_runs(self, match):
        """Find contiguous matching frames on each positive time offset."""
        count = len(match)
        min_offset = max(1, int(round(self.min_gap * self.fps)))
        gap_tolerance = max(1, int(round(0.4 * self.fps)))
        runs = []

        for offset in range(min_offset, count):
            diagonal = np.diagonal(match, offset=offset)
            indices = np.flatnonzero(diagonal)
            if not len(indices):
                continue

            start = previous = int(indices[0])
            for index in indices[1:]:
                index = int(index)
                if index - previous > gap_tolerance + 1:
                    runs.append((offset, start, previous + 1))
                    start = index
                previous = index
            runs.append((offset, start, previous + 1))

        return runs

    def find_candidates(self):
        distances, flat = self.distance_matrix()
        if not len(flat):
            return []
        match = (
            (distances <= self.max_dist)
            & ~flat[:, None]
            & ~flat[None, :]
        )
        min_frames = max(1, int(round(self.min_sec * self.fps)))
        candidates = []

        for offset, start, end in self.diagonal_runs(match):
            if end - start < min_frames:
                continue
            candidates.append(Repeat(
                start / self.fps,
                end / self.fps,
                offset / self.fps,
            ))

        return self._unique(candidates)

    @staticmethod
    def _overlap(a0, a1, b0, b1):
        return max(0.0, min(a1, b1) - max(a0, b0))

    @classmethod
    def _unique(cls, candidates):
        """Discard near-identical candidate windows, preferring longer runs."""
        chosen = []
        for candidate in sorted(candidates, key=lambda item: -item.length):
            duplicate = False
            for existing in chosen:
                same_first = cls._overlap(
                    candidate.start, candidate.end,
                    existing.start, existing.end,
                ) > 0.5 * candidate.length
                same_second = cls._overlap(
                    candidate.second_start, candidate.second_end,
                    existing.second_start, existing.second_end,
                ) > 0.5 * candidate.length
                if same_first and same_second:
                    duplicate = True
                    break
            if not duplicate:
                chosen.append(candidate)
        return sorted(chosen, key=lambda item: (item.start, item.offset))

    def refine(self, candidate, fps=30):
        """Align and tighten a coarse candidate using larger grayscale frames."""
        width, height = 64, 36
        first_start = max(0.0, candidate.start - 2.0)
        first_end = min(self.total, candidate.end + 2.0)
        second_start = max(0.0, candidate.second_start - 3.0)
        second_end = min(self.total, candidate.second_end + 3.0)
        first = self.grab_frames(
            first_start, first_end - first_start, fps, width, height
        )
        second = self.grab_frames(
            second_start, second_end - second_start, fps, width, height
        )
        if not len(first) or not len(second):
            return None

        margin = min(1.0, 0.2 * candidate.length)
        core_start = int(round(
            (candidate.start + margin - first_start) * fps
        ))
        core_end = int(round(
            (candidate.end - margin - first_start) * fps
        ))
        core = first[max(0, core_start):min(len(first), core_end)]
        if not len(core):
            return None

        best = None
        lag_step = 1.0 / fps
        for lag in np.arange(
                candidate.offset - 1.0,
                candidate.offset + 1.0 + lag_step / 2,
                lag_step):
            second_index = int(round(
                (first_start + max(0, core_start) / fps + lag
                 - second_start) * fps
            ))
            if second_index < 0 or second_index + len(core) > len(second):
                continue
            error = np.abs(
                core - second[second_index:second_index + len(core)]
            ).mean()
            if best is None or error < best[0]:
                best = (float(error), float(lag))
        if best is None:
            return None

        base_error, lag = best
        threshold = max(6.0, base_error * 2.5)
        matches = np.zeros(len(first), dtype=bool)
        for index, frame in enumerate(first):
            second_index = int(round(
                (first_start + index / fps + lag - second_start) * fps
            ))
            if 0 <= second_index < len(second):
                error = np.abs(frame - second[second_index]).mean()
                matches[index] = error < threshold

        indices = np.flatnonzero(matches)
        if not len(indices):
            return None

        gap = max(1, int(round(0.1 * fps)))
        runs = []
        start = previous = int(indices[0])
        for index in indices[1:]:
            index = int(index)
            if index - previous > gap + 1:
                runs.append((start, previous + 1))
                start = index
            previous = index
        runs.append((start, previous + 1))
        run_start, run_end = max(runs, key=lambda run: run[1] - run[0])
        if run_end - run_start < int(round(self.min_sec * 0.75 * fps)):
            return None

        errors = []
        for index in range(run_start, run_end):
            second_index = int(round(
                (first_start + index / fps + lag - second_start) * fps
            ))
            if 0 <= second_index < len(second):
                errors.append(np.abs(first[index] - second[second_index]).mean())
        mean_error = float(np.mean(errors)) if errors else base_error
        return Repeat(
            first_start + run_start / fps,
            first_start + run_end / fps,
            lag,
            mean_error,
        )

    def is_valid(self, repeat):
        if repeat.length < max(0.75, self.min_sec * 0.75):
            return False
        if repeat.diff > self.max_diff:
            return False
        if repeat.length > repeat.offset + 0.75:
            return repeat.offset >= 2.0 and repeat.diff <= 0.4 * self.max_diff
        return True

    def detect(self):
        candidates = self.find_candidates()
        self._log(f"\n{len(candidates)} candidate repeat(s) found")
        repeats = []
        for candidate in candidates:
            repeat = self.refine(candidate)
            if repeat is None:
                self._log(
                    f"  {candidate.start:.1f}-{candidate.end:.1f}s: "
                    "could not verify, skipped"
                )
            elif not self.is_valid(repeat):
                self._log(
                    f"  {repeat.start:.1f}-{repeat.end:.1f}s "
                    f"(diff {repeat.diff:.1f}): weak match, skipped"
                )
            else:
                repeats.append(repeat)

        repeats = self._unique(repeats)
        for repeat in repeats:
            self._log(f"  {repeat}")
        return repeats

    def plan_removals(self, repeats):
        """Return merged ranges for redundant copies, without deleting both."""
        removals = []
        for repeat in repeats:
            first = (max(0.0, repeat.start), min(self.total, repeat.end))
            second = (
                max(0.0, repeat.second_start),
                min(self.total, repeat.second_end),
            )
            if first[1] <= first[0] or second[1] <= second[0]:
                continue

            duplicate = first if self.keep == "last" else second
            removals.append(duplicate)

        merged = []
        for start, end in sorted(removals):
            if merged and start <= merged[-1][1] + 0.05:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])

        result = [tuple(interval) for interval in merged]
        if sum(end - start for start, end in result) >= self.total - 0.05:
            self._log("Removal plan would erase the entire video; keeping it.")
            return []
        return result

    def keep_ranges(self, removals):
        """Calculate positive-length ranges that remain after removal."""
        keeps = []
        position = 0.0
        for start, end in removals:
            start = min(self.total, max(position, start))
            end = min(self.total, max(start, end))
            if start - position > 0.05:
                keeps.append((position, start))
            position = end
        if self.total - position > 0.05:
            keeps.append((position, self.total))
        if not keeps and self.total > 0:
            return [(0.0, self.total)]
        return keeps

    def build_ffmpeg_command(
            self, removals, output, video_filter=None, extra_args=()):
        keeps = self.keep_ranges(removals)
        if not keeps:
            raise ValueError("Cannot create output: no video ranges remain.")

        has_audio = self.has_audio
        filters = []
        for index, (start, end) in enumerate(keeps):
            filters.append(
                f"[0:v]trim=start={start:.3f}:end={end:.3f},"
                f"setpts=PTS-STARTPTS[v{index}]"
            )
            if has_audio:
                filters.append(
                    f"[0:a]atrim=start={start:.3f}:end={end:.3f},"
                    f"asetpts=PTS-STARTPTS[a{index}]"
                )

        streams = "".join(
            f"[v{index}][a{index}]" if has_audio else f"[v{index}]"
            for index in range(len(keeps))
        )
        filters.append(
            f"{streams}concat=n={len(keeps)}:v=1:a={1 if has_audio else 0}"
            f"[vcat]{'[outa]' if has_audio else ''}"
        )
        filters.append(f"[vcat]{video_filter or 'null'}[outv]")

        command = [
            self.ffmpeg_path, "-y", "-i", self.path,
            "-filter_complex", ";".join(filters),
            "-map", "[outv]",
        ]
        if has_audio:
            command += ["-map", "[outa]", "-c:a", "aac"]
        command += [
            "-c:v", "libx264", "-crf", str(self.crf),
            "-preset", self.preset, *extra_args, output,
        ]
        return command

    def cut(self, removals, output, video_filter=None, extra_args=()):
        self._log("Cutting and encoding...")
        subprocess.run(
            self.build_ffmpeg_command(
                removals, output, video_filter, extra_args
            ),
            check=True,
        )

    def run(self, output=None, dry_run=False):
        output = output or os.path.splitext(self.path)[0] + "_deduped.mp4"
        repeats = self.detect()
        if not repeats:
            self._log("No duplicated sequences found.")
            return None

        removals = self.plan_removals(repeats)
        if not removals:
            self._log("No safe duplicate ranges to remove.")
            return None

        removed = sum(end - start for start, end in removals)
        self._log(f"\nWill remove (keeping the {self.keep} copy):")
        for start, end in removals:
            self._log(f"  {start:.2f}-{end:.2f}s")
        self._log(
            f"Total removed: {removed:.1f}s  ->  "
            f"new length {self.total - removed:.1f}s"
        )
        if dry_run:
            self._log("\nDry run: nothing written.")
            return removals

        self.cut(removals, output)
        self._log(f"\nDone: {output}")
        return output
