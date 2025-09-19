import axios from 'axios';

const baseURL = (import.meta as any).env?.VITE_API_URL || 'http://localhost:4000';
export const api = axios.create({ baseURL: baseURL + '/api' });

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
