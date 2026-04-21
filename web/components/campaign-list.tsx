/**
 * File: components/campaign-list.tsx
 * Purpose: Display user's campaigns in a list view with quick actions.
 */

'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { listCampaigns, deleteCampaign, type Campaign } from '@/lib/api';

type CampaignListProps = {
  userId: string;
  onCampaignSelect?: (campaignId: string) => void;
};

export default function CampaignList({
  userId,
  onCampaignSelect,
}: CampaignListProps) {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    loadCampaigns();
  }, [userId]);

  async function loadCampaigns() {
    try {
      setLoading(true);
      const response = await listCampaigns(userId, 50);
      setCampaigns(response.campaigns);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load campaigns');
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(campaignId: string) {
    if (!confirm('Are you sure? This will unlink all associated videos.')) return;

    try {
      setDeleting(campaignId);
      await deleteCampaign(campaignId, userId);
      setCampaigns(campaigns.filter((c) => c.id !== campaignId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete campaign');
    } finally {
      setDeleting(null);
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

  if (campaigns.length === 0) {
    return (
      <div className="rounded-lg border-2 border-dashed border-gray-300 p-8 text-center">
        <p className="text-gray-600">No campaigns yet</p>
        <Link href="/campaigns/new" className="mt-4 text-blue-600 hover:text-blue-700 font-medium">
          Create your first campaign
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {campaigns.map((campaign) => (
        <div
          key={campaign.id}
          className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm hover:border-gray-300 transition-colors"
        >
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <Link
                href={`/campaigns/${campaign.id}`}
                className="text-lg font-semibold text-blue-600 hover:text-blue-700"
              >
                {campaign.name}
              </Link>
              {campaign.description && (
                <p className="mt-1 text-sm text-gray-600">{campaign.description}</p>
              )}
              <div className="mt-3 flex gap-3 text-xs text-gray-500">
                <span>📹 {campaign.clip_count} clips</span>
                <span>📅 {new Date(campaign.created_at).toLocaleDateString()}</span>
                <span
                  className={`px-2 py-1 rounded-full font-medium ${
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
            <div className="ml-4 flex gap-2">
              <Link
                href={`/campaigns/${campaign.id}`}
                className="inline-block rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
              >
                Open
              </Link>
              <button
                onClick={() => handleDelete(campaign.id)}
                disabled={deleting === campaign.id}
                className="rounded-lg bg-red-100 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-200 disabled:bg-gray-100 disabled:text-gray-400 transition-colors"
              >
                {deleting === campaign.id ? '...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
