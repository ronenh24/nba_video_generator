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
# The batch script treats this as an uploaded video (so it is not uploaded
# twice) but keeps the thumbnail file around.
EXIT_THUMBNAIL_FAILED = 2

# YouTube's limit for custom thumbnails.
MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024


# ---------------------------------------------------------------------------
# YouTube API configuration
# ---------------------------------------------------------------------------

CLIENT_SECRETS_FILE = "client_secrets.json"

# OAuth scope required to upload videos. This scope is also accepted by
# thumbnails.set, so no extra scope (or re-login) is needed for thumbnails.
YOUTUBE_UPLOAD_SCOPE = [
    "https://www.googleapis.com/auth/youtube.upload"
]

YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

# OAuth token will be saved here after the first successful login.
TOKEN_FILE = "youtube-oauth2.json"

MISSING_CLIENT_SECRETS_MESSAGE = """
WARNING: Please configure OAuth 2.0.

This program requires a client_secrets.json file.

Create OAuth 2.0 credentials in the Google Cloud Console:
https://console.cloud.google.com/

Make sure the YouTube Data API v3 is enabled for your project.

Download the OAuth client JSON file and rename it:

    client_secrets.json

Then place it in the same directory as this program.
"""

VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def get_authenticated_service():
    """
    Authenticate the user with Google OAuth 2.0 and return
    an authenticated YouTube API service.
    """

    credentials = None

    # Load an existing token if one exists.
    if os.path.exists(TOKEN_FILE):
        try:
            credentials = Credentials.from_authorized_user_file(
                TOKEN_FILE,
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
        if not os.path.exists(CLIENT_SECRETS_FILE):
            exit(
                MISSING_CLIENT_SECRETS_MESSAGE
                % os.path.abspath(CLIENT_SECRETS_FILE)
            )

        print("Starting Google OAuth authentication...")

        flow = InstalledAppFlow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            YOUTUBE_UPLOAD_SCOPE
        )

        credentials = flow.run_local_server(
            port=0,
            access_type="offline",
            prompt="consent"
        )

        # Save credentials for the next run.
        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(credentials.to_json())

        print("OAuth credentials saved to:", TOKEN_FILE)

    # Build the YouTube API service.
    #
    # google-auth credentials can be passed directly to build().
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

    # Only include tags if tags were provided.
    if tags:
        body["snippet"]["tags"] = tags

    print()
    print("Video information:")
    print("  File:       ", options.file)
    print("  Title:      ", options.title)
    # print("  Description:", options.description)
    print("  Category:   ", options.category)
    print("  Privacy:    ", options.privacyStatus)

    if options.thumbnail:
        print("  Thumbnail:  ", options.thumbnail)

    if tags:
        print("  Tags:       ", ", ".join(tags))

    print()

    # Create the upload request.
    insert_request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,

        # Resumable upload allows interrupted uploads to continue.
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

                # Only print when the percentage changes.
                if progress != last_progress:
                    print(
                        f"\rUpload progress: {progress}%",
                        end="",
                        flush=True
                    )
                    last_progress = progress

            if response is not None:
                print()  # Move to the next line after progress.

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
    Returns True on success. Never raises: the video is already live at
    this point, so a thumbnail problem must not look like a failed upload.
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
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Upload a video to YouTube using the YouTube Data API."
    )

    parser.add_argument(
        "--file",
        required=True,
        help="Video file to upload"
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
        help=(
            "Numeric YouTube video category. "
            "17 = Sports. "
            "See YouTube video categories documentation."
        )
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

    args = parser.parse_args()

    # Verify that the video exists.
    if not os.path.isfile(args.file):
        raise SystemExit(
            "Please specify a valid video file using "
            "--file=FILE"
        )

    # Authenticate.
    youtube = get_authenticated_service()

    try:
        # Upload.
        response = initialize_upload(
            youtube,
            args
        )

    except HttpError as e:

        print()
        print(
            "An HTTP error %d occurred:"
            % e.resp.status
        )
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

    # The video is live. A thumbnail failure gets its own exit code so the
    # caller doesn't treat the whole upload as failed and re-upload it.
    if args.thumbnail:
        if not set_thumbnail(youtube, response["id"], args.thumbnail):
            sys.exit(EXIT_THUMBNAIL_FAILED)


if __name__ == "__main__":
    main()