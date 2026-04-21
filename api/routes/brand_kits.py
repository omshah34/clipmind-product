"""File: api/routes/brand_kits.py
Purpose: Implements brand kit CRUD endpoints:
         - POST /brand-kits — Create
         - GET /brand-kits — List user's brand kits
         - GET /brand-kits/{id} — Get single brand kit
         - PATCH /brand-kits/{id} — Update
         - DELETE /brand-kits/{id} — Delete
         - GET /brand-kits/presets — Get preset templates
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Header, Query
from fastapi.responses import JSONResponse

from api.models.brand_kit import (
    BrandKitCreate,
    BrandKitUpdate,
    BrandKitResponse,
    BrandKitListResponse,
    BRAND_KIT_PRESETS,
)
from api.models.job import ErrorResponse
from db.repositories.brand_kits import (
    create_brand_kit,
    get_brand_kit,
    get_user_brand_kits,
    update_brand_kit,
    delete_brand_kit,
)

router = APIRouter(prefix="/brand-kits", tags=["brand-kits"])


def _get_user_id_from_headers(authorization: str | None) -> UUID:
    """Extract user_id from Authorization header.
    
    In production, this would validate a JWT token or session.
    For MVP, we accept a header like: Authorization: Bearer {user_id}
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    try:
        scheme, credentials = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            raise ValueError("Invalid scheme")
        user_id = UUID(credentials)
        return user_id
    except (ValueError, IndexError):
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")


def error_response(error: str, message: str, status_code: int) -> JSONResponse:
    payload = ErrorResponse(error=error, message=message)
    return JSONResponse(status_code=status_code, content=payload.model_dump())


@router.post("", response_model=BrandKitResponse, status_code=201)
def create_brand_kit_endpoint(
    payload: BrandKitCreate,
    authorization: str | None = Header(None),
) -> BrandKitResponse:
    """Create a new brand kit for the authenticated user."""
    try:
        user_id = _get_user_id_from_headers(authorization)
    except HTTPException as e:
        return error_response("auth_error", str(e.detail), e.status_code)

    try:
        brand_kit = create_brand_kit(
            user_id=user_id,
            name=payload.name,
            font_name=payload.font_name,
            font_size=payload.font_size,
            bold=payload.bold,
            alignment=payload.alignment,
            primary_colour=payload.primary_colour,
            outline_colour=payload.outline_colour,
            outline=payload.outline,
            watermark_url=payload.watermark_url,
            intro_clip_url=payload.intro_clip_url,
            outro_clip_url=payload.outro_clip_url,
            is_default=payload.is_default,
        )
        return BrandKitResponse(brand_kit=brand_kit)
    except Exception as e:
        return error_response("creation_error", str(e), 500)


