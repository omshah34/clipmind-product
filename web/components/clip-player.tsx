export default function ClipPlayer({ clipUrl }: { clipUrl: string }) {
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="player">
        <video controls playsInline preload="metadata" src={clipUrl} />
      </div>
      <a className="subtle-button" download href={clipUrl}>
        Download clip
      </a>
    </div>
  );
}
