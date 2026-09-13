"""
Re-collects posts (and their top 3 comments) from r/AmITheJerk via the
Arctic Shift Reddit archive API (https://arctic-shift.photon-reddit.com) -
a free, unauthenticated, pushshift-style archive, so no Reddit API
credentials are needed.

Difference from data_collection/scrape_subreddit.py: this version also
drops any post that carries an image/video/gallery attachment, keeping
text-only ("self") posts. A post is skipped (not counted toward the
target) if:
  - it is not a self (text) post, or
  - it is a gallery post, a video, or has post_hint in
    {"image", "hosted:video", "rich:video", "link"}, or has a "preview"
    payload (Reddit generates preview images for link/media posts), or
  - its body is [removed] / [deleted] / empty, or
  - it has no usable top-level comments (all comments are missing,
    [removed], or [deleted]) - i.e. nothing for a judge to react to.

Resumable: if the output CSV already exists, the script reads it, figures
out how many valid posts are already collected and the timestamp of the
oldest one, and continues from there (appending, deduping by post id)
instead of starting over.

Usage:
    python scrape_amithejerk_no_images.py [out_csv] [target_valid_posts]

Output CSV columns:
    title, content, link, subtags, upvotes, comments, comment1, comment2, comment3
"""

import csv
import os
import sys
import time

import requests

BASE = "https://arctic-shift.photon-reddit.com/api"
SUBREDDIT = "AmITheJerk"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "academic-research-script/1.0"})

UNUSABLE_CONTENT = {"[removed]", "[deleted]"}
IMAGE_POST_HINTS = {"image", "hosted:video", "rich:video", "link"}


def is_image_or_media_post(p):
    if not p.get("is_self", True):
        return True
    if p.get("is_gallery"):
        return True
    if p.get("is_video"):
        return True
    if p.get("post_hint") in IMAGE_POST_HINTS:
        return True
    if p.get("preview"):
        return True
    return False


def get_with_retry(url, params, max_retries=8):
    for attempt in range(max_retries):
        try:
            r = SESSION.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            print(f"  request error: {e}, retrying...", file=sys.stderr, flush=True)
            time.sleep(3)
            continue
        if r.status_code == 429:
            wait = int(r.headers.get("X-RateLimit-Reset", 5)) + 1
            print(f"  rate limited, waiting {wait}s...", file=sys.stderr, flush=True)
            time.sleep(wait)
            continue
        if r.status_code != 200:
            print(f"  HTTP {r.status_code} for {url} params={params}", file=sys.stderr, flush=True)
            time.sleep(2)
            continue
        return r.json()
    return None


def fetch_post_page(before):
    params = {"subreddit": SUBREDDIT, "sort": "desc", "limit": 100}
    if before:
        params["before"] = before
    data = get_with_retry(f"{BASE}/posts/search", params)
    if not data or not data.get("data"):
        return []
    return data["data"]


def fetch_top_comments(post_id, n=3):
    data = get_with_retry(
        f"{BASE}/comments/search",
        {"link_id": post_id, "limit": 100, "sort": "desc"},
    )
    if not data or not data.get("data"):
        return []
    comments = data["data"]
    usable = [
        c for c in comments
        if c.get("body") and c["body"] not in ("[removed]", "[deleted]")
    ]
    usable.sort(key=lambda c: c.get("score", 0), reverse=True)
    return [c["body"].replace("\n", " ").strip() for c in usable[:n]]


def post_id_from_link(link):
    parts = link.rstrip("/").split("/")
    idx = parts.index("comments")
    return parts[idx + 1]


