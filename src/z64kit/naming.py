"""Turning a long release name into the 8.3 name the unit displays.

The unit lists files by their 8.3 name, so a bad abbreviation is not cosmetic:
it is what the user reads while choosing a game. Plain truncation fails badly,
producing SUPERMAR and LZELDOOT, so this generates several candidate forms per
title and scores them.

The scoring rewards whole words kept, digits kept in their original position,
and the final noun kept intact. It penalises truncation, penalises reducing a
word to a single letter, and penalises dropping a word heavily unless that word
is generic. That last rule is what separates ZELDAOOT, where dropping "Legend"
is free, from CBFD, where dropping "Conker" would destroy the name.

Tuned against 1,414 real release names. Changes here are easy to get subtly
wrong, which is why the validated outputs are pinned as tests.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import PurePath

MAX_LEN = 8
FALLBACK = "GAME"

STOPWORDS = frozenset({"OF", "THE", "AND", "A", "AN", "IN", "ON", "TO", "FOR", "DE", "LA"})
DROPPABLE = frozenset(
    {
        "LEGEND",
        "ADVENTURE",
        "ADVENTURES",
        "SUPER",
        "NEW",
        "TALES",
        "CHRONICLES",
        "RETURN",
        "RETURNS",
        "REVENGE",
        "GREAT",
        "AMAZING",
        "ULTIMATE",
        "OFFICIAL",
        "CLASSIC",
        "WORLD",
    }
)
ARTICLES = ("THE", "A", "AN", "LES", "LE", "LA", "EL", "DIE", "DER", "DAS")

TAG_REGION = (
    ("USA", "U"),
    ("WORLD", "W"),
    ("EUROPE", "E"),
    ("JAPAN", "J"),
    ("GERMANY", "D"),
    ("FRANCE", "F"),
    ("ITALY", "I"),
    ("SPAIN", "S"),
    ("AUSTRALIA", "A"),
    ("BRAZIL", "B"),
    ("KOREA", "K"),
    ("CHINA", "C"),
    ("NETHERLANDS", "N"),
    ("SWEDEN", "W"),
    ("CANADA", "C"),
)

_TAG = re.compile(r"[(\[]([^)\]]*)[)\]]")
_TOKEN = re.compile(r"[A-Z]+|[0-9]+")
_SUBTITLE_SEPARATORS = (" - ", ": ", " -- ")


def deaccent(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


def clean_title(raw: str) -> tuple[str, list[str]]:
    """Strip release tags and normalise, returning the title and the tags found."""
    text = deaccent(PurePath(raw).stem)
    tags = _TAG.findall(text)
    text = _TAG.sub(" ", text).strip(" -_.")
    for article in ARTICLES:
        text = re.sub(rf",\s*{article}$", "", text, flags=re.I)
        text = re.sub(rf",\s*{article}\s+-", " -", text, flags=re.I)
    text = re.sub(rf"^({'|'.join(ARTICLES)})\s+", "", text, flags=re.I)
    text = re.sub(r"[’']s\b", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(), tags


def region_letter(tags: list[str]) -> str:
    upper = " ".join(tags).upper()
    for word, letter in TAG_REGION:
        if word in upper:
            return letter
    return "X"


def _split_subtitle(title: str) -> tuple[str, str]:
    for separator in _SUBTITLE_SEPARATORS:
        if separator in title:
            head, tail = title.split(separator, 1)
            return head.strip(), tail.strip()
    return title.strip(), ""


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.upper().replace("&", " AND "))


def _balanced(tokens: list[str], maxlen: int) -> list[str] | None:
    """Shrink the longest alphabetic token repeatedly until the join fits."""
    alpha = [i for i, t in enumerate(tokens) if not t.isdigit()]
    fixed = sum(len(t) for t in tokens if t.isdigit())
    budget = maxlen - fixed
    if not alpha or budget < len(alpha):
        return None
    lengths = {i: len(tokens[i]) for i in alpha}
    while sum(lengths.values()) > budget:
        longest = max(lengths, key=lambda k: (lengths[k], -k))
        if lengths[longest] <= 1:
            return None  # pragma: no cover -- unreachable, the guard above bounds the loop
        lengths[longest] -= 1
    return [tokens[i][: lengths[i]] if i in lengths else tokens[i] for i in range(len(tokens))]


def _score(
    parts: list[str],
    source: list[str],
    dropped: list[str],
    maxlen: int,
    *,
    is_initials: bool = False,
) -> int | None:
    joined = "".join(parts)
    if not joined or len(joined) > maxlen:
        return None
    if is_initials:
        if len(joined) < 3:
            return None
        truncated, whole, last_whole = 1, 0, 0
    else:
        truncated = sum(1 for a, b in zip(source, parts, strict=False) if len(b) < len(a))
        whole = sum(
            1
            for a, b in zip(source, parts, strict=False)
            if a == b and len(a) > 1 and not a.isdigit()
        )
        last_whole = 0
        for a, b in zip(reversed(source), reversed(parts), strict=False):
            if not a.isdigit():
                last_whole = 2 if a == b else 0
                break

    cost = sum(1 if w in DROPPABLE else 10 for w in dropped)
    score = 2 * whole + last_whole - 3 * truncated - cost

    digits = [t for t in source if t.isdigit()]
    if digits and all(d in joined for d in digits):
        score += 2

    first_alpha = next((w for w in source if not w.isdigit()), "")
    if not dropped and first_alpha and first_alpha not in DROPPABLE:
        score += 3

    score += len(joined)
    score -= 3 * sum(1 for p in parts if len(p) == 1 and not p.isdigit())
    return score


def candidates(title: str, maxlen: int = MAX_LEN) -> list[str]:
    main, subtitle = _split_subtitle(title)
    main_tokens = [w for w in _tokenize(main) if w not in STOPWORDS] or _tokenize(main)
    sub_tokens = _tokenize(subtitle)

    tails: list[list[str]] = []
    if sub_tokens:
        if len("".join(sub_tokens)) + len("".join(main_tokens)) <= maxlen:
            tails.append(list(sub_tokens))
        tails.append(["".join(w[0] for w in sub_tokens)])
    else:
        tails.append([])

    scored: list[tuple[int, int, str]] = []
    alpha_count = max(1, len([w for w in main_tokens if not w.isdigit()]))

    for tail in tails:
        for drop in range(alpha_count):
            kept, dropped, seen = [], [], 0
            for word in main_tokens:
                if not word.isdigit():
                    seen += 1
                    if seen <= drop:
                        dropped.append(word)
                        continue
                kept.append(word)
            if not kept:
                continue
            base = kept + tail

            for generator in ("full", "balanced", "head", "initials"):
                if generator == "full":
                    candidate: list[str] | None = base[:]
                    source, initials = base, False
                elif generator == "balanced":
                    candidate = _balanced(base, maxlen)
                    source, initials = base, False
                elif generator == "head":
                    alpha_at = [i for i, t in enumerate(base) if not t.isdigit()]
                    if len(alpha_at) < 2:
                        continue
                    design = [
                        t if (i == alpha_at[0] or t.isdigit()) else t[0] for i, t in enumerate(base)
                    ]
                    candidate = _balanced(design, maxlen)
                    source, initials = design, False
                else:
                    alpha = [t for t in base if not t.isdigit()]
                    if len(alpha) < 2:
                        continue
                    letters = "".join(t[0] for t in alpha)
                    built: list[str] = []
                    placed = False
                    for token in base:
                        if token.isdigit():
                            built.append(token)
                        elif not placed:
                            built.append(letters)
                            placed = True
                    candidate = built
                    source, initials = base, True

                if not candidate:
                    continue
                parts = candidate
                value = _score(parts, source, dropped, maxlen, is_initials=initials)
                if value is not None:
                    scored.append((value, -len("".join(parts)), "".join(parts)))

    scored.sort(reverse=True)
    ordered: list[str] = []
    for _, _, name in scored:
        if name not in ordered:
            ordered.append(name)
    return ordered


def shorten(title: str, maxlen: int = MAX_LEN) -> str:
    found = candidates(title, maxlen)
    return found[0] if found else FALLBACK


def assign(
    items: list[tuple[str, str]], maxlen: int = MAX_LEN
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Assign a unique 8.3 base name to every item, keyed by the caller's key.

    Collisions are resolved by re-shortening one character tighter and appending
    the region letter, so a title released in several regions reads as
    POKSNAPU and POKSNAPE rather than POKSNAP and POKSNAP~1.
    """
    titles: dict[str, str] = {}
    regions: dict[str, str] = {}
    for key, raw in items:
        title, tags = clean_title(raw)
        titles[key] = title
        regions[key] = region_letter(tags)

    base = {k: shorten(titles[k], maxlen) for k in titles}
    groups: dict[str, list[str]] = {}
    for key, name in base.items():
        groups.setdefault(name, []).append(key)

    used: set[str] = set()
    result: dict[str, str] = {}
    for name, keys in sorted(groups.items()):
        if len(keys) == 1:
            result[keys[0]] = name
            used.add(name)

    for _name, keys in sorted(groups.items()):
        if len(keys) == 1:
            continue
        for key in sorted(keys):
            short = shorten(titles[key], maxlen - 1)
            candidate = (short + regions[key])[:maxlen]
            if candidate not in used:
                result[key] = candidate
                used.add(candidate)
                continue
            for counter in range(1, 1000):
                suffix = f"{regions[key]}{counter}"
                fallback = (short[: maxlen - len(suffix)] + suffix)[:maxlen]
                if fallback not in used:
                    result[key] = fallback
                    used.add(fallback)
                    break
            else:
                raise ValueError(f"cannot make {titles[key]!r} unique")
    return result, titles, regions
