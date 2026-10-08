"""``/api/search`` filters, sort, paging, highlight and facets (#64).

``has``, ``after``/``before`` (days in UTC, ``after`` inclusive, ``before`` exclusive),
``sort`` and ``cursor`` narrow and order the results with the totals agreeing; each
result's ``highlight`` marks every occurrence of the terms in escaped content; and
``facets=true`` counts the matches per channel, author and month in three statements.
"""

from datetime import datetime
from typing import Any

import pytest
from httpx import AsyncClient

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.user import User
from wumpus_archiver.storage.database import Database

GUILD_ID = 1
GENERAL_ID = 10
RANDOM_ID = 11
ALICE_ID = 201
BOB_ID = 202

# (id, channel, author, created_at, content, attachment content types). Every one says
# "deploy"; 705 is the only other message, so a search without q can be told apart.
MESSAGES: list[tuple[int, int, int, datetime, str, list[str]]] = [
    (701, GENERAL_ID, ALICE_ID, datetime(2024, 3, 31, 23, 59), "deploy notes", ["image/png"]),
    (702, GENERAL_ID, BOB_ID, datetime(2024, 4, 1, 0, 0), "deploy video", ["video/mp4"]),
    (
        703,
        RANDOM_ID,
        ALICE_ID,
        datetime(2024, 4, 15, 12, 0),
        "deploy log https://ci.example.test/1",
        [],
    ),
    (
        704,
        GENERAL_ID,
        BOB_ID,
        datetime(2024, 5, 1, 0, 0),
        "deploy <script>alert('x')</script> & Deploy again, deploy!",
        ["application/pdf"],
    ),
    (705, RANDOM_ID, BOB_ID, datetime(2024, 5, 2, 0, 0), "unrelated", []),
]


@pytest.fixture(autouse=True)
async def seeded(database: Database) -> None:
    async with database.session() as session:
        session.add(Guild(id=GUILD_ID, name="Guild"))
        session.add_all(
            [
                Channel(id=GENERAL_ID, guild_id=GUILD_ID, name="general", type=0),
                Channel(id=RANDOM_ID, guild_id=GUILD_ID, name="random", type=0),
                User(id=ALICE_ID, username="alice", global_name="Alice"),
                User(id=BOB_ID, username="bob"),
            ]
        )
        attachment_id = 9000
        for message_id, channel_id, author_id, at, content, types in MESSAGES:
            session.add(
                Message(
                    id=message_id,
                    channel_id=channel_id,
                    author_id=author_id,
                    content=content,
                    clean_content=content,
                    created_at=at,
                    scraped_at=at,
                )
            )
            for content_type in types:
                attachment_id += 1
                session.add(
                    Attachment(
                        id=attachment_id,
                        message_id=message_id,
                        filename=f"{attachment_id}.bin",
                        content_type=content_type,
                        size=1,
                        url=f"https://cdn.example.test/{attachment_id}",
                    )
                )


async def search(client: AsyncClient, **params: Any) -> dict[str, Any]:
    response = await client.get("/api/search", params=params)
    assert response.status_code == 200, response.text
    payload: dict[str, Any] = response.json()
    return payload


def ids(payload: dict[str, Any]) -> list[int]:
    return [int(result["message"]["id"]) for result in payload["results"]]


class TestHas:
    @pytest.mark.parametrize(
        ("has", "expected"),
        [("image", [701]), ("video", [702]), ("file", [704, 702, 701]), ("link", [703])],
    )
    async def test_has_keeps_only_messages_carrying_it(
        self, client: AsyncClient, has: str, expected: list[int]
    ) -> None:
        payload = await search(client, q="deploy", has=has)
        assert ids(payload) == expected
        assert payload["total"] == len(expected)

    async def test_has_image_returns_only_messages_with_image_attachments(
        self, client: AsyncClient
    ) -> None:
        payload = await search(client, has="image")
        assert ids(payload) == [701]
        types = [a["content_type"] for r in payload["results"] for a in r["message"]["attachments"]]
        assert types == ["image/png"]

    async def test_an_unknown_kind_is_a_422(self, client: AsyncClient) -> None:
        response = await client.get("/api/search", params={"q": "deploy", "has": "gif"})
        assert response.status_code == 422


class TestDates:
    @pytest.mark.parametrize(
        ("bounds", "expected"),
        [
            # after is inclusive from 00:00 UTC, before exclusive up to 00:00 UTC.
            ({"after": "2024-04-01"}, [704, 703, 702]),
            ({"before": "2024-04-01"}, [701]),
            ({"after": "2024-04-01", "before": "2024-05-01"}, [703, 702]),
            ({"after": "2024-04-02", "before": "2024-04-16"}, [703]),
            ({"after": "2024-05-01", "before": "2024-04-01"}, []),
        ],
    )
    async def test_dates_bound_the_results_and_the_total(
        self, client: AsyncClient, bounds: dict[str, str], expected: list[int]
    ) -> None:
        payload = await search(client, q="deploy", **bounds)
        assert ids(payload) == expected
        assert payload["total"] == len(expected)
        # A one-result page reads its total from the COUNT, which must agree.
        limited = await search(client, q="deploy", limit=1, **bounds)
        assert limited["total"] == len(expected)
        assert limited["has_more"] == (len(expected) > 1)

    async def test_a_date_alone_needs_no_q(self, client: AsyncClient) -> None:
        payload = await search(client, after="2024-05-01")
        assert ids(payload) == [705, 704]

    async def test_a_malformed_date_is_a_422(self, client: AsyncClient) -> None:
        response = await client.get("/api/search", params={"q": "deploy", "after": "May"})
        assert response.status_code == 422


