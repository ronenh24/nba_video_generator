import os
import subprocess
import tempfile
import time
import av

from .remove_duplicates import VideoDeduper


def _escape_path_for_filter(path: str) -> str:
    return path.replace("\\", "/").replace(":", "\\:")


def _overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def _remap_clips(starts, durations, removals, min_keep=1.0):
    """For each clip return (new_start, kept_seconds) after the removals, or None if
    less than `min_keep` seconds of the clip survive. Times are relative to the
    start of this call's video."""
    out = []
    for s, d in zip(starts, durations):
        e = s + d
        removed_before_start = sum(_overlap(rs, re, 0, s) for rs, re in removals)
        removed_inside = sum(_overlap(rs, re, s, e) for rs, re in removals)
        kept = d - removed_inside
        out.append((s - removed_before_start, kept) if kept >= min_keep else None)
    return out


def _combine_targets(clips, starts, durations, repeats, keep):
    """Map the index of each fully removed clip to the index of the surviving clip
    that holds the kept copy of the same footage."""
    def locate(t):
        for i, (s, d) in enumerate(zip(starts, durations)):
            if s <= t < s + d:
                return i
        return None

    targets = {}
    for i, clip in enumerate(clips):
        if clip is not None:
            continue
        j = i
        for _ in range(len(clips)):          # follow chains of removed clips
            t = starts[j] + durations[j] / 2
            t2 = None
            for r in repeats:
                if keep == "last" and r.start <= t <= r.end + 1.0:
                    t2 = t + r.offset
                    break
                if keep == "first" and r.second_start <= t <= r.second_end:
                    t2 = t - r.offset
                    break
            if t2 is None:
                j = None
                break
            j = locate(t2)
            if j is None or clips[j] is not None:
                break
        if j is not None and clips[j] is not None:
            targets[i] = j
    return targets


def write_plays(title: str, base_name: str, player_urls: list[tuple[str, str]], ffmpeg_path: str, preset: str,
                time_secs: float = 0, desc_txt=None):
    if desc_txt is None:
        desc_txt = open(title + " description.txt", "w+")

    os.makedirs(base_name, exist_ok=True)

    starts, durations, rel = [], [], 0.0
    for event_url, _ in player_urls:
        with av.open(event_url) as container:
            duration = container.duration / 1e6
        starts.append(rel)
        durations.append(duration)
        rel += duration

    n = len(player_urls)
    inputs = []
    for event_url, _ in player_urls:
        inputs += ["-i", event_url]
    concat_inputs = "".join(f"[{i}:v][{i}:a]" for i in range(n))

    output_path = title + ".mp4"
    raw_path = title + "_raw.mp4"
    caption_files = []

    try:
        # ---- pass 1: plain concat, no captions (near-lossless intermediate for detection) ----
        subprocess.run(
            [ffmpeg_path, *inputs,
             "-filter_complex", f"{concat_inputs}concat=n={n}:v=1:a=1[v][a]",
             "-map", "[v]", "-map", "[a]",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
             "-c:a", "pcm_s16le", "-y", raw_path],
            check=True,
        )

        # ---- detect repeats ----
        deduper = VideoDeduper(raw_path, ffmpeg_path, preset=preset, verbose=False)
        repeats = deduper.detect()
        removals = deduper.plan_removals(repeats)

        # ---- final clip timeline and descriptions ----
        clips = _remap_clips(starts, durations, removals)
        targets = _combine_targets(clips, starts, durations, repeats, deduper.keep)
        merged = {}
        for removed, survivor in targets.items():
            merged.setdefault(survivor, []).append(removed)

        entries = []                                   # (text, start, end) in the final video
        for idx, clip in enumerate(clips):
            if clip is None:
                continue
            parts = []
            for k in sorted([idx] + merged.get(idx, [])):
                d = player_urls[k][1]
                if d not in parts:
                    parts.append(d)
            new_start, kept = clip
            entries.append((" / ".join(parts), new_start, new_start + kept))

        # ---- pass 2: cut repeats and draw the captions on the final timeline ----
        draw = []
        for i, (text, t0, t1) in enumerate(entries):
            fd, caption_path = tempfile.mkstemp(suffix=".txt", prefix=f"caption_{i}_")
            with os.fdopen(fd, "w") as f:
                f.write(text)
            caption_files.append(caption_path)
            safe = _escape_path_for_filter(os.path.abspath(caption_path))
            draw.append(
                f"drawtext=textfile='{safe}':enable='gte(t,{t0:.3f})*lt(t,{t1:.3f})'"
                f":x=(w-text_w)/2:y=5:fontsize=18:fontcolor=white"
            )
        draw.append("drawbox=x=1070:y=0:w=210:h=40:color=purple@1:t=fill")
        draw.append(f"drawtext=text='youtube.com/@NBAFullPlayHighlights':x=1070+(210-text_w)/2:y=(40-text_h)/2:fontsize=12:fontcolor=white")

        deduper.cut(removals, output_path, video_filter=",".join(draw),
                    extra_args=["-movflags", "+faststart"])
    finally:
        for p in caption_files + [raw_path]:
            try:
                os.remove(p)
            except OSError:
                pass

    # ---- description file uses the same text and times as the captions ----
    for text, t0, _ in entries:
        desc_txt.write(time.strftime('%H:%M:%S', time.gmtime(time_secs + t0)) + " - " + text + "\n")

    time_secs += sum(durations) - sum(e - s for s, e in removals)

    for event_url, _ in player_urls:
        os.remove(event_url)

    return time_secs, desc_txt
