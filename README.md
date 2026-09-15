# r/AmITheJerk (text-only): 23,170 posts + top comments

The complete scrapeable history of **r/AmITheJerk**, filtered down to text-only ("self") posts, with each post's top 3 highest-scoring top-level comments attached.

## Description

r/AmITheJerk runs the same "crowd renders a verdict" ritual as r/AmItheAsshole, but with its own vocabulary: commenters answer **YTJ** (You're The Jerk) or **NTJ** (Not The Jerk) instead of AITA's YTA/NTA. This file is part of a larger project asking **"does the question do the judging?"** — whether the specific verdict wording a community uses (asshole vs. jerk vs. wrong vs. overreacting, etc.) shifts the judgment reached on an otherwise-comparable situation — so it's built to be directly comparable to sibling dumps of AITA, AmIWrong, AmIOverreacting, and other "judge me" subreddits collected the same way.

This particular file is the **image-free variant**: unlike a plain recent-sample scrape of the subreddit, every post here was checked and kept only if it was a text ("self") post with no image, gallery, or video attachment. That makes it suitable for pure-text NLP work (verdict classification, moral-language modeling, LLM-as-judge studies) without needing to separately filter out posts whose actual content lives in an attached picture the model can't see. It is also the subreddit's **entire history of qualifying posts**, not a capped sample — collection stopped only because the archive API had no more pages to return, not because a row-count target was hit.

## File details

| Property | Value |
|---|---|
| File | `data_files/scraped_posts.csv` |
| Subreddit | r/AmITheJerk |
| Rows | 23,170 |
| Coverage | Entire scrapeable history of the subreddit (paged newest → oldest until the archive returned no further pages), not a sample |
| Post filter | Text-only posts only — image, gallery, and video posts are excluded (see Collection methodology) |
| Encoding | UTF-8 CSV, comma-delimited, header row included |
| Size on disk | ~62.9 MB |
| Companion files | `scraping/scrape_amithejerk.py` (the collection script) and `scraping/scrape.log` (a full run log with running skip/valid counters) |

Every retained row has a non-empty post body and at least one usable (non-removed, non-deleted) top-level comment; posts failing either check were dropped during collection rather than kept as nulls.

## Column descriptions

| Column | Type | Description |
|---|---|---|
| `title` | string | The Reddit post title, exactly as authored by the original poster. |
| `content` | string | The full body text of the post (the OP's account of the situation). Internal line breaks are collapsed to single spaces. Never empty — posts with a `[removed]`, `[deleted]`, or blank body were excluded during collection, not kept as empty rows. |
| `link` | string | Canonical URL of the post on reddit.com, e.g. `https://www.reddit.com/r/AmITheJerk/comments/<post_id>/...`. The `<post_id>` path segment is a unique key for the row. |
| `subtags` | string | The post's flair (Reddit's `link_flair_text`). **Empty for all 23,170 rows in this file** — r/AmITheJerk posts in this archive carry no flair text, so this column is present for schema-compatibility with sibling files but carries no signal here. |
| `upvotes` | integer | The post's Reddit score (upvotes minus downvotes) at collection time. Ranges 0–23,146 across this file; median 7. |
| `comments` | integer | Total number of comments Reddit reported for the post at collection time (can exceed 3 even though only the top 3 are kept). Ranges 1–8,405; median 16. |
| `comment1` | string | The single highest-scoring top-level comment on the post, by Reddit score. Never empty — every retained post has at least one usable comment. |
| `comment2` | string | The second-highest-scoring top-level comment. Empty in 1,218 rows (posts with fewer than 2 usable comments). |
| `comment3` | string | The third-highest-scoring top-level comment. Empty in 2,562 rows (posts with fewer than 3 usable comments). |

`comment1`–`comment3` are drawn from top-level comments only (no replies-to-comments), filtered to non-removed/non-deleted, sorted by score descending. In a handful of low-engagement posts `comment1` is the subreddit's automated submission-guidelines bot reply rather than an actual verdict — a minor, low-frequency artifact (roughly 1 in 2,000 rows) worth accounting for if you're mining these columns for YTJ/NTJ verdicts.

## Collection methodology

Collected with `scraping/scrape_amithejerk.py` against the [Arctic Shift Reddit archive API](https://arctic-shift.photon-reddit.com) — a free, unauthenticated, Pushshift-style mirror of Reddit, so no Reddit API credentials were required. Posts were paged newest-first via `/posts/search`. A post was **skipped** (not written to the CSV) if:

- it was not a self (text) post — i.e. it was a gallery post, a video, or had `post_hint` in `{"image", "hosted:video", "rich:video", "link"}`, or carried a Reddit-generated preview payload, or
- its body was `[removed]`, `[deleted]`, or empty, or
- it had no usable top-level comments (all missing, `[removed]`, or `[deleted]`).

For each retained post, top-level comments were fetched via `/comments/search`, filtered to non-removed/non-deleted, sorted by score descending, and the top 3 kept. The scraper is resumable and dedupes by Reddit post ID.

Final run totals (from `scraping/scrape.log`): 32,433 raw posts seen → 5,691 skipped as image/video/gallery, 1,996 skipped as removed/deleted/empty, 1,576 skipped for having no usable comments → **23,170 valid posts written**, at which point the archive API returned no further history for the subreddit.

**No usernames, author IDs, or other author-identifying fields were collected or are present in this file.**

## Relationship to the wider corpus

This project also includes `data_collection/amithejerk.csv` — a separate, 20,000-row *recent-most sample* of the same subreddit that does **not** filter out image/video/gallery posts. Use that file if you want a same-schema, same-size sample directly comparable to the other 10 subreddits in the wider "judge me" corpus (r/AmItheAsshole, r/AITAH, r/AmIWrong, r/relationship_advice, etc.). Use *this* file (`data_files/scraped_posts.csv`) if you specifically need r/AmITheJerk's full history, or need text-only posts because your pipeline can't make use of image content.

## Known limitations / caveats

- `subtags` carries no information for this file — it is empty in every row.
- No pre-extracted verdict (YTJ vs. NTJ) column is included; extracting one requires parsing `comment1`–`comment3` with a rule-based or model-based classifier. Roughly 39% of rows contain an explicit "YTJ"/"NTJ" token somewhere in their top 3 comments; the rest express a verdict in prose without the acronym.
- Only the top 3 top-level comments by score are included, not full comment threads or replies-to-comments.
- `upvotes` and `comments` reflect Reddit's counts at scrape time, not a post's final/asymptotic score.
- Scraped exclusively from already-public Reddit posts/comments; no private, quarantined, or removed content is included by construction.

## License / usage

The post and comment text was authored by individual Reddit users and is not released into the public domain by Reddit or by this dataset — original authors retain rights to their own words. Shared for **non-commercial research and educational use** (NLP research, moral-judgment / LLM-as-judge studies, content-moderation research, etc.), consistent with data obtained through Reddit's public API surface. If you plan to publish text excerpts or redistribute derived data, review Reddit's User Agreement/Content Policy and your institution's human-subjects guidance for social-media text.

## Acknowledgements

Collected via the [Arctic Shift](https://arctic-shift.photon-reddit.com) Reddit archive project. All post and comment text remains the property of its original Reddit authors.