def load_existing_state(out_path):
    """Returns (existing_valid_count, seen_ids, resume_before) from an existing CSV."""
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        return 0, set(), None

    seen_ids = set()
    last_link = None
    with open(out_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        count = 0
        for row in reader:
            if not row:
                continue
            count += 1
            link = row[2]
            seen_ids.add(post_id_from_link(link))
            last_link = link

    if last_link is None:
        return 0, set(), None

    last_id = post_id_from_link(last_link)
    data = get_with_retry(f"{BASE}/posts/ids", {"ids": last_id})
    resume_before = None
    if data and data.get("data"):
        resume_before = data["data"][0]["created_utc"]

    return count, seen_ids, resume_before


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "amithejerk_no_images.csv"
    target_valid_posts = int(sys.argv[2]) if len(sys.argv) > 2 else 50000

    existing_count, seen_ids, resume_before = load_existing_state(out_path)

    if existing_count >= target_valid_posts:
        print(f"Already at target: {existing_count} >= {target_valid_posts} in {out_path}. Nothing to do.", flush=True)
        return

    if existing_count > 0:
        print(
            f"Resuming r/{SUBREDDIT}: {existing_count} valid posts already in {out_path}, "
            f"continuing before={resume_before}...",
            flush=True,
        )
    else:
        print(f"Collecting up to {target_valid_posts} valid, text-only (no image/video/gallery) posts from r/{SUBREDDIT}...", flush=True)

    valid_count = existing_count
    raw_seen = 0
    skipped_image = 0
    skipped_removed = 0
    skipped_no_comments = 0
    skipped_dupe = 0
    before = resume_before

    file_mode = "a" if existing_count > 0 else "w"
    with open(out_path, file_mode, newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if existing_count == 0:
            writer.writerow([
                "title", "content", "link", "subtags", "upvotes",
                "comments", "comment1", "comment2", "comment3",
            ])

        while valid_count < target_valid_posts:
            batch = fetch_post_page(before)
            if not batch:
                print(f"No more data returned by API, stopping (r/{SUBREDDIT} history exhausted).", flush=True)
                break
            before = batch[-1]["created_utc"]

            for p in batch:
                if p.get("stickied"):
                    continue
                raw_seen += 1

                post_id = p.get("id", "")
                if post_id in seen_ids:
                    skipped_dupe += 1
                    continue

                if is_image_or_media_post(p):
                    skipped_image += 1
                    continue

                content = (p.get("selftext") or "").strip()
                if content in UNUSABLE_CONTENT or content == "":
                    skipped_removed += 1
                    continue

                num_comments = p.get("num_comments", 0)
                top_comments = fetch_top_comments(post_id, 3) if num_comments > 0 else []
                if not top_comments:
                    skipped_no_comments += 1
                    continue
                while len(top_comments) < 3:
                    top_comments.append("")

                title = (p.get("title") or "").replace("\n", " ").strip()
                content = content.replace("\n", " ").strip()
                link = "https://www.reddit.com" + (p.get("permalink") or "")
                subtags = p.get("link_flair_text") or ""
                upvotes = p.get("score", 0)

                writer.writerow([
                    title, content, link, subtags, upvotes, num_comments,
                    top_comments[0], top_comments[1], top_comments[2],
                ])
                seen_ids.add(post_id)
                valid_count += 1

                if valid_count % 100 == 0:
                    print(
                        f"  [{SUBREDDIT}] valid={valid_count} raw_seen={raw_seen} "
                        f"skipped_image={skipped_image} skipped_removed={skipped_removed} "
                        f"skipped_no_comments={skipped_no_comments} skipped_dupe={skipped_dupe} before={before}",
                        flush=True,
                    )
                    f.flush()

                time.sleep(0.15)

                if valid_count >= target_valid_posts:
                    break

            time.sleep(0.3)

    print(
        f"Done r/{SUBREDDIT}. valid={valid_count} raw_seen={raw_seen} skipped_image={skipped_image} "
        f"skipped_removed={skipped_removed} skipped_no_comments={skipped_no_comments} skipped_dupe={skipped_dupe}",
        flush=True,
    )
    print(f"Wrote CSV to {out_path}", flush=True)


if __name__ == "__main__":
    main()
