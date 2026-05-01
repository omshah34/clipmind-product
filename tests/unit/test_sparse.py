"""File: tests/unit/test_sparse.py
Purpose: Unit tests for core.sparse utility.
"""

import pytest
from fastapi import HTTPException
from pydantic import BaseModel
from typing import List, Optional
from core.sparse import apply_sparse_filter

class SubModel(BaseModel):
    id: int
    name: str

class MockSchema(BaseModel):
    id: str
    status: str
    internal_flag: bool = False
    sub: Optional[SubModel] = None
    tags: List[str] = []

class MockDomainModel(BaseModel):
    id: str
    status: str
    internal_flag: bool
    internal_cost: float  # NOT in schema
    sub: Optional[SubModel] = None
    tags: List[str] = []

def test_valid_fields():
    data = MockDomainModel(id="123", status="completed", internal_flag=True, internal_cost=10.5)
    # Filter for only id and status
    result = apply_sparse_filter(data, "id,status", MockSchema)
    
    assert result == {"id": "123", "status": "completed"}
    assert "internal_flag" not in result
    assert "internal_cost" not in result

def test_security_allowlisting():
    data = MockDomainModel(id="123", status="completed", internal_flag=True, internal_cost=10.5)
    
    # Requesting a field that exists on domain but NOT in schema should fail
    with pytest.raises(HTTPException) as exc:
        apply_sparse_filter(data, "id,internal_cost", MockSchema)
    
    assert exc.value.status_code == 400
    assert "internal_cost" in str(exc.value.detail)

def test_empty_fields():
    data = MockDomainModel(id="123", status="completed", internal_flag=True, internal_cost=10.5)
    
    # Empty string should return the original data (unfiltered)
    result = apply_sparse_filter(data, "", MockSchema)
    assert result == data
    
    # None should return the original data
    result = apply_sparse_filter(data, None, MockSchema)
    assert result == data

def test_nested_object_return_full():
    # v1 behavior: requesting 'sub' returns the full sub-object
    sub = SubModel(id=1, name="test")
    data = MockDomainModel(id="123", status="completed", internal_flag=True, internal_cost=10.5, sub=sub)
    
    result = apply_sparse_filter(data, "id,sub", MockSchema)
    
    assert result["id"] == "123"
    assert result["sub"] == {"id": 1, "name": "test"}

def test_list_of_models():
    data_list = [
        MockDomainModel(id="1", status="pending", internal_flag=False, internal_cost=1.0),
        MockDomainModel(id="2", status="processing", internal_flag=False, internal_cost=2.0),
    ]
    
    result = apply_sparse_filter(data_list, "id", MockSchema)
    
    assert len(result) == 2
    assert result[0] == {"id": "1"}
    assert result[1] == {"id": "2"}

def test_invalid_field_format():
    data = MockDomainModel(id="1", status="p", internal_flag=False, internal_cost=0)
    
    # Spaces and trailing commas should be handled
    result = apply_sparse_filter(data, " id , status , ", MockSchema)
    assert result == {"id": "1", "status": "p"}
