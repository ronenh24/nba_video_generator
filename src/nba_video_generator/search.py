"""
Author: Ronen Huang
"""


import os
from typing import Literal
from datetime import datetime, timedelta
from moviepy import \
    TextClip, VideoFileClip, CompositeVideoClip, concatenate_videoclips
from nba_video_generator.src.get_box_scores import \
    get_box_scores, get_free_throws_or_fouls
from nba_video_generator.src.get_player_urls import \
    get_player_urls, get_ft_urls, get_foul_urls
from nba_video_generator.src.get_videos import \
    get_videos, get_ft_or_foul_videos, sort_plays


# Map event to column.
stat_td = {
    "FGM": 3, "FGA": 4, "3PM": 6, "3PA": 7,
    "OREB": 12, "DREB": 13, "REB": 14, "AST": 15,
    "STL": 16, "BLK": 17, "TO": 18, "PF": 19
}
td_stat = {v: k for k, v in stat_td.items()}


def generate_video(
        player_name: str, date_start: str, date_end: str | None, team: str,
        FGM: bool = True, FGA: bool = False, ThreePM: bool = False,
        ThreePA: bool = False, OREB: bool = False, DREB: bool = False,
        REB: bool = False, AST: bool = True, STL: bool = True,
        BLK: bool = True, TO: bool = False, PF: bool = False
        ) -> dict[str, list[tuple[str, str, str]]]:
    """
    Specify start date and end date as Year/Month/Day
    (for example, 2025-06-22).

    Indicate true if event should be included.

    Output is dictionary with date as key and
    ordered list of events (url, quarter, time).

    atl - Atlanta Hawks
    bkn	- Brooklyn Nets
    bos	- Boston Celtics
    cha	- Charlotte Hornets
    chi	- Chicago Bulls
    cle	- Cleveland Cavaliers
    dal	- Dallas Mavericks
    den	- Denver Nuggets
    det	- Detroit Pistons
    gsw	- Golden State Warriors
    hou - Houston Rockets
    ind	- Indiana Pacers
    lac - Los Angeles Clippers
    lal	- Los Angeles Lakers
    mem	- Memphis Grizzlies
    mia	- Miami Heat
    mil	- Milwaukee Bucks
    min	- Minnesota Timberwolves
    nop	- New Orleans Pelicans
    nyk	- New York Knicks
    okc	- Oklahoma City Thunder
    orl	- Orlando Magic
    phi	- Philadelphia 76ers
    phx	- Phoenix Suns
    por	- Portland Trail Blazers
    sac	- Sacramento Kings
    sas - San Antonio Spurs
    tor	- Toronto Raptors
    uta	- Utah Jazz
    was	- Washington Wizards
    """
    if FGA:
        FGM = False
        ThreePM = False
        ThreePA = False
    if FGM:
        ThreePM = False
        ThreePA = False
    if ThreePA:
        ThreePM = False
    if REB or (OREB and DREB):
        OREB = False
        DREB = False
        REB = True
    team = team.lower()

    td_vals = []
    if FGM:
        td_vals.append(stat_td["FGM"])
    if FGA:
        td_vals.append(stat_td["FGA"])
    if ThreePM:
        td_vals.append(stat_td["3PM"])
    if ThreePA:
        td_vals.append(stat_td["3PA"])
    if OREB:
        td_vals.append(stat_td["OREB"])
    if DREB:
        td_vals.append(stat_td["DREB"])
    if REB:
        td_vals.append(stat_td["REB"])
    if AST:
        td_vals.append(stat_td["AST"])
    if STL:
        td_vals.append(stat_td["STL"])
    if BLK:
        td_vals.append(stat_td["BLK"])
    if TO:
        td_vals.append(stat_td["TO"])
    if PF:
        td_vals.append(stat_td["PF"])

    if date_end is None:
        date_end = date_start
    date_start_copy = datetime.strptime(date_start, '%Y-%m-%d').date()
    date_end_copy = datetime.strptime(date_end, '%Y-%m-%d').date()
    delta = timedelta(days=1)

    results = {}
    while date_start_copy <= date_end_copy:
        current_date = date_start_copy.strftime('%Y-%m-%d')
        box_score = get_box_scores(current_date, team)
        if box_score:
            player_urls = get_player_urls(player_name, box_score, td_vals)
            pbp_url = box_score.rsplit("/", 1)[0] + "/play-by-play?period="
            td_vid = {}
            for td_val, player_url in player_urls:
                if td_val <= 18:
                    fg = True
                    if td_val >= 12:
                        fg = False
                    td_vid.update(get_videos(player_url, fg))
                    if td_val <= 7:
                        pbp = get_free_throws_or_fouls(current_date, team)
                        if pbp:
                            include_two = td_val <= 4
                            ft_urls = get_ft_urls(
                                player_name, pbp, pbp_url, include_two
                            )
                            td_vid.update(get_ft_or_foul_videos(ft_urls))
                else:
                    pbp = get_free_throws_or_fouls(current_date, team)
                    if pbp:
                        foul_urls = get_foul_urls(player_name, pbp, pbp_url)
                        td_vid.update(get_ft_or_foul_videos(foul_urls))
            if len(td_vid) > 0:
                results[current_date] = sort_plays(pbp_url, td_vid)
            print()
        date_start_copy += delta

    return results


