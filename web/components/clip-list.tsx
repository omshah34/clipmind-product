import ClipPlayer from "./clip-player";
import { ClipSummary } from "../lib/api";


export default function ClipList({ clips }: { clips: ClipSummary[] }) {
  return (
    <div className="clip-grid">
      {clips.map((clip) => (
        <article className="clip-tile" key={clip.clip_index}>
          <div className="clip-meta">
            <strong>Clip {clip.clip_index}</strong>
            <span>{clip.duration.toFixed(1)}s</span>
          </div>

          <ClipPlayer clipUrl={clip.clip_url} />

          <p className="clip-reason">{clip.reason}</p>

          <div className="clip-meta">
            <span>Final score</span>
            <strong>{clip.final_score.toFixed(2)}</strong>
          </div>
        </article>
      ))}
    </div>
  );
}
