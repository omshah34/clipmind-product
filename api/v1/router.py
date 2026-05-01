"""File: api/v1/router.py
Purpose: Aggregate all v1 routes into a single router for clean versioning.
"""

from fastapi import APIRouter, Depends
from api.dependencies import get_current_user

from api.routes.jobs import router as jobs_router
from api.routes.upload import router as upload_router
from api.routes.brand_kits import router as brand_kits_router
from api.routes.clip_studio import router as clip_studio_router
from api.routes.campaigns import router as campaigns_router
from api.routes.api_keys import router as api_keys_router
from api.routes.webhooks import router as webhooks_router
from api.routes.integrations import integrations_router
from api.routes.performance import performance_router
from api.routes.preview_studio import router as preview_studio_router
from api.routes.content_dna import router as content_dna_router
from api.routes.clip_sequences import router as clip_sequences_router
from api.routes.social_publish import router as social_publish_router
from api.routes.publish import router as publish_router
from api.routes.workspaces import router as workspaces_router
from api.routes.billing import router as billing_router
from api.routes.preferences import router as preferences_router
from api.routes.websockets import router as websockets_router
from api.routes.autopilot import router as autopilot_router
from api.routes.performance_alerts import router as performance_alerts_router
from api.routes.oauth import router as oauth_router
from api.routes.hooks import router as hooks_router
from api.routes.exports import exports_router

v1_router = APIRouter()

# Protected routes (require auth)
auth_deps = [Depends(get_current_user)]

v1_router.include_router(upload_router, dependencies=auth_deps)
v1_router.include_router(jobs_router, dependencies=auth_deps)
v1_router.include_router(brand_kits_router, dependencies=auth_deps)
v1_router.include_router(clip_studio_router, dependencies=auth_deps)
v1_router.include_router(campaigns_router, dependencies=auth_deps)
v1_router.include_router(api_keys_router, dependencies=auth_deps)
v1_router.include_router(integrations_router, dependencies=auth_deps)
v1_router.include_router(performance_router, dependencies=auth_deps)
v1_router.include_router(preview_studio_router, dependencies=auth_deps)
v1_router.include_router(content_dna_router, dependencies=auth_deps)
v1_router.include_router(clip_sequences_router, dependencies=auth_deps)
v1_router.include_router(social_publish_router, dependencies=auth_deps)
v1_router.include_router(publish_router, dependencies=auth_deps)
v1_router.include_router(workspaces_router, dependencies=auth_deps)
v1_router.include_router(billing_router, prefix="/billing", dependencies=auth_deps)
v1_router.include_router(preferences_router, dependencies=auth_deps)
v1_router.include_router(autopilot_router, dependencies=auth_deps)
v1_router.include_router(performance_alerts_router, dependencies=auth_deps)
v1_router.include_router(hooks_router, dependencies=auth_deps)
v1_router.include_router(exports_router, dependencies=auth_deps)

# Unprotected routes (Webhooks handle their own signature verification, Websockets have tokens in URL/headers)
v1_router.include_router(webhooks_router)
v1_router.include_router(websockets_router)
v1_router.include_router(oauth_router)
