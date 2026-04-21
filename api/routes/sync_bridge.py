"""File: api/routes/sync_bridge.py
Purpose: Export endpoints for professional NLE integration (Sync-Bridge).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from typing import Literal

from api.dependencies.auth import AuthenticatedUser, get_current_user
from services.export_engine import get_export_engine
from db.repositories.jobs import get_job

router = APIRouter(prefix="/exports", tags=["exports"])

@router.get("/{job_id}/sync-bridge")
def download_nle_xml(
    job_id: str,
    format: Literal["premiere", "davinci"] = Query("premiere", description="XML target format"),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Downloads a sequence XML for the specified job.
    - format=premiere -> Adobe Premiere Pro / FCP 7 XML (XMEML)
    - format=davinci -> DaVinci Resolve / FCPXML 1.10
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    # Security check: Ensure user owns the job or has workspace access
    # Fix: jobs table has user_id, check it
    if job.user_id != user.user_id:
        # In a full enterprise rollout, we'd check workspace membership here
        raise HTTPException(status_code=403, detail="Unauthorized access to job exports")

    export_engine = get_export_engine()
    xml_content = export_engine.generate_sync_bridge_xml(job_id, format=format)
    
    if not xml_content:
        raise HTTPException(status_code=400, detail="No clips available for this job to export")

    filename = f"clipmind_{job_id[:8]}_{format}.xml"
    media_type = "application/xml"
    
    return Response(
        content=xml_content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
