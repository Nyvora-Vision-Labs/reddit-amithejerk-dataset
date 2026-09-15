"""Read the community's verdict out of a post's top comments.

    python3 categorization/community_verdict.py    # coverage report over data_files/categorized_posts.csv

r/AmITheJerk votes with YTJ ("you're the jerk") and NTJ ("not the jerk"), but commenters also import
AITA's YTA/NTA/ESH/NAH and often write the verdict out in words instead of tagging it. Each of a
post's three stored comments is scanned for those signals, a comment votes for whichever verdict it
mentions most, and the post takes the majority of its comments -- ties broken by comment1, which is
the highest-scoring comment. Posts whose comments carry no verdict at all are left unlabeled.
"""
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
COMMENT_COLS = ["comment1", "comment2", "comment3"]

# "nah" is deliberately not a bare NTJ signal: in this corpus lowercase "nah" is ordinary speech
# ("nah bro u gotta go"), so it only counts through the spelled-out phrases below. Uppercase NAH is
# the AITA tag and is matched case-sensitively. INFO is a request for detail, not a verdict.
VERDICT_PATTERNS = {
    "YTJ": re.compile(
        r"\b(?:ytj|yta|ytah|yth)\b"
        r"|\byou(?:'| a)?re (?:the|a|an) (?:jerk|asshole|ah)\b"
        r"|\byou are (?:the|a|an) (?:jerk|asshole)\b"
        r"|\byes,? ?(?:the )?jerk\b",
        re.I),
    "NTJ": re.compile(
        r"\b(?:ntj|nta|ntah|nth)\b"
        r"|\bnot (?:the|a|an) (?:jerk|asshole|ah)\b"
        r"|\byou(?:'| a)?re not (?:the|a|an) (?:jerk|asshole)\b"
        r"|\bno(?:t)? (?:the )?jerk\b",
        re.I),
    "ESH": re.compile(r"\besh\b|\beveryone sucks\b", re.I),
    # NAH is matched only in caps: lowercase "nah" is ordinary speech, the tag is not
    "NAH": re.compile(r"\bNAH\b|(?i:\bno assholes here\b)"),
}


def verdict_of_comment(text):
    """The verdict one comment votes for: whichever it signals most often, or None if it signals none
    or splits evenly between two."""
    if not isinstance(text, str) or not text:
        return None
    counts = {name: len(pattern.findall(text)) for name, pattern in VERDICT_PATTERNS.items()}
    counts = {k: v for k, v in counts.items() if v}
    if not counts:
        return None
    top = max(counts.values())
    winners = [k for k, v in counts.items() if v == top]
    return winners[0] if len(winners) == 1 else None


def verdict_of_post(comments):
    """Majority verdict across a post's comments; ties fall to the first (highest-scoring) comment."""
    votes = [verdict_of_comment(c) for c in comments]
    present = [v for v in votes if v]
    if not present:
        return None
    counts = Counter(present)
    top = max(counts.values())
    winners = [v for v in counts if counts[v] == top]
    if len(winners) == 1:
        return winners[0]
    return next((v for v in votes if v in winners), None)  # comment1 breaks the tie


def add_community_prediction(df):
    """Adds the community_prediction column to a frame that has comment1..comment3."""
    df["community_prediction"] = [verdict_of_post([row[c] for c in COMMENT_COLS])
                                  for _, row in df[COMMENT_COLS].iterrows()]
    return df


def report(df):
    verdicts = df["community_prediction"]
    found = verdicts.notna()
    print(f"posts with a community verdict : {found.sum():>6,}  ({found.mean():.1%})")
    print(f"posts with no verdict in any of the 3 comments : {(~found).sum():>6,}  ({(~found).mean():.1%})")
    print(f"total                          : {len(df):>6,}\n")
    counts = verdicts.value_counts()
    for name, n in counts.items():
        print(f"  {name:4} {n:>6,}  {n / found.sum():6.1%} of judged posts")
    if {"YTJ", "NTJ"} <= set(counts.index):
        print(f"\nNTJ:YTJ ratio among the two main verdicts: "
              f"{counts['NTJ'] / counts['YTJ']:.1f} to 1 -- posters are told they are not the jerk "
              f"{counts['NTJ'] / (counts['NTJ'] + counts['YTJ']):.0%} of the time")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data_files" / "categorized_posts.csv"
    data = pd.read_csv(path)
    if "community_prediction" not in data.columns:
        data = add_community_prediction(data)
    report(data)