class TestSortAndPaging:
    async def test_sort_oldest_reverses_the_order(self, client: AsyncClient) -> None:
        assert ids(await search(client, q="deploy")) == [704, 703, 702, 701]
        assert ids(await search(client, q="deploy", sort="oldest")) == [701, 702, 703, 704]

    @pytest.mark.parametrize(
        ("sort", "pages"),
        [("newest", [[704, 703], [702, 701]]), ("oldest", [[701, 702], [703, 704]])],
    )
    async def test_cursor_continues_in_sort_order(
        self, client: AsyncClient, sort: str, pages: list[list[int]]
    ) -> None:
        first = await search(client, q="deploy", sort=sort, limit=2)
        assert (ids(first), first["has_more"], first["total"]) == (pages[0], True, 4)
        cursor = ids(first)[-1]
        second = await search(client, q="deploy", sort=sort, limit=2, cursor=cursor)
        assert (ids(second), second["has_more"], second["total"]) == (pages[1], False, 4)


class TestTerms:
    async def test_every_term_must_occur_in_any_order(self, client: AsyncClient) -> None:
        assert ids(await search(client, q="again deploy")) == [704]
        assert ids(await search(client, q="deploy nowhere")) == []

    async def test_a_quoted_phrase_is_one_term(self, client: AsyncClient) -> None:
        assert ids(await search(client, q='"deploy video"')) == [702]
        assert ids(await search(client, q='"video deploy"')) == []


class TestHighlight:
    async def test_marks_every_occurrence_and_escapes_the_content(
        self, client: AsyncClient
    ) -> None:
        payload = await search(client, q="deploy", has="file", before="2024-05-02")
        highlight = payload["results"][0]["highlight"]
        assert highlight == (
            "<mark>deploy</mark> &lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt; &amp; "
            "<mark>Deploy</mark> again, <mark>deploy</mark>!"
        )
        assert "<script" not in highlight

    async def test_marks_each_term(self, client: AsyncClient) -> None:
        payload = await search(client, q="again DEPLOY")
        assert payload["results"][0]["highlight"].count("<mark>") == 4

    async def test_a_term_that_looks_like_markup_matches_the_escaped_text(
        self, client: AsyncClient
    ) -> None:
        payload = await search(client, q="<script>")
        assert ids(payload) == [704]
        assert "<mark>&lt;script&gt;</mark>" in payload["results"][0]["highlight"]

    async def test_without_q_the_snippet_is_the_escaped_content(self, client: AsyncClient) -> None:
        payload = await search(client, author_id=BOB_ID, has="file", after="2024-05-01")
        assert payload["results"][0]["highlight"] == (
            "deploy &lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt; &amp; Deploy again, deploy!"
        )


class TestFacets:
    async def test_facets_are_left_out_unless_asked_for(self, client: AsyncClient) -> None:
        assert (await search(client, q="deploy"))["facets"] is None

    async def test_facets_count_the_matches_per_channel_author_and_month(
        self, client: AsyncClient
    ) -> None:
        facets = (await search(client, q="deploy", facets="true"))["facets"]
        assert facets["channels"] == [
            {"id": str(GENERAL_ID), "name": "general", "count": 3},
            {"id": str(RANDOM_ID), "name": "random", "count": 1},
        ]
        assert [(a["id"], a["display_name"], a["count"]) for a in facets["authors"]] == [
            (str(ALICE_ID), "Alice", 2),
            (str(BOB_ID), "bob", 2),
        ]
        assert facets["months"] == [
            {"start": "2024-03-01", "count": 1},
            {"start": "2024-04-01", "count": 2},
            {"start": "2024-05-01", "count": 1},
        ]

    async def test_facets_follow_the_filters(self, client: AsyncClient) -> None:
        payload = await search(client, q="deploy", author_id=ALICE_ID, has="link", facets="true")
        facets = payload["facets"]
        assert ids(payload) == [703]
        assert [(c["name"], c["count"]) for c in facets["channels"]] == [("random", 1)]
        assert [(a["username"], a["count"]) for a in facets["authors"]] == [("alice", 1)]
        assert facets["months"] == [{"start": "2024-04-01", "count": 1}]

    async def test_facets_cost_three_statements(
        self, client: AsyncClient, statements: list[str]
    ) -> None:
        await search(client, q="deploy", limit=1)
        without = len(statements)
        statements.clear()
        await search(client, q="deploy", limit=1, facets="true")
        assert len(statements) == without + 3
