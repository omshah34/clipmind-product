/**
 * File: app/team/page.tsx
 * Purpose: Team Workspaces - Multi-user collaboration dashboard.
 *          Users can manage team members, client access, and audit logs.
 */

"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/components/auth-provider";

interface WorkspaceMember {
  member_id: string;
  user_id: string;
  email: string;
  role: "owner" | "editor" | "viewer";
  joined_at: string;
}

interface WorkspaceClient {
  client_id: string;
  client_name: string;
  contact_email: string;
  client_status: "active" | "inactive";
}

interface ClientPortal {
  portal_id: string;
  client_id: string;
  portal_token: string;
  portal_url: string;
  portal_status: "active" | "inactive";
}

interface AuditLog {
  log_id: string;
  action: string;
  performed_by: string;
  resource_type: string;
  timestamp: string;
}

export default function TeamDashboard() {
  const { user, token } = useAuth();
  const workspaceId = user?.workspaceId || user?.id || "";

  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [clients, setClients] = useState<WorkspaceClient[]>([]);
  const [portals, setPortals] = useState<ClientPortal[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);

  const [showAddMember, setShowAddMember] = useState(false);
  const [newMemberEmail, setNewMemberEmail] = useState("");
  const [newMemberRole, setNewMemberRole] = useState<"editor" | "viewer">(
    "editor"
  );

  const [showAddClient, setShowAddClient] = useState(false);
  const [newClientName, setNewClientName] = useState("");
  const [newClientEmail, setNewClientEmail] = useState("");

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (workspaceId) {
      fetchWorkspaceData();
    }
  }, [workspaceId, token]);

  const fetchWorkspaceData = async () => {
    try {
      if (!workspaceId) return;

      const [membersRes, clientsRes, portalsRes, logsRes] = await Promise.all(
        [
          fetch(`/api/v1/workspaces/${workspaceId}/members`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`/api/v1/workspaces/${workspaceId}/clients`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`/api/v1/workspaces/${workspaceId}/portals`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`/api/v1/workspaces/${workspaceId}/audit-logs`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
        ]
      );

      if (membersRes.ok)
        setMembers(await membersRes.json());
      if (clientsRes.ok)
        setClients(await clientsRes.json());
      if (portalsRes.ok)
        setPortals(await portalsRes.json());
      if (logsRes.ok)
        setAuditLogs(await logsRes.json());
    } catch (err) {
      console.error("Failed to fetch workspace data:", err);
    }
  };

  const handleAddMember = async () => {
    if (!newMemberEmail.trim()) {
      setError("Enter an email address");
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/v1/workspaces/${workspaceId}/members`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            email: newMemberEmail,
            role: newMemberRole,
          }),
        }
      );

      if (!response.ok) throw new Error("Failed to add member");

      const newMember = await response.json();
      setMembers([...members, newMember]);
      setNewMemberEmail("");
      setShowAddMember(false);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to add member";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRemoveMember = async (memberId: string) => {
    if (!confirm("Remove this team member?")) return;

    try {
      await fetch(
        `/api/v1/workspaces/${workspaceId}/members/${memberId}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      setMembers(members.filter((m) => m.member_id !== memberId));
    } catch (err) {
      console.error("Failed to remove member:", err);
    }
  };

  const handleAddClient = async () => {
    if (!newClientName.trim() || !newClientEmail.trim()) {
      setError("Enter client name and email");
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/v1/workspaces/${workspaceId}/clients`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            client_name: newClientName,
            contact_email: newClientEmail,
          }),
        }
      );

      if (!response.ok) throw new Error("Failed to add client");

      const newClient = await response.json();
      setClients([...clients, newClient]);
      setNewClientName("");
      setNewClientEmail("");
      setShowAddClient(false);

      // Create portal for this client
      const portalRes = await fetch(
        `/api/v1/workspaces/${workspaceId}/clients/${newClient.client_id}/portal`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (portalRes.ok) {
        const newPortal = await portalRes.json();
        setPortals([...portals, newPortal]);
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to add client";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const getRoleColor = (role: string) => {
    switch (role) {
      case "owner":
        return "var(--accent)";
      case "editor":
        return "#4a90e2";
      case "viewer":
        return "var(--muted)";
      default:
        return "var(--muted)";
    }
  };

  return (
    <div className="page">
      <div className="brand" style={{ marginBottom: 32 }}>
        <div className="brand-mark">
          <div
            className="brand-dot"
            style={{
              background: "linear-gradient(135deg, #667eea, #764ba2)",
            }}
          />
          Team Workspace
        </div>
      </div>

      {error && (
        <div
          style={{
            padding: 12,
            marginBottom: 16,
            backgroundColor: "rgba(255, 0, 0, 0.1)",
            border: "1px solid #AA0000",
            borderRadius: 8,
            fontSize: 12,
            color: "#FF6666",
          }}
        >
          {error}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        {/* Team Members */}
        <div className="panel">
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 16,
            }}
          >
            <h2>Team Members</h2>
            <button
              onClick={() => setShowAddMember(!showAddMember)}
              style={{
                padding: "6px 12px",
                borderRadius: 6,
                border: "1px solid var(--accent)",
                backgroundColor: "rgba(255, 111, 97, 0.2)",
                color: "var(--accent)",
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              +Add
            </button>
          </div>

          {showAddMember && (
            <div
              style={{
                padding: 12,
                marginBottom: 16,
                backgroundColor: "rgba(0, 0, 0, 0.2)",
                borderRadius: 8,
                border: "1px solid var(--line)",
              }}
            >
              <input
                type="email"
                value={newMemberEmail}
                onChange={(e) => setNewMemberEmail(e.target.value)}
                placeholder="member@company.com"
                style={{
                  width: "100%",
                  padding: 8,
                  marginBottom: 8,
                  borderRadius: 6,
                  border: "1px solid var(--line)",
                  backgroundColor: "rgba(0, 0, 0, 0.3)",
                  color: "var(--text)",
                }}
              />
              <select
                value={newMemberRole}
                onChange={(e) => setNewMemberRole(e.target.value as "editor" | "viewer")}
                aria-label="Member role"
                style={{
                  width: "100%",
                  padding: 8,
                  marginBottom: 8,
                  borderRadius: 6,
                  border: "1px solid var(--line)",
                  backgroundColor: "rgba(0, 0, 0, 0.3)",
                  color: "var(--text)",
                }}
              >
                <option value="editor">Editor</option>
                <option value="viewer">Viewer</option>
              </select>
              <button
                onClick={handleAddMember}
                disabled={isLoading}
                style={{
                  width: "100%",
                  padding: 8,
                  borderRadius: 6,
                  border: "1px solid var(--accent)",
                  backgroundColor: "rgba(255, 111, 97, 0.2)",
                  color: "var(--accent)",
                  fontWeight: 600,
                  cursor: isLoading ? "not-allowed" : "pointer",
                }}
              >
                {isLoading ? "Adding..." : "Add Member"}
              </button>
            </div>
          )}

          {members.map((member) => (
            <div
              key={member.member_id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: 12,
                marginBottom: 8,
                backgroundColor:
                  member.user_id === user?.id
                    ? "rgba(255, 111, 97, 0.05)"
                    : "rgba(0, 0, 0, 0.2)",
                borderRadius: 8,
                border: "1px solid var(--line)",
              }}
            >
              <div>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>
                  {member.email}
                </div>
                <div style={{ fontSize: 12, color: "var(--muted)" }}>
                  {member.user_id === user?.id ? "You" : "Joined"}{" "}
                  {new Date(member.joined_at).toLocaleDateString()}
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span
                  style={{
                    padding: "4px 8px",
                    borderRadius: 4,
                    backgroundColor: `${getRoleColor(member.role)}15`,
                    color: getRoleColor(member.role),
                    fontSize: 11,
                    fontWeight: 600,
                    textTransform: "uppercase",
                  }}
                >
                  {member.role}
                </span>
                {member.user_id !== user?.id && user?.role === "owner" && (
                  <button
                    onClick={() => handleRemoveMember(member.member_id)}
                    style={{
                      padding: "4px 8px",
                      borderRadius: 4,
                      border: "1px solid #AA0000",
                      backgroundColor: "rgba(255, 0, 0, 0.1)",
                      color: "#FF6666",
                      fontSize: 11,
                      cursor: "pointer",
                    }}
                  >
                    Remove
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Clients & Portals */}
        <div className="panel">
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 16,
            }}
          >
            <h2>Clients</h2>
            <button
              onClick={() => setShowAddClient(!showAddClient)}
              style={{
                padding: "6px 12px",
                borderRadius: 6,
                border: "1px solid #4a90e2",
                backgroundColor: "rgba(74, 144, 226, 0.2)",
                color: "#4a90e2",
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              +Add
            </button>
          </div>

          {showAddClient && (
            <div
              style={{
                padding: 12,
                marginBottom: 16,
                backgroundColor: "rgba(0, 0, 0, 0.2)",
                borderRadius: 8,
                border: "1px solid var(--line)",
              }}
            >
              <input
                type="text"
                value={newClientName}
                onChange={(e) => setNewClientName(e.target.value)}
                placeholder="Client name"
                style={{
                  width: "100%",
                  padding: 8,
                  marginBottom: 8,
                  borderRadius: 6,
                  border: "1px solid var(--line)",
                  backgroundColor: "rgba(0, 0, 0, 0.3)",
                  color: "var(--text)",
                }}
              />
              <input
                type="email"
                value={newClientEmail}
                onChange={(e) => setNewClientEmail(e.target.value)}
                placeholder="contact@client.com"
                style={{
                  width: "100%",
                  padding: 8,
                  marginBottom: 8,
                  borderRadius: 6,
                  border: "1px solid var(--line)",
                  backgroundColor: "rgba(0, 0, 0, 0.3)",
                  color: "var(--text)",
                }}
              />
              <button
                onClick={handleAddClient}
                disabled={isLoading}
                style={{
                  width: "100%",
                  padding: 8,
                  borderRadius: 6,
                  border: "1px solid #4a90e2",
                  backgroundColor: "rgba(74, 144, 226, 0.2)",
                  color: "#4a90e2",
                  fontWeight: 600,
                  cursor: isLoading ? "not-allowed" : "pointer",
                }}
              >
                {isLoading ? "Adding..." : "Add Client"}
              </button>
            </div>
          )}

          {clients.map((client) => {
            const clientPortals = portals.filter((p) => p.client_id === client.client_id);
            return (
              <div
                key={client.client_id}
                style={{
                  padding: 12,
                  marginBottom: 12,
                  backgroundColor: "rgba(0, 0, 0, 0.2)",
                  borderRadius: 8,
                  border: "1px solid var(--line)",
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: 8 }}>
                  {client.client_name}
                </div>
                <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 8 }}>
                  {client.contact_email}
                </div>
                {clientPortals.length > 0 && (
                  <div
                    style={{
                      padding: 8,
                      backgroundColor: "rgba(74, 144, 226, 0.05)",
                      borderRadius: 4,
                      border: "1px solid rgba(74, 144, 226, 0.2)",
                      fontSize: 11,
                    }}
                  >
                    <div style={{ marginBottom: 4, color: "var(--muted)" }}>
                      Portal URL:
                    </div>
                    <a
                      href={clientPortals[0].portal_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: "#4a90e2", wordBreak: "break-all" }}
                    >
                      {clientPortals[0].portal_url}
                    </a>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Audit Logs */}
      <div className="panel" style={{ marginTop: 24 }}>
        <h2>Audit Logs</h2>
        {auditLogs.length === 0 ? (
          <div style={{ color: "var(--muted)", fontSize: 13 }}>No recent activity</div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
              gap: 12,
            }}
          >
            {auditLogs.slice(0, 6).map((log) => (
              <div
                key={log.log_id}
                style={{
                  padding: 12,
                  backgroundColor: "rgba(0, 0, 0, 0.2)",
                  borderRadius: 8,
                  border: "1px solid var(--line)",
                  fontSize: 12,
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: 4 }}>
                  {log.action}
                </div>
                <div style={{ color: "var(--muted)", marginBottom: 6 }}>
                  {log.resource_type} • {log.performed_by}
                </div>
                <div style={{ fontSize: 11, color: "var(--muted)" }}>
                  {new Date(log.timestamp).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
