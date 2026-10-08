"""Smoke tests for every read route over an empty archive, through the shared client.

These are the routes that had no HTTP test before the factory took its collaborators
as arguments. Each one asserts the status and shape a route returns when the archive
holds nothing, which is enough to catch a route that cannot even be served.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.parametrize(
    ("path", "status", "body"),
    [
        ("/api/guilds", 200, []),
        ("/api/guilds/1", 404, {"detail": "Guild not found"}),
        ("/api/guilds/1/channels", 200, {"channels": [], "total": 0}),
        ("/api/guilds/1/stats", 404, {"detail": "Guild not found"}),
        ("/api/guilds/1/users", 200, {"users": [], "total": 0, "has_more": False, "offset": 0}),
        ("/api/users/1", 404, {"detail": "User not found"}),
        ("/api/users/1/profile", 404, {"detail": "User not found"}),
        (
            "/api/search?q=hello",
            200,
            {"results": [], "total": 0, "query": "hello", "has_more": False, "facets": None},
        ),
        (
            "/api/channels/1/messages",
            200,
            {
                "messages": [],
                "total": 0,
                "has_more": False,
                "before_id": None,
                "after_id": None,
                "has_newer": None,
            },
        ),
        ("/api/channels/1/activity", 404, {"detail": "Channel not found"}),
        (
            "/api/channels/1/gallery",
            200,
            {"attachments": [], "total": 0, "has_more": False, "offset": 0},
        ),
        (
            "/api/guilds/1/gallery",
            200,
            {"attachments": [], "total": 0, "has_more": False, "offset": 0},
        ),
        (
            "/api/scrape/status",
            200,
            {"busy": False, "current_job": None, "has_token": False, "control_enabled": False},
        ),
        ("/api/scrape/history", 200, {"jobs": []}),
    ],
)
async def test_route_over_an_empty_archive(
    client: AsyncClient, path: str, status: int, body: object
) -> None:
    response = await client.get(path)
    assert response.status_code == status, response.text
    assert response.json() == body


async def test_timeline_gallery_over_an_empty_archive(client: AsyncClient) -> None:
    response = await client.get("/api/guilds/1/gallery/timeline")
    assert response.status_code == 200, response.text
    assert response.json()["groups"] == []


async def test_download_stats_over_an_empty_archive(client: AsyncClient) -> None:
    response = await client.get("/api/downloads/stats")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total_images"] == 0
    assert payload["attachments_dir"] is None
    assert payload["channels"] == []
