/**
 * File: app/publish/page.tsx
 * Purpose: One-Click Publish - Configure and publish clips to social platforms.
 *          Users can connect accounts, optimize captions, and schedule posts.
 */

"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/components/auth-provider";

function PublishLoading() {
  return (
    <div className="page" style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh" }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: 32, marginBottom: 16 }}>⏳</div>
        <div style={{ fontSize: 14, color: "var(--muted)" }}>Loading Publish...</div>
      </div>
    </div>
  );
}

export default function PublishPage() {
  return (
    <Suspense fallback={<PublishLoading />}>
      <PublishContent />
    </Suspense>
  );
}

interface SocialAccount {
  account_id: string;
  platform: "tiktok" | "instagram" | "youtube" | "linkedin";
  username: string;
  connected_at: string;
}

interface PublishedClip {
  published_clip_id: string;
  platform: string;
  platform_clip_id: string;
  platform_url: string;
  status: "published" | "scheduled" | "queued" | "failed";
  engagement_metrics: {
    views: number;
    likes: number;
    shares: number;
  };
}

const PLATFORMS = [
  { id: "tiktok", name: "TikTok", color: "#000000", icon: "♪" },
  { id: "instagram", name: "Instagram", color: "#E4405F", icon: "📷" },
  { id: "youtube", name: "YouTube", color: "#FF0000", icon: "▶" },
  { id: "linkedin", name: "LinkedIn", color: "#0A66C2", icon: "in" },
];

