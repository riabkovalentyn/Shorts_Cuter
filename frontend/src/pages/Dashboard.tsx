import { useState } from 'react';
import { createProject, getJob } from '../lib/api';
import { useNavigate } from 'react-router-dom';
import { useToasts } from '../shared/Toaster';

export default function Dashboard() {
  const [url, setUrl] = useState('');
  const [len, setLen] = useState(30);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const navigate = useNavigate();
  const { push } = useToasts();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      if (!/^https?:\/\//i.test(url)) {
        push({ kind: 'error', text: 'Please enter a valid http/https URL' });
        return;
      }
      const { jobId } = await createProject(url, len);
      setStatus('processing');
      // simple poll
      const interval = setInterval(async () => {
        const job = await getJob(jobId);
        setStatus(job.status);
        if (job.status === 'done' || job.status === 'error') {
          clearInterval(interval);
          if (job.status === 'done') navigate('/clips?jobId=' + jobId);
        }
      }, 2000);
    } catch (e: any) {
      push({ kind: 'error', text: e?.response?.data?.error || e?.message || 'Failed to create job' });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid md:grid-cols-3 gap-6">
      <div className="md:col-span-2">
        <div className="card">
          <div className="card-body space-y-4">
            <h2 className="text-xl font-semibold">Create new project</h2>
            <form onSubmit={onSubmit} className="space-y-4">
              <div className="space-y-2">
                <label className="label">Stream/Video URL</label>
                <input type="url" placeholder="https://..." className="input w-full" value={url} onChange={(e) => setUrl(e.target.value)} required />
              </div>
              <div className="flex items-center gap-4">
                <label className="label w-40">Clip length (sec)</label>
                <input type="number" className="input w-28" value={len} min={5} onChange={(e) => setLen(Number(e.target.value))} />
              </div>
              <div className="flex gap-3">
                <button disabled={loading} className="btn btn-primary disabled:opacity-50">Create</button>
                {status && <span className="text-sm text-slate-600">Status: {status}</span>}
              </div>
            </form>
          </div>
        </div>
      </div>
      <div className="space-y-4">
        <div className="card">
          <div className="card-body">
            <h3 className="font-semibold mb-2">Tips</h3>
            <ul className="list-disc pl-5 text-sm text-slate-600 space-y-1">
              <li>YouTube links supported (best with yt-dlp installed).</li>
              <li>Direct media URLs (mp4) also work.</li>
              <li>Default clip length is 30 seconds.</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
