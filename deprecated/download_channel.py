#!/usr/bin/env python3
"""
Robust YouTube channel video downloader with retry logic and error handling.
"""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import yt_dlp


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('download.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class ChannelDownloader:
    """Robust YouTube channel downloader with retry and resume capabilities."""

    def __init__(
        self,
        channel_url: str,
        output_dir: str = "downloads",
        max_retries: int = 3,
        retry_delay: int = 5,
        quality: str = "best",
        archive_file: str = "downloaded.txt",
        subtitles_only: bool = False,
        cookies: str = None,
        cookies_from_browser: str = None
    ):
        self.channel_url = channel_url
        self.output_dir = Path(output_dir)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.quality = quality
        self.archive_file = archive_file
        self.subtitles_only = subtitles_only
        self.cookies = cookies
        self.cookies_from_browser = cookies_from_browser

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_ydl_opts(self) -> dict:
        """Get yt-dlp options with robust settings."""
        return {
            'format': self.quality,
            'outtmpl': str(self.output_dir / '%(uploader)s/%(title)s.%(ext)s'),
            'download_archive': self.archive_file,
            'ignoreerrors': True,  # Continue on download errors
            'no_warnings': False,
            'extract_flat': False,
            'writethumbnail': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['zh-Hans', 'zh-Hant', 'en'],
            'postprocessors': [
                {
                    'key': 'FFmpegEmbedSubtitle',
                    'already_have_subtitle': False
                },
                {
                    'key': 'EmbedThumbnail',
                    'already_have_thumbnail': False
                },
                {
                    'key': 'FFmpegMetadata',
                    'add_metadata': True
                }
            ],
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
            'keepvideo': False,
            'continuedl': True,  # Resume partial downloads
            'noprogress': False,
            'quiet': False,
            'verbose': False,
            'playlistreverse': True,  # Download newest videos first
            'skip_download': self.subtitles_only,  # Skip video download if subtitles_only
            'cookiesfile': self.cookies,  # Use cookies file if provided
            'cookiesfrombrowser': self.cookies_from_browser,  # Use cookies from browser if provided
            'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'referer': 'https://www.youtube.com/',
            'headers': {
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            },
            'sleep_interval': 1,
            'max_sleep_interval': 5,
            'sleep_interval_requests': 5,
            'extractor_args': {
                'youtube': {
                    'player_client': ['web', 'android'],
                    'player_skip': ['webpage', 'configs', 'js'],
                }
            },
        }

    def download_with_retry(self) -> bool:
        """Download channel videos with retry logic."""
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Attempt {attempt}/{self.max_retries}: Starting download from {self.channel_url}")

                ydl_opts = self.get_ydl_opts()

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # Extract channel info first
                    logger.info("Extracting channel information...")
                    info = ydl.extract_info(self.channel_url, download=False)

                    if info:
                        channel_name = info.get('uploader', 'Unknown')
                        video_count = info.get('playlist_count', 0)
                        logger.info(f"Channel: {channel_name}")
                        logger.info(f"Total videos found: {video_count}")

                    # Download all videos
                    logger.info("Starting video downloads...")
                    ydl.download([self.channel_url])

                logger.info("Download completed successfully!")
                return True

            except yt_dlp.utils.DownloadError as e:
                logger.error(f"Download error on attempt {attempt}: {e}")
                if attempt < self.max_retries:
                    logger.info(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Max retries reached. Some videos may not have been downloaded.")
                    return False

            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt}: {e}")
                if attempt < self.max_retries:
                    logger.info(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Max retries reached due to unexpected errors.")
                    return False

        return False

    def get_channel_info(self) -> Optional[dict]:
        """Get channel information without downloading."""
        try:
            ydl_opts = {
                'quiet': True,
                'extract_flat': True,
                'skip_download': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.channel_url, download=False)
                return info

        except Exception as e:
            logger.error(f"Failed to extract channel info: {e}")
            return None


def main():
    parser = argparse.ArgumentParser(
        description='Robust YouTube channel video downloader',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://www.youtube.com/@QuQuUP
  %(prog)s https://www.youtube.com/@QuQuUP -o videos -q "bestvideo[height<=1080]+bestaudio/best"
  %(prog)s https://www.youtube.com/@QuQuUP --info-only
        """
    )

    parser.add_argument(
        'channel_url',
        nargs='?',
        default='https://www.youtube.com/@QuQuUP',
        help='YouTube channel URL (default: https://www.youtube.com/@QuQuUP)'
    )
    parser.add_argument(
        '-o', '--output',
        default='downloads',
        help='Output directory (default: downloads)'
    )
    parser.add_argument(
        '-q', '--quality',
        default='bestvideo+bestaudio/best',
        help='Video quality format (default: bestvideo+bestaudio/best)'
    )
    parser.add_argument(
        '-r', '--retries',
        type=int,
        default=3,
        help='Maximum retry attempts (default: 3)'
    )
    parser.add_argument(
        '-d', '--delay',
        type=int,
        default=5,
        help='Retry delay in seconds (default: 5)'
    )
    parser.add_argument(
        '-a', '--archive',
        default='downloaded.txt',
        help='Archive file to track downloaded videos (default: downloaded.txt)'
    )
    parser.add_argument(
        '--info-only',
        action='store_true',
        help='Only show channel information without downloading'
    )
    parser.add_argument(
        '-s', '--subtitles-only',
        action='store_true',
        help='Only download subtitles (no video)'
    )
    parser.add_argument(
        '-c', '--cookies',
        default=None,
        help='Path to cookies file for authentication (e.g., cookies.txt)'
    )
    parser.add_argument(
        '--cookies-from-browser',
        default=None,
        help='Load cookies from browser (e.g., chrome, firefox, safari, edge)'
    )

    args = parser.parse_args()

    downloader = ChannelDownloader(
        channel_url=args.channel_url,
        output_dir=args.output,
        max_retries=args.retries,
        retry_delay=args.delay,
        quality=args.quality,
        archive_file=args.archive
    )

    if args.info_only:
        logger.info("Fetching channel information...")
        info = downloader.get_channel_info()
        if info:
            print(json.dumps({
                'channel': info.get('uploader', 'Unknown'),
                'channel_id': info.get('channel_id', 'Unknown'),
                'video_count': info.get('playlist_count', 0),
                'url': info.get('webpage_url', args.channel_url)
            }, indent=2, ensure_ascii=False))
        else:
            logger.error("Failed to fetch channel information")
            sys.exit(1)
    else:
        success = downloader.download_with_retry()
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
