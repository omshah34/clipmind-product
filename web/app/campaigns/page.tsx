/**
 * File: app/campaigns/page.tsx
 * Purpose: Campaigns listing page - view all campaigns, create new, manage.
 */

'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { listCampaigns, deleteCampaign, type Campaign } from '@/lib/api';
import Link from 'next/link';

export default function CampaignsPage() {
  const router = useRouter();
  const { data: session, status } = useSession();

  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/login');
    }
  }, [status, router]);

  useEffect(() => {
    if (status === 'authenticated' && session?.user) {
      loadCampaigns();
    }
  }, [status, session?.user]);

  async function loadCampaigns() {
    try {
      setLoading(true);
      const userId = session?.user?.id || session?.user?.email || '';
      const data = await listCampaigns(userId, 100, 0);
      setCampaigns(data.campaigns);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load campaigns');
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(campaignId: string, campaignName: string) {
    try {
      const userId = session?.user?.id || session?.user?.email || '';
      await deleteCampaign(campaignId, userId);
      setCampaigns((prev) => prev.filter((c) => c.id !== campaignId));
      setDeleteConfirm(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete campaign');
    }
  }

  if (status === 'loading') {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (status === 'unauthenticated' || !session?.user) {
    return null;
  }

  const userId = session.user.id || session.user.email || '';

  return (
    <main className="min-h-screen bg-gradient-to-br from-[#f8fbff] to-[#eef4fb]">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Campaigns</h1>
            <p className="mt-2 text-gray-600">
              Organize videos into campaigns and schedule clips for publishing
            </p>
          </div>
          <Link
            href="/campaigns/new"
            className="inline-flex items-center gap-2 rounded-full bg-blue-600 px-4 py-2 font-semibold text-white hover:bg-blue-700 transition-colors shadow-sm"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 4v16m8-8H4"
              />
            </svg>
            New Campaign
          </Link>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 rounded-2xl bg-red-50 p-4 border border-red-100">
            <p className="text-red-900">{error}</p>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          </div>
        )}

        {/* Empty State */}
        {!loading && campaigns.length === 0 && (
          <div className="rounded-3xl border border-dashed border-gray-300 bg-white/90 p-12 text-center shadow-sm">
            <svg
              className="mx-auto h-12 w-12 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4"
              />
            </svg>
            <h3 className="mt-4 text-lg font-semibold text-gray-900">No campaigns yet</h3>
            <p className="mt-2 text-gray-600">
              Create your first campaign to organize and schedule your video clips
            </p>
            <Link
              href="/campaigns/new"
              className="mt-6 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 font-semibold text-white hover:bg-blue-700 transition-colors"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m8-8H4"
                />
              </svg>
              Create Campaign
            </Link>
          </div>
        )}

        {/* Campaigns Grid */}
        {!loading && campaigns.length > 0 && (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {campaigns.map((campaign) => (
              <div
                key={campaign.id}
                className="overflow-hidden rounded-3xl border border-gray-200 bg-white/90 shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="p-6">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <h3 className="font-semibold text-gray-900">{campaign.name}</h3>
                      {campaign.description && (
                        <p className="mt-1 text-sm text-gray-600 line-clamp-2">
                          {campaign.description}
                        </p>
                      )}
                    </div>
                    <span
                      className={`ml-2 inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
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

                  <div className="mt-4 flex items-center justify-between text-sm text-gray-600">
                    <span>{campaign.clip_count} clips</span>
                    <span>{new Date(campaign.created_at).toLocaleDateString()}</span>
                  </div>

                  <div className="mt-6 flex gap-2">
                    <Link
                      href={`/campaigns/${campaign.id}`}
                      className="flex-1 inline-flex items-center justify-center rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      Open
                    </Link>
                    <button
                      onClick={() => setDeleteConfirm(campaign.id)}
                      className="inline-flex items-center justify-center rounded-lg border border-red-300 px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 transition-colors"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Delete Confirmation Modal */}
        {deleteConfirm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 backdrop-blur-[2px]">
            <div className="max-w-sm mx-auto rounded-3xl bg-white p-6 shadow-xl border border-gray-100">
              <h3 className="text-lg font-semibold text-gray-900">Delete Campaign?</h3>
              <p className="mt-2 text-gray-600">
                This will permanently delete the campaign. Jobs will not be affected, only the
                campaign association will be removed.
              </p>
              <div className="mt-6 flex gap-3 justify-end">
                <button
                  onClick={() => setDeleteConfirm(null)}
                  className="px-4 py-2 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 font-medium"
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    const campaignName = campaigns.find((c) => c.id === deleteConfirm)?.name || '';
                    handleDelete(deleteConfirm, campaignName);
                  }}
                  className="px-4 py-2 rounded-lg bg-red-600 text-white hover:bg-red-700 font-medium"
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
