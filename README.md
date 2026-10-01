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
ollama pull llama3.1
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
from nba_video_generator.beta_search import pipeline

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
from nba_video_generator.beta_search import pipeline

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

## Automatically Make Videos With Agent - **NEW**
Makes videos of the LLM determined best player performances of specified date.

```python
from nba_video_generator.run_agent import nba_agent

date = "2025-12-25"

ffmpeg_path = r"C:\Users\ronen\Documents\Projects\nba_video_generator\src\nba_video_generator\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe"

nba_agent(date, ffmpeg_path)
```

### Process
1. Specify the date (yyyy-mm-dd).
2. LLM chooses players from pool of candidates that meet thresholds in [src\nba_video_generator\nba_agent\config.py](src\nba_video_generator\nba_agent\config.py).
3. The videos are made with the `pipeline` method. The thumbnails with relevant statistics are made afterward.
4. (Optional) Upload to YouTube with Python. Example program in [src\nba_video_generator\example_youtube_upload_scripts](src\nba_video_generator\example_youtube_upload_scripts). Link to data api - [https://developers.google.com/youtube/v3/guides/uploading_a_video](https://developers.google.com/youtube/v3/guides/uploading_a_video).

A video of the process is provided below.

[https://www.youtube.com/watch?v=IC8SrrvS4xE&feature=youtu.be](https://www.youtube.com/watch?v=IC8SrrvS4xE&feature=youtu.be)
