"""File: core/sparse.py
Purpose: Utility for sparse fieldsets (API field filtering).
         Enforces schema-based allowlisting to prevent internal data exposure.
"""

from typing import Any, List, Optional, Type, Set
from fastapi import HTTPException
from pydantic import BaseModel

def apply_sparse_filter(
    data: Any,
    fields_str: Optional[str],
    schema: Type[BaseModel]
) -> Any:
    """Filter a Pydantic model or list of models based on a comma-separated field string.
    
    Validates requested fields against the provided schema (allowlist).
    Returns a dict or list of dicts.
    """
    if not fields_str:
        return data

    # 1. Parse and validate fields
    requested_fields = {f.strip() for f in fields_str.split(",") if f.strip()}
    if not requested_fields:
        return data

    allowed_fields = set(schema.model_fields.keys())
    
    # Check for invalid fields (security check)
    invalid_fields = requested_fields - allowed_fields
    if invalid_fields:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_fields",
                "message": f"Requested fields not in schema: {', '.join(invalid_fields)}",
                "allowed_fields": sorted(list(allowed_fields))
            }
        )

    # 2. Apply filtering
    if isinstance(data, list):
        return [
            _filter_single_item(item, requested_fields, schema)
            for item in data
        ]
    return _filter_single_item(data, requested_fields, schema)

def _filter_single_item(item: Any, fields: Set[str], schema: Type[BaseModel]) -> dict:
    """Helper to filter a single item using Pydantic's include mechanism."""
    # If it's already a dict, we convert it to the schema model first to ensure allowlisting
    # but usually 'item' will be a domain model (SQLAlchemy result or JobRecord)
    
    if hasattr(item, "model_dump"):
        # Domain models might have more fields than the schema. 
        # We must only include fields that are BOTH requested AND in the schema.
        return item.model_dump(include=fields)
    
    # Fallback for plain objects or SQLAlchemy rows
    result = {}
    for field in fields:
        if hasattr(item, field):
            result[field] = getattr(item, field)
        elif isinstance(item, dict) and field in item:
            result[field] = item[field]
    return result
