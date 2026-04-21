/**
 * File: app/campaigns/[id]/page.tsx
 * Purpose: Campaign management page - view details, upload videos, manage schedule.
 */

'use client';

import { useParams, useRouter } from 'next/navigation';
import { useState, useEffect } from 'react';
import { useSession } from 'next-auth/react';
import { getCampaign, getCampaignStats, type Campaign, type CampaignStats } from '@/lib/api';
import BatchUploadForm from '@/components/batch-upload-form';
import CampaignCalendar from '@/components/campaign-calendar';

export default function CampaignPage() {
  const router = useRouter();
  const params = useParams();
  const { data: session, status } = useSession();
  const campaignId = params?.id as string;

  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [stats, setStats] = useState<CampaignStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/login');
    }
  }, [status, router]);

  useEffect(() => {
    if (status === 'authenticated' && session?.user && campaignId) {
      loadCampaignData();
    }
  }, [status, session?.user, campaignId]);

  async function loadCampaignData() {
    try {
      setLoading(true);
      const userId = session?.user?.id || session?.user?.email || '';
      const [campaignData, statsData] = await Promise.all([
        getCampaign(campaignId, userId),
        getCampaignStats(campaignId, userId),
      ]);
      setCampaign(campaignData);
      setStats(statsData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load campaign');
    } finally {
      setLoading(false);
    }
  }

  if (status === 'loading' || loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (status === 'unauthenticated' || !session?.user) {
    return null;
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 p-8">
        <div className="rounded-lg bg-red-50 p-4">
          <p className="text-red-900">{error}</p>
        </div>
      </div>
    );
  }

  if (!campaign) {
    return null;
  }

  const userId = session.user.id || session.user.email || '';

  return (
    <main className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">{campaign.name}</h1>
              {campaign.description && (
                <p className="mt-2 text-gray-600">{campaign.description}</p>
              )}
            </div>
            <span
              className={`px-4 py-2 rounded-full font-semibold text-sm ${
                campaign.status === 'active'
                  ? 'bg-green-100 text-green-800'
                  : campaign.status === 'paused'
                    ? 'bg-yellow-100 text-yellow-800'
                    : 'bg-gray-100 text-gray-800'
              }`}
            >
              {campaign.status}
            </span>
          </div>
        </div>

        {/* Breadcrumb */}
        <div className="mb-6 flex items-center gap-2 text-sm text-gray-600">
          <a href="/campaigns" className="text-blue-600 hover:text-blue-700 font-medium">
            Campaigns
          </a>
          <span>/</span>
          <span className="text-gray-900 font-medium">{campaign.name}</span>
        </div>

        {/* Stats */}
        {stats && (
          <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <div className="text-3xl font-bold text-blue-600">
                {stats.total_videos_uploaded}
              </div>
              <div className="text-sm text-gray-600">Videos Uploaded</div>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <div className="text-3xl font-bold text-blue-600">
                {stats.total_clips_detected}
              </div>
              <div className="text-sm text-gray-600">Clips Detected</div>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <div className="text-3xl font-bold text-blue-600">
                {stats.clips_scheduled}
              </div>
              <div className="text-sm text-gray-600">Scheduled for Publishing</div>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <div className="text-3xl font-bold text-blue-600">
                {stats.avg_clip_score.toFixed(1)}
              </div>
              <div className="text-sm text-gray-600">Avg Clip Score</div>
            </div>
          </div>
        )}

        {/* Main content - two column layout */}
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          {/* Left column - Upload */}
          <div className="lg:col-span-1">
            <BatchUploadForm
              campaignId={campaignId}
              userId={userId}
              onUploadComplete={loadCampaignData}
            />
          </div>

          {/* Right column - Calendar */}
          <div className="lg:col-span-2">
            <CampaignCalendar
              campaignId={campaignId}
              userId={userId}
              daysAhead={30}
            />
          </div>
        </div>

        {/* Help section */}
        <div className="mt-8 rounded-lg border border-gray-200 bg-blue-50 p-6">
          <h3 className="font-semibold text-blue-900">💡 Campaign Tips</h3>
          <ul className="mt-3 list-inside space-y-2 text-sm text-blue-900">
            <li>• Upload multiple videos at once and ClipMind will process them automatically</li>
            <li>• Each video generates up to 3 clips with optimized scores</li>
            <li>• Clips are automatically scheduled based on your campaign settings</li>
            <li>• Adjust scheduling interval in campaign settings (default: 1 clip per day)</li>
            <li>• All clips are ready for direct publishing to TikTok, Instagram, YouTube Shorts</li>
          </ul>
        </div>
      </div>
    </main>
  );
}
