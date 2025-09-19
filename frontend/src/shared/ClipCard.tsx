export default function ClipCard({ clip, onUpload }: { clip: any; onUpload: () => void }) {
  const normalizeRel = (p?: string) => {
    if (!p) return null;
    const idx = p.toLowerCase().lastIndexOf('storage');
    const rel = idx >= 0 ? p.slice(idx + 'storage'.length + 1) : p;
    return rel.replace(/\\/g, '/');
  };
  const thumbRel = normalizeRel(clip.thumbPath);
  const fileRel = normalizeRel(clip.filePath);
  const thumbUrl = thumbRel ? `http://localhost:4000/storage/${thumbRel}` : null;
  const fileUrl = fileRel ? `http://localhost:4000/storage/${fileRel}` : '#';

  return (
    <div className="card overflow-hidden">
      {thumbUrl ? (
        <img src={thumbUrl} alt={clip.title} className="w-full h-44 object-cover" />
      ) : (
        <div className="w-full h-44 bg-slate-200" />
      )}
      <div className="card-body space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="font-semibold line-clamp-1">{clip.title || 'Untitled'}</div>
          <span className={`text-xs px-2 py-0.5 rounded-full ${clip.status === 'uploaded' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>{clip.status}</span>
        </div>
        <div className="text-sm text-slate-600 line-clamp-2">{clip.description}</div>
        <div className="flex flex-wrap gap-1 text-xs text-slate-500">
          {Array.isArray(clip.hashtags) && clip.hashtags.slice(0, 3).map((h: string) => (
            <span key={h} className="px-2 py-0.5 rounded bg-slate-100">{h}</span>
          ))}
        </div>
        <div className="flex gap-3 pt-1">
          <a className="btn btn-ghost" href={fileUrl} target="_blank" rel="noreferrer">Preview</a>
          {clip.status !== 'uploaded' ? (
            <button onClick={onUpload} className="ml-auto btn btn-success">Upload</button>
          ) : (
            <span className="ml-auto text-green-700">Uploaded</span>
          )}
        </div>
      </div>
    </div>
  );
}
