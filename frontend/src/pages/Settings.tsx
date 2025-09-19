import { useState } from 'react';
import { getYouTubeAuthUrl } from '../lib/api';

export default function Settings() {
  const [authUrl, setAuthUrl] = useState<string | null>(null);

  async function fetchUrl() {
    const url = await getYouTubeAuthUrl();
    setAuthUrl(url);
    window.location.href = url;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">YouTube OAuth</h2>
      <div className="card">
        <div className="card-body space-y-3">
          <p className="text-slate-600">Connect your YouTube account to enable direct uploads from the app.</p>
          <button onClick={fetchUrl} className="btn btn-danger">Connect YouTube</button>
          {authUrl && <div className="text-sm break-all text-slate-500">Auth URL: {authUrl}</div>}
        </div>
      </div>
    </div>
  );
}
