import axios from 'axios';

const baseURL = (import.meta as any).env?.VITE_API_URL || 'http://localhost:4000';
export const api = axios.create({ baseURL: baseURL + '/api' });

/**
 * Resolve a clip asset path against the API origin.
 *
 * The backend returns storage paths as root-relative ("/storage/clips/x.mp4").
 * The frontend is served from a different origin in every setup we ship (Vite
 * on :5173, nginx on :80, GitHub Pages), so using them raw makes the browser
 * request the asset from the frontend and get index.html back.
 */
export function assetUrl(path?: string | null): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  return baseURL + (path.startsWith('/') ? path : '/' + path);
}

export async function createProject(sourceUrl: string, clipLengthSec = 30) {
  const { data } = await api.post('/projects', { sourceUrl, clipLengthSec });
  return data as { jobId: string; status: string };
}

export async function getJob(id: string) {
  const { data } = await api.get(`/jobs/${id}`);
  return data;
}

export async function listClips(jobId?: string) {
  const { data } = await api.get('/clips', { params: { jobId } });
  return data;
}

export async function uploadClip(clipId: string) {
  const { data } = await api.post(`/clips/${clipId}/upload`);
  return data;
}

export async function getYouTubeAuthUrl() {
  const { data } = await api.get('/auth/youtube/url');
  return data.url as string;
}

export async function getYouTubeStatus() {
  const { data } = await api.get('/auth/youtube/status');
  return data as { configured: boolean; connected: boolean };
}
