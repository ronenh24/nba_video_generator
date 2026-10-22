#!/usr/bin/env python3

import http.client as httplib
import httplib2
import os
import random
import sys
import time

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


# Explicitly tell the underlying HTTP transport library not to retry,
# since we are handling retry logic ourselves.
httplib2.RETRIES = 1

# Maximum number of times to retry before giving up.
MAX_RETRIES = 10

# Always retry when these exceptions are raised.
RETRIABLE_EXCEPTIONS = (
    httplib2.HttpLib2Error,
    IOError,
    httplib.NotConnected,
    httplib.IncompleteRead,
    httplib.ImproperConnectionState,
    httplib.CannotSendRequest,
    httplib.CannotSendHeader,
    httplib.ResponseNotReady,
    httplib.BadStatusLine,
)

# Always retry when an HttpError with one of these status codes is raised.
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

# Exit code meaning "the video uploaded fine, but the thumbnail did not".
EXIT_THUMBNAIL_FAILED = 2

# Exit code meaning "the video uploaded fine, but adding to playlists failed".
EXIT_PLAYLIST_FAILED = 3

# YouTube's limit for custom thumbnails.
MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024


# ---------------------------------------------------------------------------
# YouTube API configuration
# ---------------------------------------------------------------------------

CLIENT_SECRETS_FILE = r"C:\Users\ronen\Videos\nba_videos\client_secrets.json"

# OAuth scope required to upload videos. This scope is also accepted by
# thumbnails.set and playlistItems.insert.
YOUTUBE_UPLOAD_SCOPE = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube"  # <-- Add this line
]

YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

# OAuth token will be saved here after the first successful login.
TOKEN_FILE = "youtube-oauth2.json"

VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def get_authenticated_service(
    client_secrets_file: str = CLIENT_SECRETS_FILE,
    token_file: str = TOKEN_FILE,
):
    """
    Authenticate the user with Google OAuth 2.0 and return
    an authenticated YouTube API service.
    """

    credentials = None

    # Load an existing token if one exists.
    if os.path.exists(token_file):
        try:
            credentials = Credentials.from_authorized_user_file(
                token_file,
                YOUTUBE_UPLOAD_SCOPE
            )
        except Exception as e:
            print("Could not load existing OAuth token:")
            print(e)
            credentials = None

    # Refresh an expired token when possible.
    if credentials and credentials.expired and credentials.refresh_token:
        try:
            print("Refreshing OAuth credentials...")
            credentials.refresh(Request())
        except Exception as e:
            print("Could not refresh OAuth credentials:")
            print(e)
            credentials = None

    # If we don't have valid credentials, start OAuth login.
    if not credentials or not credentials.valid:
        if not os.path.isfile(client_secrets_file):
            raise FileNotFoundError(
                f"Client secrets file not found: {client_secrets_file}"
            )

        print("Starting Google OAuth authentication...")

        flow = InstalledAppFlow.from_client_secrets_file(
            client_secrets_file,
            YOUTUBE_UPLOAD_SCOPE
        )

        credentials = flow.run_local_server(
            port=0,
            access_type="offline",
            prompt="consent"
        )

        # Save credentials for the next run.
        token_directory = os.path.dirname(os.path.abspath(token_file))
        os.makedirs(token_directory, exist_ok=True)
        token_fd = os.open(
            token_file,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        with os.fdopen(token_fd, "w", encoding="utf-8") as token:
            token.write(credentials.to_json())

        print("OAuth credentials saved.")

    # Build the YouTube API service.
    youtube = build(
        YOUTUBE_API_SERVICE_NAME,
        YOUTUBE_API_VERSION,
        credentials=credentials
    )

    return youtube


# ---------------------------------------------------------------------------
# Video upload
# ---------------------------------------------------------------------------

def initialize_upload(youtube, options):
    """
    Create the YouTube video insert request, run it, and return the
    API response (which contains the new video's "id").
    """

    tags = None

    if options.keywords:
        tags = [
            keyword.strip()
            for keyword in options.keywords.split(",")
            if keyword.strip()
        ]

    body = {
        "snippet": {
            "title": options.title,
            "description": options.description,
            "categoryId": options.category,
        },
        "status": {
            "privacyStatus": options.privacyStatus,
        },
    }

    if tags:
        body["snippet"]["tags"] = tags

    print()
    print("Video information:")
    print("  File:       ", options.file)
    print("  Title:      ", options.title)
    print("  Category:   ", options.category)
    print("  Privacy:    ", options.privacyStatus)

    if options.thumbnail:
        print("  Thumbnail:  ", options.thumbnail)

    if options.playlists:
        print("  Playlists:  ", ", ".join(options.playlists))

    if tags:
        print("  Tags:       ", ", ".join(tags))

    print()

    insert_request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=MediaFileUpload(
            options.file,
            chunksize=1024 * 1024,
            resumable=True
        )
    )

    return resumable_upload(insert_request)


# ---------------------------------------------------------------------------
# Resumable upload with exponential backoff
# ---------------------------------------------------------------------------

