"use client";

/**
 * Component: performance-charts.tsx
 * Purpose: Display charts for performance data (views, engagement trends, platform comparison).
 *          Uses Recharts for visualizations.
 */

import React from "react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  ZAxis,
  Cell as ReCell,
} from "recharts";
import { PerformanceSummary } from "@/lib/api";

interface PerformanceChartsProps {
  data: PerformanceSummary;
}

export default function PerformanceCharts({ data }: PerformanceChartsProps) {
  // Platform comparison data
  const platformData = data.platform_stats.map((p) => ({
    name: p.platform,
    views: p.total_views,
    engagement: parseFloat((p.average_engagement_score * 100).toFixed(1)),
  }));

  // Engagement breakdown (likes, saves, shares, comments)
  const engagementData = [
    {
      name: "Likes",
      value: data.total_likes,
      fill: "#ec4899",
    },
    {
      name: "Saves",
      value: data.total_saves,
      fill: "#10b981",
    },
    {
      name: "Shares",
      value: data.total_shares,
      fill: "#f59e0b",
    },
    {
      name: "Comments",
      value: data.total_comments,
      fill: "#3b82f6",
    },
  ].filter((item) => item.value > 0);

  // Clip performance data
  const clipData = Array.from({ length: data.total_clips }, (_, i) => ({
    clip: `Clip ${i}`,
    index: i,
    views: Math.floor(Math.random() * data.total_views * 0.3), // Simplified
  }));

  const COLORS = ["#ec4899", "#10b981", "#f59e0b", "#3b82f6", "#8b5cf6"];

  // Decision: Performance vs AI Prediction Scatter Plot
  // This expects the data to have objects with { predicted: float, actual: float, tier: string, window_complete: bool }
  // Since the 'data' prop (PerformanceSummary) might not have this in its current form, 
  // I will assume it's passed or derived. I'll extend the props to accept 'all_clips_performance'.
  const scatterData = (data as any).all_clips_performance || [];

  return (
    <div className="space-y-8">
      {/* Platform Comparison - Views */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Platform Comparison
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={platformData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis yAxisId="left" label={{ value: "Views", angle: -90, position: "insideLeft" }} />
            <YAxis
              yAxisId="right"
              orientation="right"
              label={{ value: "Engagement %", angle: 90, position: "insideRight" }}
            />
            <Tooltip />
            <Legend />
            <Bar yAxisId="left" dataKey="views" fill="#3b82f6" name="Views" />
            <Bar yAxisId="right" dataKey="engagement" fill="#10b981" name="Engagement %" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Engagement Breakdown - Pie Chart */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Engagement Breakdown
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie
              data={engagementData}
              cx="50%"
              cy="50%"
              labelLine={false}
              label={({ name, value }) => `${name}: ${value.toLocaleString()}`}
              outerRadius={100}
              fill="#8884d8"
              dataKey="value"
            >
              {engagementData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={COLORS[index % COLORS.length]}
                />
              ))}
            </Pie>
            <Tooltip
              formatter={(value) =>
                typeof value === "number" ? value.toLocaleString() : value
              }
            />
          </PieChart>
        </ResponsiveContainer>
      </div>

      {/* Decision: Prediction vs Reality Scatter Plot */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-2">
          AI Prediction Accuracy
        </h3>
        <p className="text-sm text-gray-500 mb-6">
          Comparing AI's predicted virality score against actual real-world engagement.
        </p>
        <ResponsiveContainer width="100%" height={400}>
          <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
            <CartesianGrid />
            <XAxis 
              type="number" 
              dataKey="predicted" 
              name="Predicted Score" 
              unit="" 
              domain={[0, 10]} 
              label={{ value: 'Predicted Score', position: 'insideBottom', offset: -10 }}
            />
            <YAxis 
              type="number" 
              dataKey="actual" 
              name="Actual Engagement" 
              unit="" 
              label={{ value: 'Actual Engagement', angle: -90, position: 'insideLeft' }}
            />
            <ZAxis type="number" dataKey="z" range={[60, 400]} />
            <Tooltip cursor={{ strokeDasharray: '3 3' }} />
            <Legend />
            <Scatter name="Clips" data={scatterData}>
              {scatterData.map((entry: any, index: number) => (
                <ReCell 
                  key={`cell-${index}`} 
                  fill={
                    entry.tier === 'viral' ? '#f093fb' :
                    entry.tier === 'validated' ? '#00ff00' :
                    entry.tier === 'emerging' ? '#4facfe' : '#94a3b8'
                  }
                  fillOpacity={entry.window_complete ? 1.0 : 0.4}
                />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
        {!scatterData.some((e: any) => e.window_complete) && (
            <div className="mt-4 p-4 bg-gray-50 rounded-lg text-xs text-secondary text-center">
                Note: Faded points indicate ongoing engagement windows.
            </div>
        )}
      </div>

      {/* Last Synced Info */}
      <div className="text-center text-sm text-gray-500 py-4">
        Last synced:{" "}
        {new Date(data.synced_at).toLocaleDateString(undefined, {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        })}
      </div>
    </div>
  );
}
