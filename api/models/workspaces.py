"""File: api/models/workspaces.py
Purpose: Pydantic models for Team Workspaces and Client Portals
"""

from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional, List, Dict
from datetime import datetime


class WorkspaceCreateRequest(BaseModel):
    """Request to create a new workspace."""
    name: str = Field(max_length=255)
    slug: str = Field(max_length=100, pattern="^[a-z0-9-]+$")


class WorkspaceResponse(BaseModel):
    """Workspace details."""
    id: UUID
    owner_id: UUID
    name: str
    slug: str
    plan: str
    settings: Dict
    logo_url: Optional[str]
    brand_color: Optional[str]
    is_active: bool
    member_count: int
    clips_this_month: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class WorkspaceListResponse(BaseModel):
    """List of workspaces."""
    workspaces: List[WorkspaceResponse]
    total: int


class WorkspaceMemberResponse(BaseModel):
    """Team member in workspace."""
    id: UUID
    user_id: UUID
    workspace_id: UUID
    role: str  # owner, admin, editor, viewer
    joined_at: datetime
    user_name: Optional[str]
    user_email: Optional[str]
    
    class Config:
        from_attributes = True


class InviteMemberRequest(BaseModel):
    """Request to invite member to workspace."""
    email: str
    role: str = Field(description="admin, editor, viewer")
    message: Optional[str] = None


class ClientResponse(BaseModel):
    """Client managed by workspace."""
    id: UUID
    workspace_id: UUID
    client_name: str
    client_contact_email: Optional[str]
    description: Optional[str]
    is_active: bool
    portal_slug: Optional[str]
    created_at: datetime


class ClientCreateRequest(BaseModel):
    """Request to create a client."""
    client_name: str = Field(max_length=255)
    client_contact_email: Optional[str] = None
    description: Optional[str] = None


class ClientPortalBranding(BaseModel):
    """Branding for client portal."""
    logo_url: Optional[str]
    custom_domain: Optional[str]
    brand_color: Optional[str]
    company_name: Optional[str]


class ClientPortalResponse(BaseModel):
    """Client delivery portal."""
    id: UUID
    workspace_id: UUID
    client_id: UUID
    portal_slug: str
    client_name: str
    portal_url: str = Field(description="portal.clipmind.com/p/{slug}")
    branding: ClientPortalBranding
    is_active: bool
    total_submissions: int
    pending_approvals: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class PortalSubmissionResponse(BaseModel):
    """Clips submitted to client for approval."""
    id: UUID
    portal_id: UUID
    job_id: UUID
    submission_token: str
    status: str  # pending, approved, rejected, modifications_requested
    client_feedback: Optional[str]
    approved_clip_indices: Optional[List[int]]
    expires_at: datetime
    created_at: datetime


class PortalSubmissionApprovalRequest(BaseModel):
    """Client approves/rejects submission."""
    status: str = Field(description="approved, rejected, modifications_requested")
    approved_clip_indices: Optional[List[int]] = None
    feedback: Optional[str] = None


class AuditLogResponse(BaseModel):
    """Workspace activity log entry."""
    id: UUID
    workspace_id: UUID
    user_id: Optional[UUID]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[UUID]
    details: Dict
    created_at: datetime


class WorkspaceUsageResponse(BaseModel):
    """Usage metrics for workspace."""
    workspace_id: UUID
    period: str  # current_month, last_month, year_to_date
    videos_processed: int
    clips_generated: int
    clips_published: int
    api_calls: int
    storage_gb: float
    estimated_cost: float
    plan_limit: Optional[int]
    usage_percent: float


class WorkspaceBillingResponse(BaseModel):
    """Billing info for workspace."""
    workspace_id: UUID
    current_plan: str
    monthly_cost: float
    next_billing_date: datetime
    usage_this_month: Dict
    available_addons: List[Dict]
