/**
 * File: app/campaigns/new/page.tsx
 * Purpose: Create new campaign page - form for campaign name, description, and schedule.
 */

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { createCampaign, type ScheduleConfig } from '@/lib/api';

export default function NewCampaignPage() {
  const router = useRouter();
  const { data: session, status } = useSession();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [publishInterval, setPublishInterval] = useState(1);
  const [publishHour, setPublishHour] = useState(10);
  const [publishTimezone, setPublishTimezone] = useState('UTC');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (!name.trim()) {
      setError('Campaign name is required');
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const userId = session?.user?.id || session?.user?.email || '';
      const scheduleConfig: ScheduleConfig = {
        publish_interval_days: publishInterval,
        publish_hour: publishHour,
        publish_timezone: publishTimezone,
        publish_to_channels: [],
        hashtags: [],
        enabled: true,
      };

      const campaign = await createCampaign(userId, name, description || undefined, scheduleConfig);
      router.push(`/campaigns/${campaign.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create campaign');
      setLoading(false);
    }
  }

  if (status === 'loading') {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (status === 'unauthenticated') {
    router.push('/login');
    return null;
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      <div className="mx-auto max-w-2xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-8">
          <a href="/campaigns" className="text-blue-600 hover:text-blue-700 font-medium text-sm">
            ← Back to Campaigns
          </a>
          <h1 className="mt-4 text-3xl font-bold text-gray-900">Create New Campaign</h1>
          <p className="mt-2 text-gray-600">
            Organize your videos and schedule clips for publishing
          </p>
        </div>

        {/* Form Card */}
        <div className="rounded-lg border border-gray-200 bg-white p-8 shadow-sm">
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Error */}
            {error && (
              <div className="rounded-lg bg-red-50 p-4">
                <p className="text-red-900 text-sm">{error}</p>
              </div>
            )}

            {/* Campaign Name */}
            <div>
              <label htmlFor="name" className="block text-sm font-semibold text-gray-900">
                Campaign Name *
              </label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., Q4 Marketing Push"
                className="mt-2 w-full rounded-lg border border-gray-300 px-4 py-2 text-gray-900 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                disabled={loading}
              />
            </div>

            {/* Description */}
            <div>
              <label htmlFor="description" className="block text-sm font-semibold text-gray-900">
                Description
              </label>
              <textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What is this campaign for? (optional)"
                rows={3}
                className="mt-2 w-full rounded-lg border border-gray-300 px-4 py-2 text-gray-900 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                disabled={loading}
              />
            </div>

            {/* Schedule Settings */}
            <div className="border-t border-gray-200 pt-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Scheduling</h3>

              {/* Publish Interval */}
              <div className="mb-4">
                <label htmlFor="interval" className="block text-sm font-medium text-gray-900">
                  Publish Interval (days between clips)
                </label>
                <select
                  id="interval"
                  value={publishInterval}
                  onChange={(e) => setPublishInterval(parseInt(e.target.value))}
                  className="mt-2 w-full rounded-lg border border-gray-300 px-4 py-2 text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  disabled={loading}
                >
                  <option value={1}>Every day</option>
                  <option value={2}>Every 2 days</option>
                  <option value={3}>Every 3 days</option>
                  <option value={7}>Weekly</option>
                  <option value={14}>Bi-weekly</option>
                  <option value={30}>Monthly</option>
                </select>
              </div>

              {/* Publish Hour */}
              <div className="mb-4">
                <label htmlFor="hour" className="block text-sm font-medium text-gray-900">
                  Publish Time (hour of day)
                </label>
                <select
                  id="hour"
                  value={publishHour}
                  onChange={(e) => setPublishHour(parseInt(e.target.value))}
                  className="mt-2 w-full rounded-lg border border-gray-300 px-4 py-2 text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  disabled={loading}
                >
                  {Array.from({ length: 24 }, (_, i) => (
                    <option key={i} value={i}>
                      {i.toString().padStart(2, '0')}:00
                    </option>
                  ))}
                </select>
              </div>

              {/* Timezone */}
              <div className="mb-4">
                <label htmlFor="timezone" className="block text-sm font-medium text-gray-900">
                  Timezone
                </label>
                <select
                  id="timezone"
                  value={publishTimezone}
                  onChange={(e) => setPublishTimezone(e.target.value)}
                  className="mt-2 w-full rounded-lg border border-gray-300 px-4 py-2 text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  disabled={loading}
                >
                  <option>UTC</option>
                  <option>US/Eastern</option>
                  <option>US/Central</option>
                  <option>US/Mountain</option>
                  <option>US/Pacific</option>
                  <option>Europe/London</option>
                  <option>Europe/Paris</option>
                  <option>Europe/Berlin</option>
                  <option>Asia/Tokyo</option>
                  <option>Asia/Singapore</option>
                  <option>Australia/Sydney</option>
                </select>
              </div>

              <div className="rounded-lg bg-blue-50 p-4">
                <p className="text-sm text-blue-900">
                  💡 <strong>Pro tip:</strong> Publish every day at 10:00 AM for maximum reach,
                  then adjust based on your audience analytics
                </p>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-3 pt-6 border-t border-gray-200">
              <button
                type="button"
                onClick={() => router.back()}
                className="px-6 py-2 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 font-medium transition-colors"
                disabled={loading}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="flex-1 px-6 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 font-medium transition-colors disabled:bg-gray-400"
                disabled={loading}
              >
                {loading ? 'Creating...' : 'Create Campaign'}
              </button>
            </div>
          </form>
        </div>

        {/* Info Section */}
        <div className="mt-8 space-y-4">
          <div className="rounded-lg border border-gray-200 bg-white p-6">
            <h3 className="font-semibold text-gray-900 mb-3">What is a Campaign?</h3>
            <ul className="space-y-2 text-sm text-gray-600">
              <li>✓ Organize related videos into groups</li>
              <li>✓ Automatically schedule detected clips for publishing</li>
              <li>✓ Control publish frequency and timing</li>
              <li>✓ Track performance across multiple videos</li>
            </ul>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-6">
            <h3 className="font-semibold text-gray-900 mb-3">How it works</h3>
            <ol className="space-y-2 text-sm text-gray-600">
              <li>1. Create a campaign and set your publishing schedule</li>
              <li>2. Upload videos to the campaign</li>
              <li>3. ClipMind detects high-quality clips and auto-schedules them</li>
              <li>4. Clips are ready to publish to TikTok, Instagram, YouTube Shorts</li>
            </ol>
          </div>
        </div>
      </div>
    </main>
  );
}
