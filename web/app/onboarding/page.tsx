/**
 * File: web/app/onboarding/page.tsx
 * Purpose: Resolves "No onboarding flow" architecture gap.
 *          Provides guided wizard and value demonstration.
 */

"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth-provider";
import { saveUserPreferences } from "@/lib/api";
import "@/styles/onboarding.css"; // Using pure CSS per requirements

export default function OnboardingWizard() {
  const [step, setStep] = useState(1);
  const router = useRouter();
  const { user } = useAuth();
  const [isSaving, setIsSaving] = useState(false);
  
  const [goals, setGoals] = useState<string[]>([]);
  const [platform, setPlatform] = useState<string>("");

  const handleGoalToggle = (goal: string) => {
    if (goals.includes(goal)) {
      setGoals(goals.filter(g => g !== goal));
    } else {
      setGoals([...goals, goal]);
    }
  };

  const completeOnboarding = async () => {
    if (!user?.id) {
      router.push('/workspaces');
      return;
    }

    setIsSaving(true);
    try {
      await saveUserPreferences(user.id, {
        goals,
        target_platform: platform || null,
        primary_goal: goals[0] || null,
        metadata: {
          audience_platform: platform || null,
        },
        onboarding_completed: true,
      });
    } catch (error) {
      console.error("Failed to save onboarding preferences:", error);
    } finally {
      setIsSaving(false);
      router.push('/workspaces');
    }
  };

  return (
    <div className="onboarding-container">
      <div className="onboarding-card">
        {/* Step Indicator */}
        <div className="step-indicator">
          <div className={`step-dot ${step >= 1 ? 'active' : ''}`} />
          <div className={`step-line ${step >= 2 ? 'active' : ''}`} />
          <div className={`step-dot ${step >= 2 ? 'active' : ''}`} />
          <div className={`step-line ${step >= 3 ? 'active' : ''}`} />
          <div className={`step-dot ${step >= 3 ? 'active' : ''}`} />
        </div>

        {step === 1 && (
          <div className="step-content fade-in">
            <h1>Welcome to ClipMind, {user?.email?.split('@')[0] || "Creator"}! 🚀</h1>
            <p>ClipMind uses advanced "Content DNA" AI to learn your specific editing fingerprint.</p>
            
            <div className="value-prop-box">
              <h3>To get started, what is your primary goal?</h3>
              <div className="goal-options">
                {["Repurpose podcasts", "Grow TikTok organically", "Automate client delivery", "Build a YouTube Shorts funnel"].map(g => (
                  <button 
                    key={g}
                    className={`goal-btn ${goals.includes(g) ? 'selected' : ''}`}
                    onClick={() => handleGoalToggle(g)}
                  >
                    {g}
                  </button>
                ))}
              </div>
            </div>

            <button className="next-btn" onClick={() => setStep(2)}>
              Continue
            </button>
          </div>
        )}

        {step === 2 && (
          <div className="step-content fade-in">
            <h1>Where is your audience? 🌍</h1>
            <p>We'll tune the scoring algorithms (Hook, Emotion, Virality) based on your primary target.</p>
            
            <div className="platform-options">
              {["TikTok", "Instagram Reels", "YouTube Shorts", "LinkedIn"].map(p => (
                <button 
                  key={p}
                  className={`platform-btn ${platform === p ? 'selected' : ''}`}
                  onClick={() => setPlatform(p)}
                >
                  {p}
                </button>
              ))}
            </div>

            <div className="nav-buttons">
              <button className="back-btn" onClick={() => setStep(1)}>Back</button>
              <button className="next-btn" onClick={() => setStep(3)} disabled={!platform}>
                Next Step
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="step-content fade-in">
            <h1>You're All Set! 🎉</h1>
            <div className="summary-box">
              <p>We've initialized your <strong>Content DNA</strong> profile.</p>
              <ul>
                <li><strong>Target:</strong> {platform}</li>
                <li><strong>Goals:</strong> {goals.length > 0 ? goals.join(", ") : "General AI editing"}</li>
              </ul>
              <p style={{marginTop: 15, fontSize: "0.9rem", color: "var(--muted)"}}>
                 Upload your first video to start collecting signals and teaching the AI your style.
              </p>
            </div>

            <button className="start-app-btn pulse" onClick={completeOnboarding} disabled={isSaving}>
              {isSaving ? "Saving..." : "Go to Dashboard"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
