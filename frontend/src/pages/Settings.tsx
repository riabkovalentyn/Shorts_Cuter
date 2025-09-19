import { useEffect, useState } from 'react';
import { getYouTubeAuthUrl, getYouTubeStatus } from '../lib/api';

export default function Settings() {
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [status, setStatus] = useState<{configured: boolean; connected: boolean} | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getYouTubeStatus().then(setStatus).catch(() => {});
  }, []);

  async function fetchUrl() {
    setError(null);
    try {
      const url = await getYouTubeAuthUrl();
      setAuthUrl(url);
      window.location.href = url;
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || 'Failed to start OAuth');
    }
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">YouTube OAuth</h2>
      <div className="card">
        <div className="card-body space-y-3">
          <p className="text-slate-600">Connect your YouTube account to enable direct uploads from the app.</p>
          {status && (
            <div className="text-sm text-slate-700">Config: {status.configured ? 'OK' : 'Missing envs'} · Connected: {status.connected ? 'Yes' : 'No'}</div>
          )}
          {error && <div className="text-sm text-red-600">{error}</div>}
          <button onClick={fetchUrl} className="btn btn-danger" disabled={status?.configured === false}>
            {status?.configured === false ? 'Config missing' : 'Connect YouTube'}
          </button>
          {authUrl && <div className="text-sm break-all text-slate-500">Auth URL: {authUrl}</div>}
        </div>
      </div>
    </div>
  );
}