function PublishContent() {
  const searchParams = useSearchParams();
  const { user, token } = useAuth();

  const jobId = searchParams.get("job") || "";
  const clipIndex = parseInt(searchParams.get("clip") || "0");

  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);
  const [socialAccounts, setSocialAccounts] = useState<SocialAccount[]>([]);
  const [publishedClips, setPublishedClips] = useState<PublishedClip[]>([]);

  const [caption, setCaption] = useState("");
  const [hashtags, setHashtags] = useState("");
  const [scheduledFor, setScheduledFor] = useState("");

  const [optimizedCaptions, setOptimizedCaptions] = useState<
    Record<string, string>
  >({});

  const [isPublishing, setIsPublishing] = useState(false);
  const [isOptimizing, setIsOptimizing] = useState(false);
  const [publishError, setPublishError] = useState<string | null>(null);

  // Fetch social accounts
  useEffect(() => {
    fetchSocialAccounts();
  }, [token]);

  const fetchSocialAccounts = async () => {
    try {
      const response = await fetch("/api/v1/publish/accounts", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setSocialAccounts(Array.isArray(data) ? data : data.accounts || []);
      }
    } catch (error) {
      console.error("Failed to fetch social accounts:", error);
    }
  };

  const handleConnectAccount = async (platform: string) => {
    window.location.href = `/integrations?platform=${encodeURIComponent(platform)}`;
  };

  const handleOptimizeCaption = async () => {
    if (!caption.trim()) {
      setPublishError("Please enter a caption");
      return;
    }

    setIsOptimizing(true);
    setPublishError(null);

    try {
      const response = await fetch(
        `/api/v1/publish/${jobId}/${clipIndex}/optimize-captions`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            original_caption: caption,
            platforms: selectedPlatforms,
          }),
        }
      );

      if (!response.ok) throw new Error("Optimization failed");

      const data = await response.json();
      setOptimizedCaptions(data);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Optimization failed";
      setPublishError(message);
    } finally {
      setIsOptimizing(false);
    }
  };

  const handlePublish = async () => {
    if (selectedPlatforms.length === 0) {
      setPublishError("Select at least one platform");
      return;
    }

    if (!caption.trim()) {
      setPublishError("Enter a caption before publishing");
      return;
    }

    setIsPublishing(true);
    setPublishError(null);

    try {
      const publishPromises = selectedPlatforms.map((platform) =>
        fetch(`/api/v1/publish/${jobId}/${clipIndex}/publish`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            platform,
            caption: optimizedCaptions[platform] || caption,
            hashtags,
            scheduled_for: scheduledFor || null,
          }),
        })
      );

      const responses = await Promise.all(publishPromises);
      const results: PublishedClip[] = [];
      for (const response of responses) {
        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new Error(payload?.detail || "Publishing failed");
        }
        results.push(await response.json());
      }

      setPublishedClips((prev) => [...prev, ...results]);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Publishing failed";
      setPublishError(message);
    } finally {
      setIsPublishing(false);
    }
  };

  const accountsByPlatform = socialAccounts.reduce(
    (acc: Record<string, SocialAccount>, account) => {
      acc[account.platform] = account;
      return acc;
    },
    {} as Record<string, SocialAccount>
  );

  return (
    <div className="page">
      <div className="brand" style={{ marginBottom: 32 }}>
        <div className="brand-mark">
          <div
            className="brand-dot"
            style={{ background: "linear-gradient(135deg, #ff6b6b, #ee5a6f)" }}
          />
          One-Click Publish
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        {/* Left: Platform Selection */}
        <div className="panel">
          <h2>Select Platforms</h2>

          <div style={{ marginBottom: 16 }}>
            {PLATFORMS.map((platform) => {
              const isConnected = !!accountsByPlatform[platform.id];
              const isSelected = selectedPlatforms.includes(platform.id);

              return (
                <div
                  key={platform.id}
                  onClick={() => {
                    if (isConnected) {
                      setSelectedPlatforms((prev) =>
                        prev.includes(platform.id)
                          ? prev.filter((p) => p !== platform.id)
                          : [...prev, platform.id]
                      );
                    }
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: 12,
                    marginBottom: 8,
                    borderRadius: 8,
                    border: `2px solid ${
                      isSelected
                        ? platform.color
                        : "var(--line)"
                    }`,
                    backgroundColor: isSelected
                      ? `${platform.color}15`
                      : "rgba(0, 0, 0, 0.2)",
                    cursor: isConnected ? "pointer" : "not-allowed",
                    opacity: isConnected ? 1 : 0.5,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span style={{ fontSize: 18 }}>{platform.icon}</span>
                    <div>
                      <div style={{ fontWeight: 600 }}>{platform.name}</div>
                      {!isConnected && (
                        <div
                          style={{
                            fontSize: 11,
                            color: "var(--muted)",
                          }}
                        >
                          Not connected
                        </div>
                      )}
                      {accountsByPlatform[platform.id] && (
                        <div
                          style={{
                            fontSize: 11,
                            color: "var(--muted)",
                          }}
                        >
                          @{accountsByPlatform[platform.id].username}
                        </div>
                      )}
                    </div>
                  </div>

                  {!isConnected && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleConnectAccount(platform.id);
                      }}
                      style={{
                        padding: "6px 12px",
                        borderRadius: 6,
                        border: "1px solid var(--line)",
                        backgroundColor: "var(--accent-soft)",
                        color: "var(--accent)",
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      Connect
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Right: Caption & Settings */}
        <div className="panel">
          <h2>Caption & Hashtags</h2>

          <label className="field" style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 8 }}>
              Caption
            </div>
            <textarea
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              placeholder="Write your caption here..."
              style={{
                width: "100%",
                minHeight: 80,
                padding: 12,
                backgroundColor: "rgba(0, 0, 0, 0.3)",
                border: "1px solid var(--line)",
                borderRadius: 8,
                color: "var(--text)",
                fontSize: 14,
              }}
              disabled={isPublishing}
            />
          </label>

          <label className="field" style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 8 }}>
              Hashtags
            </div>
            <input
              type="text"
              value={hashtags}
              onChange={(e) => setHashtags(e.target.value)}
              placeholder="#viral #content #trending"
              style={{
                width: "100%",
                padding: 10,
                backgroundColor: "rgba(0, 0, 0, 0.3)",
                border: "1px solid var(--line)",
                borderRadius: 8,
                color: "var(--text)",
              }}
              disabled={isPublishing}
            />
          </label>

          <label className="field" style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 8 }}>
              Schedule For (Optional)
            </div>
            <input
              type="datetime-local"
              value={scheduledFor}
              onChange={(e) => setScheduledFor(e.target.value)}
              style={{
                width: "100%",
                padding: 10,
                backgroundColor: "rgba(0, 0, 0, 0.3)",
                border: "1px solid var(--line)",
                borderRadius: 8,
                color: "var(--text)",
              }}
              disabled={isPublishing}
            />
          </label>

          <button
            onClick={handleOptimizeCaption}
            disabled={isOptimizing || !caption.trim() || selectedPlatforms.length === 0}
            style={{
              width: "100%",
              padding: 10,
              marginBottom: 8,
              borderRadius: 8,
              border: "1px solid rgba(255, 111, 97, 0.3)",
              backgroundColor: "rgba(255, 111, 97, 0.1)",
              color: "rgba(255, 111, 97, 0.8)",
              fontSize: 13,
              fontWeight: 600,
              cursor: isOptimizing ? "not-allowed" : "pointer",
            }}
          >
            {isOptimizing ? "Optimizing..." : "Optimize for Selected Platforms"}
          </button>

          {Object.keys(optimizedCaptions).length > 0 && (
            <div style={{ marginBottom: 16, fontSize: 12 }}>
              <div style={{ marginBottom: 8, color: "var(--muted)" }}>
                Platform-specific captions:
              </div>
              {Object.entries(optimizedCaptions).map(([platform, text]) => (
                <div
                  key={platform}
                  style={{
                    padding: 8,
                    marginBottom: 6,
                    backgroundColor: "rgba(0, 255, 0, 0.05)",
                    border: "1px solid rgba(0, 255, 0, 0.2)",
                    borderRadius: 4,
                    wordBreak: "break-word",
                  }}
                >
                  <strong style={{ color: "var(--accent)" }}>
                    {platform.toUpperCase()}:
                  </strong>{" "}
                  {text}
                </div>
              ))}
            </div>
          )}

          {publishError && (
            <div
              style={{
                padding: 12,
                marginBottom: 12,
                backgroundColor: "rgba(255, 0, 0, 0.1)",
                border: "1px solid #AA0000",
                borderRadius: 8,
                fontSize: 12,
                color: "#FF6666",
              }}
            >
              {publishError}
            </div>
          )}

          <button
            onClick={handlePublish}
            disabled={
              isPublishing ||
              selectedPlatforms.length === 0 ||
              !caption.trim()
            }
            style={{
              width: "100%",
              padding: 12,
              borderRadius: 8,
              border: "1px solid var(--accent)",
              backgroundColor: "rgba(255, 111, 97, 0.2)",
              color: "var(--accent)",
              fontWeight: 600,
              cursor: isPublishing ? "not-allowed" : "pointer",
              opacity: isPublishing || !caption.trim() ? 0.5 : 1,
            }}
          >
            {isPublishing ? "Publishing..." : "Publish to Selected Platforms"}
          </button>
        </div>
      </div>

      {publishedClips.length > 0 && (
        <div className="panel" style={{ marginTop: 24 }}>
          <h2>Published Clips</h2>
          {publishedClips.map((clip, idx) => (
            <div
              key={idx}
              style={{
                padding: 12,
                marginBottom: 12,
                borderRadius: 8,
                backgroundColor: "rgba(0, 255, 0, 0.05)",
                border: "1px solid rgba(0, 255, 0, 0.2)",
                fontSize: 13,
              }}
            >
              <div style={{ marginBottom: 6 }}>
                <strong>{clip.platform.toUpperCase()}</strong> •{" "}
                {clip.status.toUpperCase()}
                {" "}
                {clip.engagement_metrics?.views ?? 0} views
              </div>
              {clip.platform_url ? (
                <a
                  href={clip.platform_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: "var(--accent)" }}
                >
                  View on {clip.platform}
                </a>
              ) : (
                <span style={{ color: "var(--muted)" }}>
                  {clip.status === "scheduled"
                    ? "Scheduled for publishing"
                    : "Queued for publishing"}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