def resumable_upload(insert_request):
    """
    Upload a video using resumable upload with exponential backoff.
    Returns the final API response.
    """

    response = None
    error = None
    retry = 0
    last_progress = -1

    print("Uploading file...")

    while response is None:
        try:
            status, response = insert_request.next_chunk()

            if status and status.total_size:
                progress = int(
                    status.resumable_progress * 100 /
                    status.total_size
                )

                if progress != last_progress:
                    print(
                        f"\rUpload progress: {progress}%",
                        end="",
                        flush=True
                    )
                    last_progress = progress

            if response is not None:
                print()

                if "id" in response:
                    print("Video uploaded successfully!")
                    print("Video ID:", response["id"])
                    print(
                        "YouTube URL: "
                        f"https://www.youtube.com/watch?v={response['id']}"
                    )
                else:
                    raise RuntimeError(
                        "The upload failed with an unexpected response: "
                        f"{response}"
                    )

        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES:
                error = (
                    f"A retriable HTTP error {e.resp.status} occurred:\n"
                    f"{e.content}"
                )
            else:
                raise

        except RETRIABLE_EXCEPTIONS as e:
            error = f"A retriable error occurred: {e}"

        if error is not None:
            print()
            print(error)

            retry += 1

            if retry > MAX_RETRIES:
                raise RuntimeError(
                    "No longer attempting to retry."
                )

            max_sleep = 2 ** retry
            sleep_seconds = random.random() * max_sleep

            print(
                f"Sleeping {sleep_seconds:.2f} seconds "
                "before retrying..."
            )

            time.sleep(sleep_seconds)
            error = None

    return response


# ---------------------------------------------------------------------------
# Thumbnail upload
# ---------------------------------------------------------------------------

def set_thumbnail(youtube, video_id, thumbnail_path):
    """
    Set a custom thumbnail on an already-uploaded video.
    Returns True on success.
    """

    if not os.path.isfile(thumbnail_path):
        print(f"Thumbnail not found, skipping: {thumbnail_path}")
        return False

    size = os.path.getsize(thumbnail_path)

    if size > MAX_THUMBNAIL_BYTES:
        print(
            f"Thumbnail is {size / 1024 / 1024:.1f} MB; "
            "YouTube's limit is 2 MB. Skipping."
        )
        return False

    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path),
        ).execute()

        print("Thumbnail set:", thumbnail_path)
        return True

    except HttpError as e:
        print(
            f"Thumbnail upload failed (HTTP {e.resp.status}). "
            "The video itself was uploaded."
        )
        print(e.content)

        if e.resp.status == 403:
            print(
                "403 usually means the channel isn't verified for custom "
                "thumbnails yet (https://www.youtube.com/verify)."
            )

        return False

    except RETRIABLE_EXCEPTIONS as e:
        print(f"Thumbnail upload failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Playlist Management
# ---------------------------------------------------------------------------

def add_to_playlists(youtube, video_id, playlist_ids):
    """
    Add a video to one or more playlists.
    playlist_ids is a list of strings.
    Returns True if all additions succeeded, False otherwise.
    """
    if not playlist_ids:
        return True

    print(f"Adding video to {len(playlist_ids)} playlist(s)...")
    success = True
    for playlist_id in playlist_ids:
        try:
            youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id
                        }
                    }
                }
            ).execute()
            print(f"Added to playlist: {playlist_id}")
        except HttpError as e:
            print(
                f"Failed to add video to playlist {playlist_id} "
                f"(HTTP {e.resp.status}):"
            )
            print(e.content)
            success = False
        except Exception as e:
            print(f"Failed to add video to playlist {playlist_id}: {e}")
            success = False

    return success


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Upload a video to YouTube using the YouTube Data API."
    )

    parser.add_argument(
        "--file",
        required=True,
        help="Video file to upload"
    )

    parser.add_argument(
        "--client-secrets",
        default=CLIENT_SECRETS_FILE,
        help="Google OAuth client secrets JSON file"
    )

    parser.add_argument(
        "--token-file",
        default=TOKEN_FILE,
        help="Path to the saved OAuth token JSON file"
    )

    parser.add_argument(
        "--title",
        default="Test Title",
        help="Video title"
    )

    parser.add_argument(
        "--description",
        default="Test Description",
        help="Video description"
    )

    parser.add_argument(
        "--category",
        default="17",
        help="Numeric YouTube video category. 17 = Sports."
    )

    parser.add_argument(
        "--keywords",
        default="",
        help="Video keywords, comma separated"
    )

    parser.add_argument(
        "--privacyStatus",
        choices=VALID_PRIVACY_STATUSES,
        default="public",
        help="Video privacy status"
    )

    parser.add_argument(
        "--thumbnail",
        default="",
        help="Optional JPG/PNG (max 2 MB) to use as the custom thumbnail"
    )

    parser.add_argument(
        "--playlists",
        nargs='+',
        type=str,
        default=None,
        help="Optional list of YouTube playlist IDs to add the video to (e.g., --playlists PL1 PL2)"
    )

    args = parser.parse_args()

    if not os.path.isfile(args.file):
        raise SystemExit("Please specify a valid video file using --file=FILE")

    youtube = get_authenticated_service(
        args.client_secrets,
        args.token_file,
    )

    try:
        response = initialize_upload(youtube, args)

    except HttpError as e:
        print()
        print("An HTTP error %d occurred:" % e.resp.status)
        print(e.content)
        sys.exit(1)

    except KeyboardInterrupt:
        print()
        print("Upload cancelled by user.")
        sys.exit(1)

    except Exception as e:
        print()
        print("An error occurred:")
        print(e)
        sys.exit(1)

    playlist_success = True
    if args.playlists:
        playlist_success = add_to_playlists(youtube, response["id"], args.playlists)

    thumbnail_success = True
    if args.thumbnail:
        thumbnail_success = set_thumbnail(youtube, response["id"], args.thumbnail)

    if not playlist_success:
        sys.exit(EXIT_PLAYLIST_FAILED)
    if not thumbnail_success:
        sys.exit(EXIT_THUMBNAIL_FAILED)


if __name__ == "__main__":
    main()