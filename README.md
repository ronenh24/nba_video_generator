# NBA Highlights Video Generator

## Author
Ronen Huang  

## Time Frame
August 2025 to Present

## How the Generator Works
1. The user provides the full player name (as per NBA website), the date range, the team abbreviated (as per NBA website), and choices of what highlights to include. An example can be seen below.
    ```python
    from nba_video_generator.search import generate_video

    jalen_green_assists_urls = generate_video(
        player_name="Jalen Green",
        date_start="2024-11-01", 
        date_end="2024-11-08",
        team="hou",
        FGM=False,
        FGA=False,
        ThreePM=False,
        ThreePA=False,
        OREB=False,
        DREB=False,
        REB=False, 
        AST=True,
        STL=False,
        BLK=False,
        TO=True,
        PF=False
    )
    ```
2. The program crawls the NBA website for links to the box score involving the player team.
3. The program crawls the team box score for links to the events involving the player.
4. The program crawls the player events for links to the videos.

If field goals or personal fouls are selected as highlight, the corresponding ESPN play by play link is used to determine the times of those events. Then the NBA play by play link is crawled for the videos of those events.

The output returns a dictionary where the keys are the dates and the events are the sorted list of events (represented as a tuple of video url, quarter, and time). An example can be seen below.
```python
{
    '2024-11-02':
        [
            (video url 1, '1', '8:12'),
            (video url 2, '3', '9:50'),
            (video url 3, '3', '8:52'),
            (video url 4, '3','2:38')
        ],
    '2024-11-04':
        [
            (video url 5, '3', '1:37'),
            (video url 6, '4', '11:28'),
            (video url 7, '4', '10:54'),
            (video url 8, '4', '10:28'),
            (video url 9, '4', '2:10'),
            (video url 10, '4', '1:34')
        ],
    ...
}
```


### NBA Team Abbreviations
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

## How to Make Video From Event URLS
Once the dictionary of event urls are obtained from the ``generate_videos`` method, the user can make the MP4 video with the ``make_video`` method which takes parameters
- video_urls - dictionary of event urls
- base_name - name of video
- fps - frame per second
- preset - Choose from "ultrafast", "veryfast", "superfast", "faster", "fast", "medium", "slow", "slower", "veryslow", "placebo"
- segment - how to create videos with "Whole", "Game" (one video per game), "Quarter" (one video per quarter), "Play" (one video per play)

An example can be seen below.
```python
from nba_video_generator.search import make_video

make_video(
    video_urls=jalen_green_assists_urls,
    base_name="jalen_green_assists",
    fps=30, preset="ultrafast",
    segment="Whole"
)

```

## Examples
The examples can be seen in the ``make_videos_example.ipynb`` notebook which demonstrate the outputs of both methods described above.