@router.get("", response_model=BrandKitListResponse, status_code=200)
def list_brand_kits(
    authorization: str | None = Header(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> BrandKitListResponse:
    """List all brand kits for the authenticated user."""
    try:
        user_id = _get_user_id_from_headers(authorization)
    except HTTPException as e:
        return error_response("auth_error", str(e.detail), e.status_code)

    try:
        brand_kits = get_user_brand_kits(user_id)
        # Simple pagination
        paginated = brand_kits[offset : offset + limit]
        return BrandKitListResponse(brand_kits=paginated, total=len(brand_kits))
    except Exception as e:
        return error_response("fetch_error", str(e), 500)


@router.get("/{brand_kit_id}", response_model=BrandKitResponse, status_code=200)
def get_brand_kit_endpoint(
    brand_kit_id: UUID,
    authorization: str | None = Header(None),
) -> BrandKitResponse:
    """Get a specific brand kit by ID."""
    try:
        user_id = _get_user_id_from_headers(authorization)
    except HTTPException as e:
        return error_response("auth_error", str(e.detail), e.status_code)

    try:
        brand_kit = get_brand_kit(brand_kit_id)
        if not brand_kit:
            return error_response("not_found", "Brand kit not found", 404)
        
        # Verify user owns this brand kit
        if brand_kit.user_id != user_id:
            return error_response("forbidden", "You do not own this brand kit", 403)
        
        return BrandKitResponse(brand_kit=brand_kit)
    except Exception as e:
        return error_response("fetch_error", str(e), 500)


@router.patch("/{brand_kit_id}", response_model=BrandKitResponse, status_code=200)
def update_brand_kit_endpoint(
    brand_kit_id: UUID,
    payload: BrandKitUpdate,
    authorization: str | None = Header(None),
) -> BrandKitResponse:
    """Update a brand kit. Only provided fields are updated."""
    try:
        user_id = _get_user_id_from_headers(authorization)
    except HTTPException as e:
        return error_response("auth_error", str(e.detail), e.status_code)

    try:
        brand_kit = get_brand_kit(brand_kit_id)
        if not brand_kit:
            return error_response("not_found", "Brand kit not found", 404)
        
        if brand_kit.user_id != user_id:
            return error_response("forbidden", "You do not own this brand kit", 403)
        
        # Build update dict with only non-None values
        update_fields = {k: v for k, v in payload.model_dump().items() if v is not None}
        
        updated_kit = update_brand_kit(brand_kit_id, **update_fields)
        return BrandKitResponse(brand_kit=updated_kit)
    except ValueError as e:
        return error_response("update_error", str(e), 400)
    except Exception as e:
        return error_response("update_error", str(e), 500)


@router.delete("/{brand_kit_id}", status_code=200)
def delete_brand_kit_endpoint(
    brand_kit_id: UUID,
    authorization: str | None = Header(None),
) -> dict:
    """Delete a brand kit."""
    try:
        user_id = _get_user_id_from_headers(authorization)
    except HTTPException as e:
        return error_response("auth_error", str(e.detail), e.status_code)

    try:
        brand_kit = get_brand_kit(brand_kit_id)
        if not brand_kit:
            return error_response("not_found", "Brand kit not found", 404)
        
        if brand_kit.user_id != user_id:
            return error_response("forbidden", "You do not own this brand kit", 403)
        
        delete_brand_kit(brand_kit_id)
        return {"deleted": True, "id": str(brand_kit_id)}
    except Exception as e:
        return error_response("delete_error", str(e), 500)


@router.get("/presets/list", status_code=200)
def get_brand_kit_presets():
    """Get available brand kit presets."""
    return {
        "presets": [
            {
                "id": preset_id,
                "name": preset.name,
                "description": preset.description,
                "preview": {
                    "font_name": preset.font_name,
                    "font_size": preset.font_size,
                    "bold": preset.bold,
                    "primary_colour": preset.primary_colour,
                    "outline_colour": preset.outline_colour,
                },
            }
            for preset_id, preset in BRAND_KIT_PRESETS.items()
        ]
    }


@router.post("/presets/{preset_id}/apply", response_model=BrandKitResponse, status_code=201)
def apply_preset(
    preset_id: str,
    payload_name: str = Query("Brand Kit from Preset"),
    authorization: str | None = Header(None),
) -> BrandKitResponse:
    """Create a new brand kit from a preset."""
    if preset_id not in BRAND_KIT_PRESETS:
        return error_response("invalid_preset", f"Preset '{preset_id}' not found", 404)
    
    try:
        user_id = _get_user_id_from_headers(authorization)
    except HTTPException as e:
        return error_response("auth_error", str(e.detail), e.status_code)

    try:
        preset = BRAND_KIT_PRESETS[preset_id]
        brand_kit = create_brand_kit(
            user_id=user_id,
            name=payload_name,
            font_name=preset.font_name,
            font_size=preset.font_size,
            bold=preset.bold,
            alignment=preset.alignment,
            primary_colour=preset.primary_colour,
            outline_colour=preset.outline_colour,
            outline=preset.outline,
        )
        return BrandKitResponse(brand_kit=brand_kit)
    except Exception as e:
        return error_response("creation_error", str(e), 500)
