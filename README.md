# NBA Highlights Video Generator

## Videos
Posted on [NBA Full Play Highlights](https://www.youtube.com/@NBAFullPlayHighlights).

## Author
Ronen Huang  

## Time Frame
August 2025 to Present

## FFmpeg Build
Download from [https://www.gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/).

## Ollama Build
Download from [https://ollama.com/download](https://ollama.com/download) and pull one time.
```bash
ollama pull lfm2.5-thinking:1.2b
```

## NBA Team Abbreviations
- atl - Atlanta Hawks
- bkn	- Brooklyn Nets
- bos	- Boston Celtics
- cha	- Charlotte Hornets
- chi	- Chicago Bulls
- cle	- Cleveland Cavaliers
- dal	- Dallas Mavericks
- den	- Denver Nuggets
- det	- Detroit Pistons
- gsw	- Golden State Warriors
- hou - Houston Rockets
- ind	- Indiana Pacers
- lac - Los Angeles Clippers
- lal	- Los Angeles Lakers
- mem	- Memphis Grizzlies
- mia	- Miami Heat
- mil	- Milwaukee Bucks
- min	- Minnesota Timberwolves
- nop	- New Orleans Pelicans
- nyk	- New York Knicks
- okc	- Oklahoma City Thunder
- orl	- Orlando Magic
- phi	- Philadelphia 76ers
- phx	- Phoenix Suns
- por	- Portland Trail Blazers
- sac	- Sacramento Kings
- sas - San Antonio Spurs
- tor	- Toronto Raptors
- uta	- Utah Jazz
- was	- Washington Wizards

## Manually Make Videos
The full play videos can be made from the reliable play by play rather than the unreliable box score.

```python
from nba_video_generator.src import pipeline

pipeline(
    [
        ("DiVincenzo", "2026-04-20", "min"),
    ], 
    {
        "ffmpeg_path": r"C:\Users\ronen\Documents\Projects\nba_video_generator\src\nba_video_generator\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe"
    }
)
```

A date range can be specified as well.

```python
from nba_video_generator.src import pipeline

pipeline(
    [
        ("Booker", "2026-04-19", "2026-04-27", "phx"),
    ],
    {"ffmpeg_path": r"C:\Users\ronen\Documents\Projects\nba_video_generator\src\nba_video_generator\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe"}
)
```

### Process
1. Specify the player last name (as per NBA.com website), team abbreviation, and date(s) (yyyy-mm-dd).
2. Programs crawls through play by play by quarter, keeping a list of links and times.
3. Events within 5 seconds of each other are merged to a single event.
4. Plays are concatenated together to make the video.

A video of the process is provided below.

[https://www.youtube.com/watch?v=84GDSAL5CeE](https://www.youtube.com/watch?v=-1npjVtfezU)

## Automatically Make Videos With Agent
Makes videos of the LLM determined best player performances of specified date (default today).

```python
from nba_video_generator.nba_agent import run_agent

date = "2026-06-10"

ffmpeg_path = r"C:\Users\ronen\Documents\Projects\nba_video_generator\src\nba_video_generator\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe"

run_agent(date, ffmpeg_path)
```

### Process
1. Specify the date (yyyy-mm-dd).
2. LLM chooses players from pool of candidates that meet thresholds in [src/nba_video_generator/nba_agent/config.py](src/nba_video_generator/nba_agent/config.py).
3. The videos are made with the `pipeline` method. The thumbnails with relevant statistics are made afterward.
4. (Optional) Upload to YouTube with Python. Example program in [src/nba_video_generator/example_youtube_upload_scripts](src/nba_video_generator/example_youtube_upload_scripts). Link to data api - [https://developers.google.com/youtube/v3/guides/uploading_a_video](https://developers.google.com/youtube/v3/guides/uploading_a_video).

A video of the process is provided below.

[https://www.youtube.com/watch?v=IC8SrrvS4xE&feature=youtu.be](https://www.youtube.com/watch?v=IC8SrrvS4xE&feature=youtu.be)

## Automatically Make Game Top Plays Shorts - **NEW**
Makes shorts of the top 4 plays from each of specified date (default today).

```python
from nba_video_generator.nba_shorts import make_shorts_for_date

date = "2016-06-19"

ffmpeg_path = r"C:\Users\ronen\Documents\Projects\nba_video_generator\src\nba_video_generator\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe"

make_shorts_for_date(date, ffmpeg_path)
```

## Web Interface
Run the video-generation and upload workflows from a local browser dashboard:

```bash
python -m pip install --upgrade nba-video-generator
nba-video-generator-web
```

After the new release is published, install it from PyPI as shown above. The
dashboard opens at `http://127.0.0.1:8765`. It includes forms for the
player pipeline (including date ranges and multiple players), the daily agent
(load finished games for a date and choose which to analyze), and top-plays
Shorts. Jobs run in the background and stream their output to the activity
panel. The YouTube upload workflow lets you select a video folder and
Google `client_secrets.json` using local file pickers. Uploads default to
private, preserve local files, and use a saved OAuth token under your home
directory. Only one workflow can run at a time. To choose another port or keep
the browser closed:

```bash
nba-video-generator-web --port 8766 --no-browser
```
