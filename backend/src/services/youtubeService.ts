import Clip from '../models/Clip';
import Token from '../models/Token';

export async function getAuthUrl(): Promise<string> {
  // Placeholder URL; to be replaced with real OAuth2 client auth URL
  return 'https://accounts.google.com/o/oauth2/v2/auth?...';
}

export async function handleOAuthCallback(code: string) {
  // Placeholder: store fake refresh token
  const doc = await Token.findOneAndUpdate(
    { provider: 'youtube' },
    { provider: 'youtube', refreshToken: `refresh_${code}` },
    { upsert: true, new: true }
  );
  return { ok: true, tokenId: doc._id };
}

export async function uploadClipToYouTube(clip: any) {
  // Placeholder: mark uploaded without calling YouTube API
  const updated = await Clip.findByIdAndUpdate(
    clip._id,
    { status: 'uploaded', youtube: { id: `fake_${clip._id}`, publishedAt: new Date().toISOString() } },
    { new: true }
  ).lean();
  return updated;
}
