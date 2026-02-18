"""API route handlers — split by domain into sub-modules."""

from fastapi import APIRouter

from wumpus_archiver.api.routes.channels import router as channels_router
from wumpus_archiver.api.routes.datasource import router as datasource_router
from wumpus_archiver.api.routes.downloads import router as downloads_router
from wumpus_archiver.api.routes.gallery import router as gallery_router
from wumpus_archiver.api.routes.guilds import router as guilds_router
from wumpus_archiver.api.routes.messages import router as messages_router
from wumpus_archiver.api.routes.scrape import router as scrape_router
from wumpus_archiver.api.routes.search import router as search_router
from wumpus_archiver.api.routes.stats import router as stats_router
from wumpus_archiver.api.routes.transfer import router as transfer_router
from wumpus_archiver.api.routes.users import router as users_router

router = APIRouter()

router.include_router(guilds_router)
router.include_router(channels_router)
router.include_router(gallery_router)
router.include_router(messages_router)
router.include_router(search_router)
router.include_router(stats_router)
router.include_router(users_router)
router.include_router(scrape_router)
router.include_router(downloads_router)
router.include_router(datasource_router)
router.include_router(transfer_router)

__all__ = ["router"]
