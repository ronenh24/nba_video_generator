"""Direct HTTP downloads for NBA video media."""
import os
from urllib.parse import parse_qs, urlparse

import requests


VIDEO_EVENTS_ASSET_URL = "https://stats.nba.com/stats/videoeventsasset"
VIDEO_EVENTS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}

MEDIA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Encoding": "identity",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://harbor-lane-6d2c.pages.dev/",
    "Sec-Fetch-Dest": "video",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-Storage-Access": "active",
}


def video_events_asset_url(game_id: str, event_id: int) -> str:
    """Build the NBA endpoint URL for a play's video metadata."""
    return (
        f"{VIDEO_EVENTS_ASSET_URL}?GameID={game_id}"
        f"&GameEventID={event_id}"
    )


def resolve_video_url(asset_url: str) -> str:
    """Resolve a videoeventsasset URL to its 1280x720 MP4 media URL."""
    params = parse_qs(urlparse(asset_url).query)
    try:
        game_id = params["GameID"][0]
        event_id = int(params["GameEventID"][0])
    except (KeyError, IndexError, ValueError) as exc:
        raise ValueError(
            f"Invalid videoeventsasset URL: {asset_url}"
        ) from exc

    response = requests.get(
        VIDEO_EVENTS_ASSET_URL,
        params={"GameID": game_id, "GameEventID": event_id},
        headers=VIDEO_EVENTS_HEADERS,
        timeout=(15, 45),
    )
    response.raise_for_status()
    data = response.json()

    try:
        result_sets = data["resultSets"]
        metadata = result_sets["Meta"]
        playlist = result_sets["playlist"]
        event = next(
            item for item in playlist
            if str(item["gi"]) == game_id and int(item["ei"]) == event_id
        )
        video = next(
            item for item in metadata["videoUrls"] if item.get("uuid")
        )
        year = int(event["y"])
        month = int(event["m"])
        day = int(event["d"])
        video_uuid = video["uuid"]
    except (KeyError, IndexError, StopIteration, TypeError, ValueError) as exc:
        raise ValueError(
            f"No video metadata found for game {game_id}, event {event_id}"
        ) from exc

    return (
        "https://videos.nba.com/nba/pbp/media/"
        f"{year}/{month:02d}/{day:02d}/{game_id}/{event_id}/"
        f"{video_uuid}_1280x720.mp4"
    )


def download_media(url: str, path: str, referer: str | None = None) -> None:
    """Stream an NBA MP4 to disk and atomically replace the destination."""
    headers = dict(MEDIA_HEADERS)
    if referer:
        headers["Referer"] = referer

    temp_path = path + ".part"
    downloaded = 0
    prefix = bytearray()
    try:
        with requests.get(
            url, headers=headers, stream=True, timeout=(15, 90)
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()
            if content_type and not (
                content_type.startswith("video/")
                or "application/octet-stream" in content_type
            ):
                raise ValueError(
                    f"Expected video content, received {content_type}"
                )

            with open(temp_path, "wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    if len(prefix) < 16:
                        prefix.extend(chunk[:16 - len(prefix)])
                    output.write(chunk)
                    downloaded += len(chunk)

        if not downloaded:
            raise ValueError("Downloaded video is empty")
        if b"ftyp" not in prefix:
            raise ValueError("Response does not contain an MP4 file header")

        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
