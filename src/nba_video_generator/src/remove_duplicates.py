#!/usr/bin/env python3
"""
remove_duplicates.py
"""
import os
import subprocess
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Repeat:
    """A sequence at [start, end) that plays again `offset` seconds later."""
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
        return (f"{self.start:.2f}-{self.end:.2f}s  ==  "
                f"{self.second_start:.2f}-{self.second_end:.2f}s   "
                f"(length {self.length:.1f}s, offset {self.offset:.2f}s, "
                f"diff {self.diff:.1f})")


class VideoDeduper:
    def __init__(
            self, path: str, ffmpeg_path: str, keep="last", fps=30,
            max_dist=10, min_sec=1.5, min_gap=1.5, max_diff=10, crf=18,
            preset="veryfast", verbose=True, ffprobe_path=None):
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        if keep not in ("first", "last"):
            raise ValueError("keep must be 'first' or 'last'")
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

    # ------------------------------------------------------------ utilities
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
            out = self._run(
                [
                    self.ffprobe_path, "-v", "error", "-show_entries",
                    "format=duration", "-of", "default=nw=1:nk=1", self.path
                ]
            ).stdout
            self._total = float(out.decode().strip())
        return self._total

    @property
    def has_audio(self):
        if self._audio is None:
            out = self._run(
                [
                    self.ffprobe_path, "-v", "error", "-select_streams", "a",
                    "-show_entries", "stream=index", "-of", "csv=p=0",
                    self.path
                ]
            ).stdout
            self._audio = bool(out.strip())
        return self._audio

    def grab_frames(self, start, length, fps, w, h):
        cmd = [
            self.ffmpeg_path, "-v", "error", "-ss", f"{start:.3f}", "-t",
            f"{length:.3f}", "-i", self.path, "-vf",
            f"fps={fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-"
        ]
        raw = self._run(cmd).stdout
        return np.frombuffer(
            raw, np.uint8
        ).reshape(-1, h, w).astype(np.float32)

    @staticmethod
    def phash(img):
        d = cv2.dct(img)[:8, :8]
        return (d > np.median(d[1:])).ravel()

    # ----------------------------------------------------- step 1: coarse scan
    def distance_matrix(self):
        self._log("Sampling frames...")
        frames = self.grab_frames(0, 1e9, self.fps, 32, 32)
        n = len(frames)
        self._log(f"  {n} frames at {self.fps} fps ({n / self.fps:.1f}s)")

        hashes = np.stack([self.phash(f) for f in frames])
        flat = frames.reshape(n, -1).std(axis=1) < 8
        del frames  # free ~15 MB before building the n×n matrix

        # Hamming distance via matmul:
        # dist[i,j] = sum(h[i]) + sum(h[j]) - 2*dot(h[i],h[j])
        h = hashes.astype(np.int8)
        sums = h.sum(axis=1)
        matches = h @ h.T
        dist = sums[:, None] + sums[None, :] - 2 * matches
        return dist, flat

    def diagonal_runs(self, match):
        n = len(match)
        gap = int(self.min_gap * self.fps)
        runs = []
        for off in range(gap, n):
            diag = np.diagonal(match, offset=off)
            i, length = 0, len(diag)
            while i < length:
                if diag[i]:
                    j = i
                    while j < length and diag[j]:
                        j += 1
                    runs.append([off, i, j])
                    i = j
                else:
                    i += 1
        runs.sort()
        merged = []
        for off, s, e in runs:
            if merged and merged[-1][0] == off and s - merged[-1][2] <= 2:
                merged[-1][2] = e
            else:
                merged.append([off, s, e])
        return merged

    def find_candidates(self):
        dist, flat = self.distance_matrix()
        match = (dist <= self.max_dist) & ~flat[:, None] & ~flat[None, :]
        min_len = int(self.min_sec * self.fps)

        cands = []
        for off, s, e in self.diagonal_runs(match):
            if e - s < min_len:
                continue
            if (e - s) > off + int(0.75 * self.fps):
                continue
            cands.append(Repeat(s / self.fps, e / self.fps, off / self.fps))
        return self._unique(cands)

    @staticmethod
    def _unique(cands):
        ov = lambda a, b, c, d: max(0.0, min(b, d) - max(a, c))
        cands = sorted(cands, key=lambda c: -c.length)
        chosen = []
        for c in cands:
            dup = any(ov(c.start, c.end, k.start, k.end) > 0.5 * c.length and
                      ov(
                          c.second_start, c.second_end,
                          k.second_start, k.second_end
                        ) > 0.5 * c.length
                      for k in chosen)
            if not dup:
                chosen.append(c)
        return sorted(chosen, key=lambda c: c.start)

    # ----------------------------------------------------- step 2: refinement
    def refine(self, cand, fps=30):
        w, h = 64, 36
        ta0, ta1 = max(0.0, cand.start - 2), min(self.total, cand.end + 2)
        tb0 = max(0.0, cand.second_start - 3)
        tb1 = min(self.total, cand.second_end + 3)
        fa = self.grab_frames(ta0, ta1 - ta0, fps, w, h)
        fb = self.grab_frames(tb0, tb1 - tb0, fps, w, h)

        margin = min(1.0, 0.2 * cand.length)
        core0 = int((cand.start + margin - ta0) * fps)
        core1 = int((cand.end - margin - ta0) * fps)
        if core1 <= core0:
            return None
        core = fa[core0:core1]

        best = None
        for lag in np.arange(
            cand.offset - 1.0, cand.offset + 1.0 + 1e-9, 1.0 / fps
        ):
            j0 = int(round((ta0 + core0 / fps + lag - tb0) * fps))
            if j0 < 0 or j0 + len(core) > len(fb):
                continue
            err = np.abs(core - fb[j0:j0 + len(core)]).mean()
            if best is None or err < best[0]:
                best = (err, lag)
        if best is None:
            return None
        err, lag = best

        thresh = max(6.0, err * 2.5)
        good = np.zeros(len(fa), dtype=bool)
        for i in range(len(fa)):
            j = int(round((ta0 + i / fps + lag - tb0) * fps))
            if 0 <= j < len(fb) and np.abs(fa[i] - fb[j]).mean() < thresh:
                good[i] = True
        idx = np.nonzero(good)[0]
        if len(idx) == 0:
            return None

        runs, st, pr = [], idx[0], idx[0]
        for i in idx[1:]:
            if i - pr > 3:
                runs.append((st, pr))
                st = i
            pr = i
        runs.append((st, pr))
        st, en = max(runs, key=lambda r: r[1] - r[0])
        return Repeat(ta0 + st / fps, ta0 + (en + 1) / fps,
                      float(lag), float(err))

    def is_valid(self, rep):
        if rep.length < self.min_sec - 1:
            return False
        if rep.diff > self.max_diff:
            return False
        if rep.length > rep.offset + 0.75:
            return rep.offset >= 2.0 and rep.diff <= 0.4 * self.max_diff
        return True

    def detect(self):
        cands = self.find_candidates()
        self._log(f"\n{len(cands)} candidate repeat(s) found")
        repeats = []
        for c in cands:
            r = self.refine(c)
            if r is None:
                self._log(
                    f"  {c.start:.1f}-{c.end:.1f}s: could not verify, skipped"
                )
            elif not self.is_valid(r):
                self._log(
                    f"  {r.start:.1f}-{r.end:.1f}s (diff {r.diff:.1f}): "
                    "static shot or weak match, skipped"
                )
            else:
                self._log(f"  {r}")
                repeats.append(r)
        return repeats

    # ------------------------------------------------------------ step 3: cut
    def plan_removals(self, repeats):
        removals = []
        for r in repeats:
            if self.keep == "last":
                if r.end - r.second_start > 0.75:
                    end = r.end
                elif r.end > r.second_start - 1.0:
                    end = r.second_start
                else:
                    end = r.end
                removals.append((r.start, end))
            else:
                removals.append((r.second_start, r.second_end))
        removals.sort()
        merged = []
        for s, e in removals:
            if merged and s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        return [tuple(m) for m in merged]

    def keep_ranges(self, removals):
        keeps, pos = [], 0.0
        for s, e in removals:
            if s - pos > 0.05:
                keeps.append((pos, s))
            pos = e
        if self.total - pos > 0.05:
            keeps.append((pos, self.total))
        return keeps

    def build_ffmpeg_command(
            self, removals, output, video_filter=None, extra_args=()
    ):
        keeps = self.keep_ranges(removals)
        audio = self.has_audio
        parts = []
        for k, (s, e) in enumerate(keeps):
            parts.append(
                f"[0:v]trim=start={s:.3f}:"
                f"end={e:.3f},setpts=PTS-STARTPTS[v{k}]"
            )
            if audio:
                parts.append(
                    f"[0:a]atrim=start={s:.3f}:end={e:.3f},"
                    f"asetpts=PTS-STARTPTS[a{k}]"
                )
        inputs = "".join(f"[v{k}][a{k}]" if audio else f"[v{k}]"
                         for k in range(len(keeps)))
        parts.append(f"{inputs}concat=n={len(keeps)}:v=1:a={1 if audio else 0}"
                     f"[vcat]{'[outa]' if audio else ''}")
        parts.append(f"[vcat]{video_filter or 'null'}[outv]")
        cmd = [
            self.ffmpeg_path, "-y", "-i", self.path,
            "-filter_complex", ";".join(parts), "-map", "[outv]"
        ]
        if audio:
            cmd += ["-map", "[outa]", "-c:a", "aac"]
        cmd += [
            "-c:v", "libx264", "-crf", str(self.crf), "-preset",
            self.preset, *extra_args, output]
        return cmd

    def cut(self, removals, output, video_filter=None, extra_args=()):
        self._log("Cutting and encoding (this can take a while)...")
        subprocess.run(
            self.build_ffmpeg_command(
                removals, output, video_filter, extra_args
            ), check=True)

    # ---------------------------------------------------------------- driver
    def run(self, output=None, dry_run=False):
        output = output or os.path.splitext(self.path)[0] + "_deduped.mp4"
        repeats = self.detect()
        if not repeats:
            self._log(
                "No duplicated sequences found. Try max_dist=14 or min_sec=3."
            )
            return None
        removals = self.plan_removals(repeats)
        removed = sum(e - s for s, e in removals)
        self._log(f"\nWill remove (keeping the {self.keep} copy):")
        for s, e in removals:
            self._log(f"  {s:.2f}-{e:.2f}s")
        new_length = self.total - removed
        self._log(
            f"Total removed: {removed:.1f}s  ->  new length {new_length:.1f}s"
        )
        if dry_run:
            self._log(
                "\nDry run: nothing written. Check the ranges by eye "
                "before cutting."
            )
            return removals
        self.cut(removals, output)
        self._log(f"\nDone: {output}")
        return output
