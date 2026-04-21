/**
 * File: components/campaign-calendar.tsx
 * Purpose: Calendar view of scheduled clips in a campaign.
 */

'use client';

import React, { useState, useEffect } from 'react';
import { getCampaignCalendar, type ClipCalendar } from '@/lib/api';

type CampaignCalendarProps = {
  campaignId: string;
  userId: string;
  daysAhead?: number;
};

export default function CampaignCalendar({
  campaignId,
  userId,
  daysAhead = 30,
}: CampaignCalendarProps) {
  const [calendar, setCalendar] = useState<ClipCalendar | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  useEffect(() => {
    loadCalendar();
  }, [campaignId]);

  async function loadCalendar() {
    try {
      setLoading(true);
      const data = await getCampaignCalendar(campaignId, userId, daysAhead);
      setCalendar(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load calendar');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg bg-red-50 p-4">
        <p className="text-sm font-medium text-red-900">{error}</p>
      </div>
    );
  }

  if (!calendar) {
    return null;
  }

  const dates = Object.keys(calendar.clips_by_date).sort();
  const selectedClips = selectedDate ? calendar.clips_by_date[selectedDate] || [] : [];

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <h3 className="mb-4 text-lg font-semibold text-gray-900">Publish Calendar</h3>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Date list */}
        <div className="lg:col-span-1">
          <div className="space-y-1 max-h-96 overflow-y-auto">
            {dates.length === 0 ? (
              <p className="text-sm text-gray-600 p-4">No clips scheduled</p>
            ) : (
              dates.map((date) => {
                const clipCount = calendar.clips_by_date[date].length;
                const isSelected = date === selectedDate;

                return (
                  <button
                    key={date}
                    onClick={() => setSelectedDate(isSelected ? null : date)}
                    className={`w-full text-left px-3 py-2 rounded-lg transition-colors ${
                      isSelected
                        ? 'bg-blue-100 text-blue-900 font-medium'
                        : 'hover:bg-gray-100 text-gray-900'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span>{new Date(date).toLocaleDateString()}</span>
                      <span className="text-xs font-semibold bg-blue-200 text-blue-900 px-2 py-1 rounded-full">
                        {clipCount}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Clips for selected date */}
        <div className="lg:col-span-2">
          {selectedDate ? (
            <div className="space-y-3">
              <h4 className="font-semibold text-gray-900">
                {new Date(selectedDate).toLocaleDateString()} — {selectedClips.length} clip(s)
              </h4>
              <div className="space-y-2">
                {selectedClips.map((clip, idx) => (
                  <div
                    key={idx}
                    className="rounded-lg border border-gray-200 bg-gray-50 p-3"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="font-medium text-gray-900">Clip {idx + 1}</div>
                        <div className="mt-1 text-sm text-gray-600">
                          {clip.start_time?.toFixed(1)}s — {clip.end_time?.toFixed(1)}s
                        </div>
                        {clip.reason && (
                          <div className="mt-1 text-xs text-gray-600">
                            {clip.reason}
                          </div>
                        )}
                      </div>
                      <div className="ml-4 text-right">
                        <div className="text-lg font-bold text-blue-600">
                          {clip.final_score?.toFixed(1)}
                        </div>
                        <div className="text-xs text-gray-500">score</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-32 text-gray-600">
              <p>Select a date to view scheduled clips</p>
            </div>
          )}
        </div>
      </div>

      {/* Summary */}
      <div className="mt-6 pt-4 border-t border-gray-200">
        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <div className="text-2xl font-bold text-blue-600">
              {calendar.total_scheduled_clips}
            </div>
            <div className="text-sm text-gray-600">Total Scheduled</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-700">{dates.length}</div>
            <div className="text-sm text-gray-600">Publishing Days</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-700">
              {daysAhead}
            </div>
            <div className="text-sm text-gray-600">Days Ahead</div>
          </div>
        </div>
      </div>
    </div>
  );
}
