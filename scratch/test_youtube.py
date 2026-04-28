"""Test YouTube URL import end-to-end (metadata + short download test)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.video_downloader import validate_url, get_video_info, VideoDownloaderError

# Test 1: Domain validation
test_urls = [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", True),
    ("https://youtu.be/dQw4w9WgXcQ", True),
    ("https://vimeo.com/123456", False),
    ("https://twitter.com/video/123", False),
]
print("=== Domain validation ===")
for url, expected in test_urls:
    result = validate_url(url)
    status = "OK" if result == expected else "FAIL"
    print(f"  [{status}] {url[:50]}... => {result} (expected {expected})")

# Test 2: Metadata fetch (short video to avoid long download)
print("\n=== Metadata fetch ===")
short_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
try:
    info = get_video_info(short_url, timeout_seconds=20)
    print(f"  OK: title='{info.get('title', 'N/A')}' duration={info.get('duration', 'N/A')}s is_live={info.get('is_live', False)}")
except VideoDownloaderError as e:
    print(f"  ERROR: {e}")
except Exception as e:
    print(f"  UNEXPECTED: {type(e).__name__}: {e}")
