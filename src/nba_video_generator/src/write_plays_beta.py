import os
import subprocess
import time
import av
# from moviepy import \
#     TextClip, VideoFileClip, CompositeVideoClip, concatenate_videoclips


def write_plays(title: str, base_name: str, date: str, player_urls: list[tuple[str, str]], ffmpeg_path: str, preset: str):
    desc_txt = open(title + " description.txt", "w+")
    time_secs = 0

    for i, (event_url, desc) in enumerate(player_urls):
        desc_txt.write(time.strftime('%H:%M:%S', time.gmtime(time_secs)) + " - " + desc + "\n")
        with open("temp.txt", "w") as f:
            f.write(desc)
        subprocess.run([
            ffmpeg_path, "-i", event_url, "-vf",
            f"drawtext=textfile='temp.txt':x=(w-text_w)/2:y=5:fontsize=18:fontcolor=white",
            "-c:v", "libx264", "-preset", preset, "-crf", "0", "-c:a", "copy", 
            "-movflags", "+faststart", "-y",
            base_name + "/" + base_name + "_" + date.replace("-", "") + "_play" + str(i) + ".mp4"
        ], check=True)
        # video_clip = VideoFileClip(event_url)
        # if include_caption:
        #     desc_clip = TextClip(
        #         text=desc, font_size=18, color="white",
        #         size=(1280, None)
        #     ).with_position("top").with_duration(video_clip.duration)
        #    clip = CompositeVideoClip([video_clip, desc_clip], use_bgclip=True)
        #     clip.audio = video_clip.audio
        # else:
        #     clip = video_clip
        with av.open(event_url) as container:
            time_secs += container.duration / 1e6
        # clip.write_videofile(
        #     base_name + "/" + base_name + "_" + date.replace("-", "") + "_play" +
        #     str(i) + ".mp4", fps=fps, preset=preset, threads=2
        # )
        # clip.close()
        # if include_caption:
        #     video_clip.close()
        #     desc_clip.close()

    desc_txt.close()

    files = [
        os.path.join(os.path.abspath(base_name), f)
        for f in os.listdir(base_name)
        if base_name in f
    ]

    files.sort(key=os.path.getctime)

    list_path = os.path.join(base_name, "file_list.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for file_path in files:
            safe_path = file_path.replace("\\", "/")
            safe_path = safe_path.replace("'", r"'\''")  # escape apostrophes
            f.write(f"file '{safe_path}'\n")

    output_path = title + ".mp4"

    if os.path.exists(output_path):
        os.remove(output_path)

    subprocess.run(
        [
            ffmpeg_path, "-f", "concat", "-safe", "0", "-i", list_path,
            "-vf", "drawbox=x=1070:y=0:w=210:h=40:color=black@1:t=fill", "-c:v", "libx264",
            "-crf", "10", "-c:a", "copy", output_path
        ],
        check=True
    )