def make_video(
    video_urls: dict[str, list[tuple[str, str, str]]],
    base_name: str, fps: int = 30,
    preset: Literal["ultrafast", "veryfast", "superfast", "faster",
                    "fast", "medium", "slow", "slower", "veryslow",
                    "placebo"] = "fast",
    segment: Literal["Whole", "Game", "Quarter", "Play"] = "Whole"
) -> None:
    """
    base_name specifies video path.
    
    segment by Whole, Game, or Quarter
    """
    directories = base_name.rsplit("/", 1)[0]
    try:
        os.makedirs(directories)
    except Exception:
        pass

    video_clips = []
    for date, events in video_urls.items():
        i = 1
        if segment == "Quarter":
            _make_video_quarter(base_name, date, events, fps, preset)
        else:
            txt_clip = TextClip(
                text=date, font_size=36, color="white",
                size=(1280, 720)
            ).with_position("center").with_duration(2)
            video_clips.append(txt_clip)
            for event_url, desc, _, _ in events:
                clip = VideoFileClip(event_url)
                desc_clip = TextClip(
                    text=desc, font_size=28, color="white",
                    size=(1280, None)
                ).with_position("top").with_duration(clip.duration)
                video_clips.append(CompositeVideoClip([clip, desc_clip]))
                if segment == "Play":
                    if len(video_clips) == 2:
                        video = concatenate_videoclips(video_clips)
                    else:
                        video = video_clips[0]
                    video.write_videofile(
                        base_name + "_" + date.replace("-", "") + "_play" +
                        str(i) + ".mp4", fps=fps, preset=preset
                    )
                    i += 1
                    video_clips.clear()
            if segment == "Game":
                video = concatenate_videoclips(video_clips)
                video.write_videofile(
                    base_name + "_" + date.replace("-", "") + ".mp4",
                    fps=fps, preset=preset
                )
                video_clips.clear()

    if segment == "Whole":
        video = concatenate_videoclips(video_clips)
        first_date = list(video_urls.keys())[0].replace("-", "")
        last_date = list(video_urls.keys())[-1].replace("-", "")
        video.write_videofile(
            base_name + "_" + first_date + "_" + last_date + ".mp4",
            fps=fps, preset=preset
        )


def _make_video_quarter(
    base_name: str, date: str, events: list[tuple[str, str, str]],
    fps: int = 30, preset: str = "fast"
) -> None:
    video_clips = [
        TextClip(
            text=date, font_size=36, color="white",
            size=(1280, 720)
        ).with_position("center").with_duration(2)
    ]
    current_quarter = events[0][2]

    for event_url, desc, quarter, _ in events:
        video_clip = VideoFileClip(event_url)
        desc_clip = TextClip(
            text=desc, font_size=28, color="white",
            size=(1280, None)
        ).with_position("top").with_duration(video_clip.duration)
        clip = CompositeVideoClip([video_clip, desc_clip])
        if quarter == current_quarter:
            video_clips.append(clip)
        else:
            video = concatenate_videoclips(video_clips)
            video_name = base_name + "_" + date.replace("-", "") + \
                "q" + current_quarter + ".mp4"
            video.write_videofile(video_name, fps=fps, preset=preset)
            video_clips = [clip]
            current_quarter = quarter

    video = concatenate_videoclips(video_clips)
    video_name = base_name + "_" + date.replace("-", "") + \
        "q" + current_quarter + ".mp4"
    video.write_videofile(video_name, fps=fps, preset=preset)
