import fs from 'node:fs';
import path from 'node:path';
import { google } from 'googleapis';
import Clip from '../models/Clip';
import Token from '../models/Token';

function getOAuthClient() {
  const clientId = process.env.GOOGLE_CLIENT_ID;
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET;
  const redirectUri = process.env.YT_REDIRECT_URI || 'http://localhost:4000/api/auth/youtube/callback';
  if (!clientId || !clientSecret) {
    throw new Error('Missing GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET env vars');
  }
  return new google.auth.OAuth2(clientId, clientSecret, redirectUri);
}

export async function getAuthUrl(): Promise<string> {
  const oauth2Client = getOAuthClient();
  const scopes = [
    'https://www.googleapis.com/auth/youtube.upload',
  ];
  const url = oauth2Client.generateAuthUrl({
    access_type: 'offline',
    prompt: 'consent',
    scope: scopes,
  });
  return url;
}

export async function handleOAuthCallback(code: string) {
  const oauth2Client = getOAuthClient();
  const { tokens } = await oauth2Client.getToken(code);
  if (!tokens.refresh_token) {
    throw new Error('No refresh_token received. Ensure you used access_type=offline and prompt=consent.');
  }
  const doc = await Token.findOneAndUpdate(
    { provider: 'youtube' },
    {
      provider: 'youtube',
      refreshToken: tokens.refresh_token,
      accessToken: tokens.access_token,
      scope: tokens.scope,
      tokenType: tokens.token_type,
      expiryDate: tokens.expiry_date,
      updatedAt: new Date(),
    },
    { upsert: true, new: true }
  );
  return { ok: true, tokenId: doc._id };
}

async function getAuthedClient() {
  const doc = await Token.findOne({ provider: 'youtube' }).lean();
  if (!doc?.refreshToken) throw new Error('YouTube not connected: no refresh token stored');
  const oauth2Client = getOAuthClient();
  oauth2Client.setCredentials({ refresh_token: doc.refreshToken });
  return oauth2Client;
}

export async function uploadClipToYouTube(clip: any) {
  const oauth2Client = await getAuthedClient();
  const youtube = google.youtube({ version: 'v3', auth: oauth2Client });

  const filePath: string = clip.filePath;
  if (!filePath || !fs.existsSync(filePath)) throw new Error('Clip file not found');

  const title = clip.title || 'Shorts Clip';
  const description = clip.description || '';
  const tags = Array.isArray(clip.hashtags) ? clip.hashtags.map((h: string) => h.replace(/^#/, '')) : [];

  const res = await youtube.videos.insert({
    part: ['snippet', 'status'],
    requestBody: {
      snippet: { title, description, tags, categoryId: '22' },
      status: { privacyStatus: 'private' },
    },
    media: { body: fs.createReadStream(path.resolve(filePath)) },
  });

  const id = res.data.id || 'unknown';
  const updated = await Clip.findByIdAndUpdate(
    clip._id,
    { status: 'uploaded', youtube: { id, publishedAt: new Date().toISOString() } },
    { new: true }
  ).lean();
  return updated;
}
