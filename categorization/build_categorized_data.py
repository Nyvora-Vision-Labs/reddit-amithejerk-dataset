"""Combine the three judges into one label per post, and write the final dataset.

    python3 categorization/build_categorized_data.py

Reads categorization/post_categories_{claude,openai,deepseek}.csv and keeps a post when at least two
of the three models chose the same primary category; a post is dropped when the judges split three
ways, or when fewer than two of them managed to label it at all. The secondary category and the
confidence are voted on the same way, among the judges that backed the winning category. Reposts (identical title and body) and posts all judges
called "none" are dropped, so every story appears exactly once under one of the ten categories.

Writes two files into data_files/: categorized_posts.csv (every post that survived the judges) and
verdict_categorized_posts.csv (those of them whose commenters actually rendered a verdict).
"""
from collections import Counter
from pathlib import Path

import pandas as pd

from categorize_posts import JUDGES
from community_verdict import add_community_prediction

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data_files"
OUT_PATH = DATA_DIR / "categorized_posts.csv"
VERDICT_PATH = DATA_DIR / "verdict_categorized_posts.csv"
LABEL_COLS = ["category", "secondary_category", "confidence"]
MIN_VOTES = 2  # a majority of three

# Upvotes span 0 to 23,146 with a median of 7, so raw scores are not comparable across posts.
# These log-scaled bands each hold 4-27% of the corpus and read as levels of traction.
UPVOTE_BINS = [-1, 0, 4, 19, 99, 999, float("inf")]
UPVOTE_LABELS = ["0", "1-4", "5-19", "20-99", "100-999", "1000+"]


def upvote_ordinal(upvotes):
    """Bin raw scores into ordered traction bands (an ordered categorical, so comparisons work)."""
    return pd.cut(upvotes, bins=UPVOTE_BINS, labels=UPVOTE_LABELS, ordered=True)


def vote(values):
    """Most common value, ties broken by judge order (claude, openai, deepseek). Returns (value, count)."""
    counts = Counter(v for v in values if pd.notna(v))
    if not counts:
        return None, 0
    top = counts.most_common(1)[0][1]
    winner = next(v for v in values if pd.notna(v) and counts[v] == top)
    return winner, top


def main():
    source = pd.read_csv(DATA_DIR / "scraped_posts.csv")
    source["row_id"] = source.index

    votes = None
    for judge in JUDGES:
        path = ROOT / "categorization" / f"post_categories_{judge}.csv"
        if not path.exists():
            raise SystemExit(f"{path} is missing -- run: python3 categorization/categorize_posts.py run {judge}")
        one = (pd.read_csv(path)[["row_id", *LABEL_COLS]]
               .rename(columns={c: f"{c}_{judge}" for c in LABEL_COLS}))
        votes = one if votes is None else votes.merge(one, on="row_id", validate="one_to_one")

    judges = list(JUDGES)
    cat_cols = [f"category_{j}" for j in judges]
    # a post needs two judges to agree, not three to have answered: if one judge errored on a post
    # and the other two agree, that is still a majority of the panel
    complete = votes[votes[cat_cols].notna().sum(axis=1) >= MIN_VOTES]
    print(f"{len(votes):,} posts, {votes[cat_cols].notna().all(axis=1).sum():,} labeled by all "
          f"{len(judges)} judges, {len(complete):,} with at least {MIN_VOTES} labels")

    decided = complete[cat_cols].apply(lambda r: vote(list(r)), axis=1)
    complete = complete.assign(category=[c for c, _ in decided], agreement=[n for _, n in decided])
    print("\nhow many judges agreed on the primary category:")
    print(complete["agreement"].value_counts().sort_index(ascending=False)
          .rename(lambda n: f"{n} of {len(judges)}").to_string())

    print("\npairwise agreement on the primary category:")
    for i, a in enumerate(judges):
        for b in judges[i + 1:]:
            same = (complete[f"category_{a}"] == complete[f"category_{b}"]).mean()
            print(f"  {a:9} vs {b:9}: {same:.1%}")

    kept = complete[(complete["agreement"] >= MIN_VOTES) & (complete["category"] != "none")].copy()
    print(f"\ndropped {(complete['agreement'] < MIN_VOTES).sum():,} three-way splits and "
          f"{((complete['agreement'] >= MIN_VOTES) & (complete['category'] == 'none')).sum():,} "
          f'posts the majority called "none"')

    # the secondary category and confidence are voted among the judges that backed the winning category
    for col in ("secondary_category", "confidence"):
        picks = []
        for row in kept.itertuples():
            backers = [j for j in judges if getattr(row, f"category_{j}") == row.category]
            picks.append(vote([getattr(row, f"{col}_{j}") for j in backers])[0])
        kept[col] = picks

    print("\nmost common disagreements (majority category -> the outvoted judge's pick):")
    clashes = Counter()
    for row in kept.itertuples():
        for j in judges:
            other = getattr(row, f"category_{j}")
            if other != row.category and pd.notna(other):
                clashes[(row.category, other)] += 1
    for (won, lost), n in clashes.most_common(10):
        print(f"  {won:22} -> {lost:22} {n}")

    out = source.merge(kept[["row_id", "category", *LABEL_COLS[1:]]], on="row_id", how="inner")
    reposts = out.duplicated(subset=["title", "content"], keep="first")
    print(f"\ndropping {reposts.sum()} repost(s) -- same title and body as an earlier post, kept once")
    out = out.loc[~reposts]
    out["upvote_ordinal"] = upvote_ordinal(out["upvotes"])
    out = add_community_prediction(out)
    out = out[["row_id", "title", "content", "link", "upvotes", "upvote_ordinal", "comments",
               "comment1", "comment2", "comment3", "community_prediction",
               "category", "secondary_category", "confidence"]]
    out.to_csv(OUT_PATH, index=False)

    # the analysis set: only posts whose commenters actually rendered a verdict
    judged = out[out["community_prediction"].notna()]
    judged.to_csv(VERDICT_PATH, index=False)

    print(f"\nWrote {OUT_PATH} -- {len(out):,} posts ({len(out) / len(source):.1%} of the {len(source):,} scraped)")
    print(f"Wrote {VERDICT_PATH} -- {len(judged):,} of those carry a community verdict")
    print(out["category"].value_counts().to_string())
    print("\nupvote_ordinal:")
    print(out["upvote_ordinal"].value_counts().sort_index().to_string())
    found = out["community_prediction"].notna()
    print(f"\ncommunity_prediction: {found.sum():,} posts carry a verdict, {(~found).sum():,} do not")
    print(out["community_prediction"].value_counts().to_string())


if __name__ == "__main__":
    main()
