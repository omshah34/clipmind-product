"use client";

/**
 * Page: app/intelligence/page.tsx
 * Purpose: Clip Intelligence Dashboard - shows performance analytics for all jobs.
 *          Displays performance summary, charts, alerts, and platform statistics.
 */

import React, { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  getPerformanceSummary,
  getPerformanceAlerts,
  markAlertAsRead,
  PerformanceSummary,
  PerformanceAlert,
} from "@/lib/api";
import PerformanceSummaryCards from "@/components/performance-summary";
import PerformanceCharts from "@/components/performance-charts";
import { ErrorBoundary } from "@/components/error-boundary";

export default function IntelligenceContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const jobId = searchParams.get("job_id");
  const clipIndex = searchParams.get("clip_index");

  const [userId] = useState(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("user_id") || "";
    }
    return "";
  });

  const [performanceSummary, setPerformanceSummary] =
    useState<PerformanceSummary | null>(null);
  const [alerts, setAlerts] = useState<PerformanceAlert[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"summary" | "alerts">("summary");

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        setError(null);

        if (!userId) {
          setError("User not authenticated");
          return;
        }

        if (!jobId) {
          setError("No job selected");
          return;
        }

        // Load performance summary
        const summary = await getPerformanceSummary(jobId, userId);
        setPerformanceSummary(summary);

        // Load alerts
        const alertsData = await getPerformanceAlerts(userId);
        setAlerts(alertsData.alerts);
        setUnreadCount(alertsData.unread_count);
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to load performance data";
        setError(message);
        console.error("Performance load error:", err);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [jobId, userId]);

  const handleMarkAlertAsRead = async (alertId: string) => {
    try {
      await markAlertAsRead(alertId, userId);
      setAlerts(alerts.map((a) => (a.id === alertId ? { ...a, is_read: true } : a)));
      setUnreadCount(Math.max(0, unreadCount - 1));
    } catch (err) {
      console.error("Failed to mark alert as read:", err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
          <p className="mt-4 text-gray-600">Loading performance analytics...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <div className="bg-white rounded-lg shadow-md p-6 max-w-md w-full">
          <div className="flex items-center justify-center w-10 h-10 rounded-full bg-red-100 mb-4">
            <span className="text-red-600 text-xl">!</span>
          </div>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">Error</h2>
          <p className="text-gray-600 mb-4">{error}</p>
          <button
            onClick={() => router.push("/")}
            className="w-full px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark transition"
          >
            Go Back Home
          </button>
        </div>
      </div>
    );
  }

  if (!performanceSummary) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <div className="bg-white rounded-lg shadow-md p-6 max-w-md w-full">
          <h2 className="text-lg font-semibold text-gray-900 mb-2">
            No Data Available
          </h2>
          <p className="text-gray-600 mb-4">
            This job doesn't have performance data yet. Performance metrics appear once clips are published to social platforms.
          </p>
          <button
            onClick={() => router.push("/")}
            className="w-full px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark transition"
          >
            Go Back Home
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto p-4 sm:p-6 lg:p-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">
                Clip Intelligence
              </h1>
              <p className="text-gray-600 mt-1">
                Performance analytics for job {jobId?.substring(0, 8)}...
              </p>
            </div>
            <button
              onClick={() => router.back()}
              className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition"
            >
              ← Back
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 mb-6">
          <button
            onClick={() => setActiveTab("summary")}
            className={`px-4 py-3 font-medium border-b-2 transition ${
              activeTab === "summary"
                ? "text-primary border-primary"
                : "text-gray-600 border-transparent hover:text-gray-900"
            }`}
          >
            Performance Summary
          </button>
          <button
            onClick={() => setActiveTab("alerts")}
            className={`px-4 py-3 font-medium border-b-2 transition relative ${
              activeTab === "alerts"
                ? "text-primary border-primary"
                : "text-gray-600 border-transparent hover:text-gray-900"
            }`}
          >
            Alerts
            {unreadCount > 0 && (
              <span className="absolute top-2 right-2 inline-flex items-center justify-center h-5 w-5 rounded-full bg-red-500 text-white text-xs font-bold">
                {unreadCount}
              </span>
            )}
          </button>
        </div>

        {/* Summary Tab */}
        {activeTab === "summary" && (
          <div className="space-y-6">
            <ErrorBoundary name="Summary Cards">
              <PerformanceSummaryCards data={performanceSummary} clipIndex={clipIndex} />
            </ErrorBoundary>
            <ErrorBoundary name="Performance Charts">
              <PerformanceCharts data={performanceSummary} clipIndex={clipIndex} />
            </ErrorBoundary>
          </div>
        )}

        {/* Alerts Tab */}
        {activeTab === "alerts" && (
          <div className="bg-white rounded-lg shadow-md p-6">
            {alerts.length === 0 ? (
              <div className="text-center py-12">
                <p className="text-gray-500">No alerts at this time</p>
              </div>
            ) : (
              <div className="space-y-3">
                {alerts.map((alert) => (
                  <div
                    key={alert.id}
                    className={`flex items-start justify-between p-4 rounded-lg border transition ${
                      alert.is_read
                        ? "bg-gray-50 border-gray-200"
                        : "bg-blue-50 border-blue-300"
                    }`}
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span
                          className={`px-2 py-1 rounded-full text-xs font-medium ${
                            alert.alert_type === "milestone"
                              ? "bg-green-100 text-green-800"
                              : alert.alert_type === "trending"
                              ? "bg-orange-100 text-orange-800"
                              : "bg-red-100 text-red-800"
                          }`}
                        >
                          {alert.alert_type.charAt(0).toUpperCase() +
                            alert.alert_type.slice(1)}
                        </span>
                        {!alert.is_read && (
                          <span className="h-2 w-2 rounded-full bg-blue-500"></span>
                        )}
                      </div>
                      <p className="text-gray-900 mt-1">{alert.message}</p>
                      <p className="text-xs text-gray-500 mt-1">
                        {new Date(alert.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    {!alert.is_read && (
                      <button
                        onClick={() => handleMarkAlertAsRead(alert.id)}
                        className="ml-4 px-3 py-1 text-sm font-medium text-primary hover:bg-blue-100 rounded transition"
                      >
                        Mark Read
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

