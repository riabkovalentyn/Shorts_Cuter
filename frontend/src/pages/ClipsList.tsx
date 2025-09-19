import { useEffect, useState } from 'react';
import { listClips, uploadClip } from '../lib/api';
import ClipCard from '../shared/ClipCard';

function useQuery() {
  const params = new URLSearchParams(window.location.search);
  return Object.fromEntries(params.entries());
}

export default function ClipsList() {
  const { jobId } = useQuery() as { jobId?: string };
  const [clips, setClips] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const data = await listClips(jobId);
      setClips(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  async function onUpload(id: string) {
    await uploadClip(id);
    await refresh();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <h2 className="text-xl font-semibold">Clips {jobId ? <span className="text-slate-500 text-base">(job {jobId})</span> : ''}</h2>
        <button onClick={refresh} className="btn btn-ghost">Refresh</button>
      </div>
      {loading && <div className="text-slate-500">Loading...</div>}
      {clips.length === 0 && !loading && (
        <div className="card">
          <div className="card-body text-slate-600">No clips yet. Create a project on the Dashboard.</div>
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {clips.map((c) => (
          <ClipCard key={c._id} clip={c} onUpload={() => onUpload(c._id)} />
        ))}
      </div>
    </div>
  );
}
