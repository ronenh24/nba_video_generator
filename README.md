# NBA Highlights Video Generator

## Videos
Posted on [NBA Full Play Highlights](https://www.youtube.com/@NBAFullPlayHighlights).

## Author
Ronen Huang  

## Time Frame
August 2025 to Present

## FFmpeg Build
Download from [https://www.gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/).

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

## Beta
The full play videos can be made from the reliable play by play rather than the unreliable box score. This does not work for compilations yet.

```python
from nba_video_generator.beta_search import pipeline

pipeline(
    [
        ("DiVincenzo", "2026-04-20", "min"),
    ], 
    {
        "ffmpeg_path": r"C:\Users\ronen\Documents\Projects\nba_video_generator\src\nba_video_generator\ffmpeg-2025-10-21-git-535d4047d3-essentials_build\bin\ffmpeg.exe"
    }
)
```

## Process
1. Specify the player last name (as per NBA.com website), team abbreviation, and date (yyyy-mm-dd).
2. Programs crawls through play by play by quarter, keeping a list of links and times.
3. Events within 5 seconds of each other are merged to a single event.
4. Plays are concatenated together to make the video.

A video of the process is provided below.

https://www.youtube.com/watch?v=84GDSAL5CeE

