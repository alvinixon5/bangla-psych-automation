import os
import requests
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
            "categoryId": "27",  # Education
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
    print(f"   YouTube Link: https://youtube.com/shorts/{video_id}")

    if thumb_path and os.path.exists(thumb_path):
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumb_path, mimetype="image/jpeg"),
            ).execute()
            print("   YouTube কাস্টম থাম্বনেইল সফলভাবে সেট হয়েছে!")
        except Exception as e:
            print(f"   থাম্বনেইল সেট করা যায়নি (YouTube Studio-তে ফোন ভেরিফিকেশন ও নতুন Refresh Token চেক করুন): {e}")


def upload_to_facebook(video_path: str, pkg: ResearchedContentPackage):
    print("-> Facebook Page-এ আপলোড শুরু হচ্ছে...")
    page_id = os.getenv("FB_PAGE_ID")
    access_token = os.getenv("FB_ACCESS_TOKEN")
    url = f"https://graph-video.facebook.com/v21.0/{page_id}/videos"

    with open(video_path, "rb") as video_file:
        files = {"source": video_file}
        data = {
            "access_token": access_token,
            "title": pkg.yt_title[:100],
            "description": pkg.fb_caption,
        }
        response = requests.post(url, files=files, data=data, timeout=180)
        res = response.json()
        if "id" in res:
            print(f"   Facebook আপলোড সফল! Post ID: {res['id']}")
            print(f"   Facebook Link: https://www.facebook.com/{page_id}/videos/{res['id']}")
        else:
            raise RuntimeError(f"Facebook আপলোড ব্যর্থ: {res}")


def print_x_manual_copy(pkg: ResearchedContentPackage):
    print("\n" + "=" * 55)
    print("📋 X (Twitter)-এ ম্যানুয়াল পোস্টের জন্য রেডিমেড ক্যাপশন ও হ্যাশট্যাগ:")
    print("-" * 55)
    print(pkg.x_post)
    print("=" * 55 + "\n")


def publish_all(rendered_files: dict, pkg: ResearchedContentPackage):
    try:
        upload_to_youtube(rendered_files["vertical_9x16"], rendered_files["thumb_yt"], pkg)
    except Exception as e:
        print(f"   [YouTube Error]: {e}")

    try:
        upload_to_facebook(rendered_files["portrait_4x5"], pkg)
    except Exception as e:
        print(f"   [Facebook Error]: {e}")

    print_x_manual_copy(pkg)
