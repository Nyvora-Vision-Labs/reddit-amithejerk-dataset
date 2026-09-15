"""Strip emoji and invisible junk out of post text.

What goes:
  - HTML entities, unescaped first so the character they name can then be handled on its own terms.
    Reddit text arrives double-escaped, so a single unescape pass leaves entities like "&#x200B;"
    sitting in the text as literal characters; unescaping repeats until the string stops changing;
  - emoji and pictographs, including multi-codepoint sequences (flags, skin tones, ZWJ families),
    replaced by a space so the words either side do not fuse together;
  - zero-width spaces and joiners, bidi marks, byte-order marks, soft hyphens and variation
    selectors, which are invisible but break tokenizing and string matching;
  - the U+FFFD replacement character, left behind wherever an earlier encoding step lost a byte;
  - non-breaking spaces, which become ordinary spaces.

What stays: curly quotes, em and en dashes, ellipses, accented letters and currency symbols. Those
are ordinary English punctuation -- the corpus has 128,000 curly apostrophes, and deleting them would
turn "don't" into "dont".
"""
import html

import regex

# an emoji, optionally with a variation selector, skin-tone modifier, or further ZWJ-joined emoji
EMOJI = regex.compile(
    r"\p{Extended_Pictographic}[︎️]?[\U0001F3FB-\U0001F3FF]?"
    r"(?:‍\p{Extended_Pictographic}[︎️]?[\U0001F3FB-\U0001F3FF]?)*"
)
INVISIBLE = regex.compile(r"[​-‏  ‪-‮⁠-⁤﻿�­︎️]")
WHITESPACE = regex.compile(r"\s+")
TEXT_COLUMNS = ["title", "content"]


def unescape_fully(text, limit=3):
    """html.unescape until the text stops changing, for the double-escaped entities Reddit stores."""
    for _ in range(limit):
        once = html.unescape(text)
        if once == text:
            break
        text = once
    return text


def clean_text(text):
    """Emoji- and junk-free version of one string; anything that is not a string is passed through."""
    if not isinstance(text, str):
        return text
    cleaned = EMOJI.sub(" ", unescape_fully(text))
    cleaned = cleaned.replace(" ", " ")
    cleaned = INVISIBLE.sub("", cleaned)
    return WHITESPACE.sub(" ", cleaned).strip()


def clean_columns(df, columns=TEXT_COLUMNS):
    """Clean the text columns of a frame in place and report how many values changed."""
    changed = {}
    for column in columns:
        if column not in df.columns:
            continue
        before = df[column]
        df[column] = before.map(clean_text)
        changed[column] = int((before.fillna("") != df[column].fillna("")).sum())
    return changed
