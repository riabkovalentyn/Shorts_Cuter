import fs from 'node:fs';
import path from 'node:path';
import axios from 'axios';
import ytdl from 'ytdl-core';
import { spawn, spawnSync } from 'node:child_process';

const storageDir = process.env.STORAGE_DIR || path.resolve(__dirname, '..', '..', 'storage');
const downloadsDir = path.join(storageDir, 'downloads');
const binDir = path.join(storageDir, 'bin');

function ensureDirs() {
  fs.mkdirSync(downloadsDir, { recursive: true });
  fs.mkdirSync(binDir, { recursive: true });
}

export const ingestService = {
  async getYtDlpPath(): Promise<string | null> {
    // Prefer system yt-dlp if present
    const sys = spawnSync('yt-dlp', ['--version'], { stdio: 'ignore' });
    if (sys.status === 0) return 'yt-dlp';

    // Try local cached binary under storage/bin
    const exeName = process.platform === 'win32' ? 'yt-dlp.exe' : 'yt-dlp';
    const localPath = path.join(binDir, exeName);
    if (fs.existsSync(localPath)) return localPath;

    // Attempt to download latest binary
    const url = process.platform === 'win32'
      ? 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe'
      : 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp';
    try {
      const resp = await axios.get(url, { responseType: 'stream' });
      await new Promise<void>((resolve, reject) => {
        const ws = fs.createWriteStream(localPath);
        resp.data.pipe(ws);
        ws.on('finish', resolve);
        ws.on('error', reject);
      });
      if (process.platform !== 'win32') {
        try { fs.chmodSync(localPath, 0o755); } catch {}
      }
      return localPath;
    } catch {
      return null;
    }
  },
  async download(sourceUrl: string, jobId: string): Promise<string> {
    ensureDirs();
    const outPath = path.join(downloadsDir, `${jobId}.mp4`);
    // Try YouTube first if URL matches, else HTTP stream
    try {
      if (ytdl.validateURL(sourceUrl)) {
        const ytDlpPath = await this.getYtDlpPath();
        if (ytDlpPath) {
          console.log(`[ingest] Using yt-dlp (${ytDlpPath}) to download YouTube video`);
          await new Promise<void>((resolve, reject) => {
            const args = [
              '--no-playlist',
              '-f', 'bv*+ba/b',
              '--merge-output-format', 'mp4',
              '-o', outPath,
              sourceUrl,
            ];
            const cp = spawn(ytDlpPath, args, { stdio: ['ignore', 'pipe', 'pipe'] });
            let stderr = '';
            cp.stderr.on('data', (d) => (stderr += d.toString()));
            cp.on('error', (e) => reject(e));
            cp.on('close', (code) => {
              if (code === 0) return resolve();
              reject(new Error(`yt-dlp failed with code ${code}. ${stderr || ''}`));
            });
          });
        } else {
          console.log('[ingest] yt-dlp not found, falling back to ytdl-core');
          try {
            const chooseFormat = (formats: any[]) => {
              const mp4 = formats.filter((f: any) => f.container === 'mp4' && f.hasAudio && f.hasVideo);
              if (mp4.length) {
                // pick highest quality mp4
                return mp4.sort((a: any, b: any) => (b.bitrate || 0) - (a.bitrate || 0))[0].itag;
              }
              return 'highest';
            };
            const info = await ytdl.getInfo(sourceUrl);
            const itagOrQuality: any = chooseFormat(info.formats);
            await new Promise<void>((resolve, reject) => {
              ytdl(sourceUrl, { quality: itagOrQuality, filter: 'audioandvideo' })
                .pipe(fs.createWriteStream(outPath))
                .on('finish', () => resolve())
                .on('error', reject);
            });
          } catch (err) {
            throw new Error('YouTube download failed via ytdl-core. Tip: install yt-dlp and ensure it is in PATH (winget install yt-dlp.yt-dlp or choco install yt-dlp).');
          }
        }
      } else {
        console.log('[ingest] HTTP download');
        const response = await axios.get(sourceUrl, { responseType: 'stream' });
        await new Promise<void>((resolve, reject) => {
          const stream = response.data.pipe(fs.createWriteStream(outPath));
          stream.on('finish', () => resolve());
          stream.on('error', reject);
        });
      }
      const stat = fs.statSync(outPath);
      if (!stat.size || stat.size < 1024) {
        throw new Error('Downloaded file is too small');
      }
    } catch (e) {
      // Clean up and bubble the error to mark job failed
      if (fs.existsSync(outPath)) fs.unlinkSync(outPath);
      const hint = ytdl.validateURL(sourceUrl)
        ? ' Tip: install yt-dlp and ensure it is in PATH (winget install yt-dlp.yt-dlp or choco install yt-dlp).'
        : '';
      const msg = (e as any)?.message || String(e);
      throw new Error(`${msg}${hint}`);
    }
    return outPath;
  },
};
