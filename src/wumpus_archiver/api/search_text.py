"""The search query's terms, and the highlighted snippet a search result shows.

A query is split into terms on whitespace; a double-quoted run is one term, spaces and
all. A message matches when its content holds every term, case-insensitively (archive
reads do the matching). The highlight is HTML: the message content is escaped first and
only the ``<mark>`` elements around the matches are markup, so content can never inject
any of its own.
"""

import html
import re
from collections.abc import Sequence

_TERM = re.compile(r'"([^"]*)"|(\S+)')

SNIPPET_WIDTH = 200
"""At most how many characters of the content a snippet shows, besides the ellipses."""

SNIPPET_LEAD = 60
"""How many characters before the first match a snippet starts, at most."""

_WORD_SNAP = 15
"""How far a snippet's ends move to fall between words rather than inside one."""

ELLIPSIS = "…"


def search_terms(query: str | None) -> list[str]:
    """The distinct terms of ``query``, in order, compared case-insensitively.

    ``deploy "build failed"`` is two terms, ``deploy`` and ``build failed``. An unclosed
    quote is taken literally, and an empty quoted run is no term.
    """
    if not query:
        return []
    terms: list[str] = []
    seen: set[str] = set()
    for quoted, bare in _TERM.findall(query):
        term = (quoted if quoted else bare).strip()
        if term and term.casefold() not in seen:
            seen.add(term.casefold())
            terms.append(term)
    return terms


def highlight(content: str, terms: Sequence[str]) -> str:
    """The snippet of ``content`` around its first match, every match in ``<mark>``.

    Whitespace runs collapse to one space. The snippet starts up to ``SNIPPET_LEAD``
    characters before the first match and is at most ``SNIPPET_WIDTH`` characters long,
    widened only to keep a match whole; a cut end shows an ellipsis. With no term or
    no match it is the start of the content. Everything but the marks is HTML-escaped.
    """
    text = " ".join(content.split())
    matches: list[tuple[int, int]] = []
    if terms:
        # Longest first, so a term that contains another is marked whole.
        alternatives = sorted({t for t in terms if t}, key=len, reverse=True)
        pattern = re.compile("|".join(re.escape(t) for t in alternatives), re.IGNORECASE)
        matches = [m.span() for m in pattern.finditer(text) if m.end() > m.start()]

    first = matches[0][0] if matches else 0
    start = max(0, first - SNIPPET_LEAD)
    if start > 0:
        space = text.find(" ", start, min(first, start + _WORD_SNAP))
        if space != -1:
            start = space + 1
    end = min(len(text), start + SNIPPET_WIDTH)
    for match_start, match_end in matches:
        if match_start < end < match_end:
            end = match_end
    if end < len(text):
        space = text.rfind(" ", max(start, end - _WORD_SNAP), end)
        if space != -1 and not any(s < space < e or space < s < end for s, e in matches):
            end = space

    pieces: list[str] = [ELLIPSIS] if start > 0 else []
    at = start
    for match_start, match_end in matches:
        if match_end <= start or match_start >= end:
            continue
        pieces.append(html.escape(text[at:match_start]))
        pieces.append(f"<mark>{html.escape(text[match_start:match_end])}</mark>")
        at = match_end
    pieces.append(html.escape(text[at:end]))
    if end < len(text):
        pieces.append(ELLIPSIS)
    return "".join(pieces)
