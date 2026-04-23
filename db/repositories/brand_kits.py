"""Brand Kit repository functions."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text

from api.models.brand_kit import BrandKitRecord
from db.connection import engine


def _row_to_brand_kit_record(row: Any) -> BrandKitRecord:
    return BrandKitRecord.model_validate(dict(row._mapping))


def create_brand_kit(
    *,
    user_id: UUID | str,
    name: str,
    font_name: str = "Arial",
    font_size: int = 22,
    bold: bool = True,
    alignment: int = 2,
    primary_colour: str = "&H00FFFFFF",
    outline_colour: str = "&H00000000",
    outline: int = 2,
    watermark_url: str | None = None,
    intro_clip_url: str | None = None,
    outro_clip_url: str | None = None,
    vocabulary_hints: list[str] | None = None,
    is_default: bool = False,
) -> BrandKitRecord:
    """Create a new brand kit for a user."""
    query = text(
        """
        INSERT INTO brand_kits (
            user_id, name, font_name, font_size, bold, alignment,
            primary_colour, outline_colour, outline,
            watermark_url, intro_clip_url, outro_clip_url,
            vocabulary_hints, is_default
        )
        VALUES (
            :user_id, :name, :font_name, :font_size, :bold, :alignment,
            :primary_colour, :outline_colour, :outline,
            :watermark_url, :intro_clip_url, :outro_clip_url,
            :vocabulary_hints, :is_default
        )
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "user_id": str(user_id),
                "name": name,
                "font_name": font_name,
                "font_size": font_size,
                "bold": bold,
                "alignment": alignment,
                "primary_colour": primary_colour,
                "outline_colour": outline_colour,
                "outline": outline,
                "watermark_url": watermark_url,
                "intro_clip_url": intro_clip_url,
                "outro_clip_url": outro_clip_url,
                "vocabulary_hints": vocabulary_hints,
                "is_default": is_default,
            },
        ).one()
    return _row_to_brand_kit_record(row)


def get_brand_kit(brand_kit_id: UUID | str) -> BrandKitRecord | None:
    """Retrieve a brand kit by ID."""
    query = text("SELECT * FROM brand_kits WHERE id = :brand_kit_id")
    with engine.connect() as connection:
        row = connection.execute(query, {"brand_kit_id": str(brand_kit_id)}).one_or_none()
    return _row_to_brand_kit_record(row) if row else None


def get_user_brand_kits(user_id: UUID | str) -> list[BrandKitRecord]:
    """Retrieve all brand kits for a user."""
    query = text(
        """
        SELECT * FROM brand_kits WHERE user_id = :user_id
        ORDER BY is_default DESC, created_at DESC
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"user_id": str(user_id)}).fetchall()
    return [_row_to_brand_kit_record(row) for row in rows]


def get_user_default_brand_kit(user_id: UUID | str) -> BrandKitRecord | None:
    """Retrieve the default brand kit for a user."""
    query = text(
        """
        SELECT * FROM brand_kits WHERE user_id = :user_id AND is_default = true
        LIMIT 1
        """
    )
    with engine.connect() as connection:
        row = connection.execute(query, {"user_id": str(user_id)}).one_or_none()
    return _row_to_brand_kit_record(row) if row else None


def update_brand_kit(brand_kit_id: UUID | str, **fields: Any) -> BrandKitRecord:
    """Update a brand kit. Only provided fields are updated."""
    brand_kit = get_brand_kit(brand_kit_id)
    if not brand_kit:
        raise ValueError(f"Brand kit {brand_kit_id} not found")

    updatable_fields = {
        "name",
        "font_name",
        "font_size",
        "bold",
        "alignment",
        "primary_colour",
        "outline_colour",
        "outline",
        "watermark_url",
        "intro_clip_url",
        "outro_clip_url",
        "vocabulary_hints",
        "is_default",
    }

    assignments: list[str] = []
    params: dict[str, Any] = {"brand_kit_id": str(brand_kit_id)}

    for field_name, value in fields.items():
        if field_name not in updatable_fields:
            raise ValueError(f"Cannot update field: {field_name}")
        assignments.append(f"{field_name} = :{field_name}")
        params[field_name] = value

    if not assignments:
        return brand_kit

    query = text(
        f"""
        UPDATE brand_kits
        SET {", ".join(assignments)}
        WHERE id = :brand_kit_id
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(query, params).one()
    return _row_to_brand_kit_record(row)


def delete_brand_kit(brand_kit_id: UUID | str) -> bool:
    """Delete a brand kit."""
    query = text("DELETE FROM brand_kits WHERE id = :brand_kit_id")
    with engine.begin() as connection:
        result = connection.execute(query, {"brand_kit_id": str(brand_kit_id)})
    return result.rowcount > 0
