"""The search query's terms and the highlighted snippet (``wumpus_archiver.api.search_text``)."""

import pytest

from wumpus_archiver.api.search_text import (
    ELLIPSIS,
    SNIPPET_LEAD,
    SNIPPET_WIDTH,
    highlight,
    search_terms,
)


@pytest.mark.parametrize(
    ("query", "terms"),
    [
        (None, []),
        ("", []),
        ("   ", []),
        ("deploy", ["deploy"]),
        ("deploy  failed", ["deploy", "failed"]),
        ('deploy "build failed"', ["deploy", "build failed"]),
        ('""', []),
        ('"unclosed', ['"unclosed']),
        ("Deploy deploy DEPLOY", ["Deploy"]),
        ("100% a_b", ["100%", "a_b"]),
    ],
)
def test_search_terms(query: str | None, terms: list[str]) -> None:
    assert search_terms(query) == terms


def test_every_occurrence_is_marked_whatever_its_case() -> None:
    assert highlight("Hi hi HI", ["hi"]) == "<mark>Hi</mark> <mark>hi</mark> <mark>HI</mark>"


def test_the_content_is_escaped_and_only_the_marks_are_markup() -> None:
    marked = highlight('<img src=x onerror="alert(1)"> & hi', ["hi"])
    assert marked == "&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; <mark>hi</mark>"


def test_a_term_containing_another_is_marked_whole() -> None:
    assert highlight("deployment", ["deploy", "deployment"]) == "<mark>deployment</mark>"


def test_no_terms_or_no_match_is_the_start_of_the_content() -> None:
    assert highlight("a  b\n c", []) == "a b c"
    assert highlight("plain", ["nothing"]) == "plain"
    long = "word " * 100
    assert highlight(long, []).endswith(ELLIPSIS)
    assert not highlight(long, []).startswith(ELLIPSIS)


def test_a_long_message_is_cut_around_the_first_match_between_words() -> None:
    before = " ".join(f"b{n:02d}" for n in range(40))
    after = " ".join(f"a{n:02d}" for n in range(80))
    snippet = highlight(f"{before} needle {after} needle", ["needle"])
    assert snippet.startswith(ELLIPSIS) and snippet.endswith(ELLIPSIS)
    body = snippet[1:-1]
    assert body.split()[0].startswith("b")  # a whole word, not a cut one
    assert len(body.split(" <mark>")[0]) <= SNIPPET_LEAD
    assert len(body.replace("<mark>", "").replace("</mark>", "")) <= SNIPPET_WIDTH
    assert body.count("<mark>") == 1  # the second needle is past the snippet


def test_a_match_at_the_cut_is_kept_whole() -> None:
    content = "x" * (SNIPPET_WIDTH - 2) + "needle tail"
    snippet = highlight(content, ["x" * 3, "needle"])
    assert "<mark>needle</mark>" in snippet
