import os
import subprocess
import tempfile
import time
import av


def _escape_path_for_filter(path: str) -> str:
    """Escape a filesystem path for use inside an ffmpeg filtergraph option value
    (e.g. textfile='...'). Forward-slash the separators and escape any drive-letter
    colon, since ':' is the filtergraph option separator."""
    return path.replace("\\", "/").replace(":", "\\:")


def write_plays(title: str, base_name: str, date: str, player_urls: list[tuple[str, str]], ffmpeg_path: str, preset: str,
                 time_secs: float = 0, desc_txt=None):
    if desc_txt is None:
        desc_txt = open(title + " description.txt", "w+")

    os.makedirs(base_name, exist_ok=True)

    # Probe durations up front (cheap header read, no decode) so we can write the
    # running timeline before doing any encoding.
    durations = []
    for event_url, desc in player_urls:
        desc_txt.write(time.strftime('%H:%M:%S', time.gmtime(time_secs)) + " - " + desc + "\n")
        with av.open(event_url) as container:
            duration = container.duration / 1e6
        durations.append(duration)
        time_secs += duration

    n = len(player_urls)
    inputs = []
    filter_parts = []
    concat_inputs = ""
    caption_files = []

    for i, (event_url, desc) in enumerate(player_urls):
        inputs += ["-i", event_url]

        fd, caption_path = tempfile.mkstemp(suffix=".txt", prefix=f"caption_{i}_")
        with os.fdopen(fd, "w") as f:
            f.write(desc)
        caption_files.append(caption_path)

        safe_caption_path = _escape_path_for_filter(os.path.abspath(caption_path))
        filter_parts.append(
            f"[{i}:v]drawtext=textfile='{safe_caption_path}':x=(w-text_w)/2:y=5:fontsize=18:fontcolor=white[v{i}]"
        )
        concat_inputs += f"[v{i}][{i}:a]"

    filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=1[vcat][a]")
    filter_parts.append("[vcat]drawbox=x=1070:y=0:w=210:h=40:color=black@1:t=fill[vout]")
    filter_complex = ";".join(filter_parts)

    output_path = title + ".mp4"
    if os.path.exists(output_path):
        os.remove(output_path)

    try:
        subprocess.run(
            [
                ffmpeg_path,
                *inputs,
                "-filter_complex", filter_complex,
                "-map", "[vout]", "-map", "[a]",
                "-c:v", "libx264", "-preset", preset, "-crf", "10",
                "-c:a", "aac",
                "-movflags", "+faststart", "-y",
                output_path,
            ],
            check=True,
        )
    finally:
        for caption_path in caption_files:
            try:
                os.remove(caption_path)
            except OSError:
                pass

    for event_url, _ in player_urls:
        os.remove(event_url)

    return time_secs, desc_txt
