"""Collect r/AmITheJerk text posts and their top 3 comments from Reddit's official API.

Usage:
    python scraping/scrape_amithejerk.py [out_csv]

Credentials come from the environment or from .env in the project root. Register a script-type app
at https://www.reddit.com/prefs/apps to get them:
    REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT

Only text ("self") posts are kept, and only those a reader could actually judge. A submission is
skipped -- not written, not counted -- when:
  - it is not a self post, or it carries an image, gallery, video or link preview;
  - its body is [removed], [deleted] or empty;
  - it has no usable top-level comment left after removed/deleted ones are dropped.

For each kept post the top-level comments are sorted by score and the best three are stored, which is
what gives every row a verdict to read later.

Resumable: if the output CSV already exists the script reads it, skips the submission IDs already
collected, and appends.
"""
import csv
import os
import re
import sys
import time
from pathlib import Path

import praw
import prawcore

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
SUBREDDIT = "AmITheJerk"
DEFAULT_OUT = ROOT / "data_files" / "scraped_posts.csv"
COMMENTS_KEPT = 3
FIELDS = ["id", "title", "content", "link", "upvotes", "comments", "comment1", "comment2", "comment3"]

DEAD_BODY = {"[removed]", "[deleted]", ""}
MEDIA_HINTS = {"image", "hosted:video", "rich:video", "link"}
WHITESPACE = re.compile(r"\s+")


def load_env():
    """Read .env without overriding variables already set in the environment."""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, _, value = line.partition("=")
            os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def reddit_client():
    load_env()
    missing = [k for k in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")
               if not os.environ.get(k)]
    if missing:
        sys.exit(f"Missing Reddit credentials: {', '.join(missing)}. Set them in the environment or {ENV_PATH}")
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ["REDDIT_USER_AGENT"],
        # PRAW sleeps rather than raising when the API's rate limit is reached
        ratelimit_seconds=300,
    )


def clean(text):
    """Collapse internal whitespace so one post stays on one CSV row."""
    return WHITESPACE.sub(" ", (text or "").strip())


def has_media(submission):
    """True when the post's real content is a picture, video or link rather than its text."""
    return (getattr(submission, "is_gallery", False)
            or getattr(submission, "is_video", False)
            or getattr(submission, "post_hint", None) in MEDIA_HINTS
            or bool(getattr(submission, "preview", None)))


def top_comments(submission, n=COMMENTS_KEPT):
    """The n highest-scoring usable top-level comments, or [] when the post has none."""
    submission.comments.replace_more(limit=0)  # drop "load more comments" placeholders
    usable = [c for c in submission.comments
              if clean(getattr(c, "body", "")).lower() not in DEAD_BODY and getattr(c, "author", None)]
    usable.sort(key=lambda c: c.score, reverse=True)
    return [clean(c.body) for c in usable[:n]]


def already_collected(path):
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {row["id"] for row in csv.DictReader(f)}


def main(out_path=DEFAULT_OUT):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    seen = already_collected(out_path)
    reddit = reddit_client()
    subreddit = reddit.subreddit(SUBREDDIT)

    counts = {"raw": 0, "media": 0, "dead_body": 0, "no_comments": 0, "dupe": 0, "valid": len(seen)}
    start = time.time()
    is_new_file = not out_path.exists()
    with open(out_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new_file:
            writer.writeheader()

        # listing the subreddit newest-first; PRAW pages until the listing is exhausted
        for submission in subreddit.new(limit=None):
            counts["raw"] += 1
            if submission.id in seen:
                counts["dupe"] += 1
                continue
            if not submission.is_self or has_media(submission):
                counts["media"] += 1
                continue
            body = clean(submission.selftext)
            if body.lower() in DEAD_BODY:
                counts["dead_body"] += 1
                continue
            try:
                comments = top_comments(submission)
            except prawcore.exceptions.PrawcoreException as e:
                print(f"  comment fetch failed for {submission.id}: {e}", file=sys.stderr, flush=True)
                continue
            if not comments:
                counts["no_comments"] += 1
                continue

            comments += [""] * (COMMENTS_KEPT - len(comments))
            writer.writerow({
                "id": submission.id,
                "title": clean(submission.title),
                "content": body,
                "link": f"https://www.reddit.com{submission.permalink}",
                "upvotes": submission.score,
                "comments": submission.num_comments,
                "comment1": comments[0], "comment2": comments[1], "comment3": comments[2],
            })
            f.flush()
            seen.add(submission.id)
            counts["valid"] += 1
            if counts["valid"] % 100 == 0:
                print(f"  [{SUBREDDIT}] " + " ".join(f"{k}={v}" for k, v in counts.items())
                      + f" ({(time.time() - start) / 60:.0f} min)", flush=True)

    print(f"Done r/{SUBREDDIT}. " + " ".join(f"{k}={v}" for k, v in counts.items()))
    print(f"Wrote CSV to {out_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT)
