import os
import requests
import tweepy
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from research_engine import ResearchedContentPackage


def upload_to_youtube(video_path: str, thumb_path: str, pkg: ResearchedContentPackage):
    print("-> YouTube Shorts-এ আপলোড শুরু হচ্ছে...")
    creds = Credentials(
        token=None,
        refresh_token=os.getenv("YT_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("YT_CLIENT_ID"),
        client_secret=os.getenv("YT_CLIENT_SECRET"),
    )
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": pkg.yt_title[:100],
            "description": pkg.yt_description,
            "tags": pkg.yt_tags,
            "categoryId": "27",
            "defaultLanguage": "bn",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    video_id = response.get("id")
    print(f"   YouTube আপলোড সফল! Video ID: {video_id}")

    if video_id and os.path.exists(thumb_path):
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumb_path, mimetype="image/jpeg"),
            ).execute()
            print("   YouTube থাম্বনেইল সেট হয়েছে!")
        except Exception as thumb_err:
            print(f"   থাম্বনেইল সেট করা যায়নি (চ্যানেল ভেরিফিকেশন লাগতে পারে): {thumb_err}")


def upload_to_facebook(video_path: str, pkg: ResearchedContentPackage):
    page_id = os.getenv("FB_PAGE_ID")
    access_token = os.getenv("FB_ACCESS_TOKEN")
    if not page_id or not access_token:
        print("-> Facebook সিক্রেট পাওয়া যায়নি, স্কিপ করা হলো।")
        return

    print("-> Facebook Page-এ আপলোড শুরু হচ্ছে...")
    url = f"https://graph-video.facebook.com/v21.0/{page_id}/videos"
    with open(video_path, "rb") as vid_file:
        files = {"source": ("video_fb.mp4", vid_file, "video/mp4")}
        data = {
            "access_token": access_token,
            "title": pkg.yt_title[:100],
            "description": pkg.fb_caption,
        }
        res = requests.post(url, data=data, files=files, timeout=180).json()

    if "id" in res:
        print(f"   Facebook আপলোড সফল! Post ID: {res['id']}")
    else:
        raise RuntimeError(f"Facebook আপলোড ব্যর্থ: {res}")


def upload_to_x(video_path: str, pkg: ResearchedContentPackage):
    api_key = os.getenv("X_API_KEY")
    api_secret = os.getenv("X_API_SECRET")
    access_token = os.getenv("X_ACCESS_TOKEN")
    access_secret = os.getenv("X_ACCESS_SECRET")
    if not all([api_key, api_secret, access_token, access_secret]):
        print("-> X সিক্রেট পাওয়া যায়নি, স্কিপ করা হলো।")
        return

    print("-> X (Twitter)-এ আপলোড শুরু হচ্ছে...")
    auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
    api_v1 = tweepy.API(auth)
    media = api_v1.media_upload(filename=video_path, media_category="tweet_video")

    client_v2 = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret,
    )
    tweet_text = pkg.x_post[:275]
    res = client_v2.create_tweet(text=tweet_text, media_ids=[media.media_id])
    print(f"   X আপলোড সফল! Tweet ID: {res.data['id']}")


def publish_all(rendered_files: dict, pkg: ResearchedContentPackage):
    errors = []

    try:
        upload_to_youtube(rendered_files["vertical_9x16"], rendered_files["thumb_yt"], pkg)
    except Exception as e:
        print(f"   [YouTube Error]: {e}")
        errors.append(f"YouTube: {e}")

    try:
        upload_to_facebook(rendered_files["portrait_4x5"], pkg)
    except Exception as e:
        print(f"   [Facebook Error]: {e}")
        errors.append(f"Facebook: {e}")

    try:
        upload_to_x(rendered_files["square_1x1"], pkg)
    except Exception as e:
        print(f"   [X Error]: {e}")
        errors.append(f"X: {e}")

    if len(errors) == 3:
        raise RuntimeError(f"সবগুলো প্ল্যাটফর্মে আপলোড ব্যর্থ হয়েছে: {errors}")
