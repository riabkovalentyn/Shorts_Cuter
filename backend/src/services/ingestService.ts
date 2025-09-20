import fs from 'node:fs';
import path from 'node:path';
import axios from 'axios';
import ytdl from 'ytdl-core';
import { spawn, spawnSync } from 'node:child_process';
import { Readable } from 'node:stream';

const storageDir = process.env.STORAGE_DIR || path.resolve(__dirname, '..', '..', '..', 'storage');
const downloadsDir = path.join(storageDir, 'downloads');
const binDir = path.join(storageDir, 'bin');
let ffmpegBin: string | undefined;
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const ff = require('@ffmpeg-installer/ffmpeg');
  if (ff?.path) ffmpegBin = ff.path as string;
} catch {}

function ensureDirs() {
  fs.mkdirSync(downloadsDir, { recursive: true });
  fs.mkdirSync(binDir, { recursive: true });
}

export const ingestService = {
  _spawnWithWatch(cmd: string, args: string[], opts: { idleTimeoutMs?: number } = {}) {
    const idleTimeoutMs = opts.idleTimeoutMs ?? 900_000; // 15 minutes idle watchdog for large files
    return new Promise<void>((resolve, reject) => {
      const cp = spawn(cmd, args, { stdio: ['ignore', 'ignore', 'pipe'] });
      let stderr = '';
      let lastProgress = Date.now();
      const timer = setInterval(() => {
        if (Date.now() - lastProgress > idleTimeoutMs) {
          try { cp.kill('SIGKILL'); } catch {}
          clearInterval(timer);
          return reject(new Error(`Download stalled for more than ${Math.round(idleTimeoutMs/1000)}s`));
        }
      }, Math.min(30_000, Math.max(5_000, Math.floor(idleTimeoutMs / 3))));
      cp.stderr.on('data', (d) => {
        const s = d.toString();
        stderr += s;
        // Heuristic: progress lines for yt-dlp and ffmpeg postprocessing
        if (/\b(\d{1,3}\.\d%|ETA|Downloading fragment|Downloading video|frame=\s*\d+|time=\s*\d+:\d+:\d+\.\d+|speed=\s*\S+|Merging formats|Destination:)/.test(s)) {
          lastProgress = Date.now();
        }
      });
      cp.on('error', (e) => {
        clearInterval(timer);
        reject(e);
      });
      cp.on('close', (code) => {
        clearInterval(timer);
        if (code === 0) return resolve();
        reject(new Error(`yt-dlp failed with code ${code}. ${stderr || ''}`));
      });
    });
  },
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
  const baseNoExt = path.join(downloadsDir, `${jobId}`);
    // Try YouTube first if URL matches, else HTTP stream
    try {
      if (ytdl.validateURL(sourceUrl)) {
        const ytDlpPath = await this.getYtDlpPath();
        if (ytDlpPath) {
          console.log(`[ingest] Using yt-dlp (${ytDlpPath}) to download YouTube video`);
          let firstError: any = null;
          // Attempt 1: prefer progressive mp4 or mp4+m4a to minimize postprocessing issues
          try {
            const args = [
              '--no-playlist',
              '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
              // Robustness flags for large videos / flaky networks
              '-R', '20', // retries
              '--fragment-retries', '20',
              '--socket-timeout', '15',
              '--retry-sleep', '1:2:10',
              '--concurrent-fragments', '5',
              '-o', `${baseNoExt}.%(ext)s`,
              sourceUrl,
            ];
            if (ffmpegBin) args.unshift(ffmpegBin), args.unshift('--ffmpeg-location');
            await this._spawnWithWatch(ytDlpPath, args, { idleTimeoutMs: 900_000 }); // up to 15 min idle
          } catch (e) {
            firstError = e;
            // Attempt 2: simple best with recode to mp4 to guarantee a usable container
            const args = [
              '--no-playlist',
              '-f', 'best',
              '--recode-video', 'mp4',
              // Robust flags as above
              '-R', '20',
              '--fragment-retries', '20',
              '--socket-timeout', '15',
              '--retry-sleep', '1:2:10',
              '--concurrent-fragments', '5',
              '-o', `${baseNoExt}.%(ext)s`,
              sourceUrl,
            ];
            if (ffmpegBin) args.unshift(ffmpegBin), args.unshift('--ffmpeg-location');
            await this._spawnWithWatch(ytDlpPath, args, { idleTimeoutMs: 900_000 }).catch(() => { throw firstError; });
          }
          // Detect actual output path (prefer mp4)
          const candidates = ['mp4', 'mkv', 'webm', 'mov', 'm4v'].map((ext) => `${baseNoExt}.${ext}`);
          const found = candidates.find((p) => fs.existsSync(p));
          if (found) {
            // proceed with found path
          } else {
            // As a fallback, find any file starting with jobId.* in downloads dir
            const files = fs.readdirSync(downloadsDir).filter((f) => f.startsWith(`${jobId}.`));
            if (files.length) {
              // use the first file
              // eslint-disable-next-line @typescript-eslint/no-unused-vars
              const _picked = files[0];
            } else {
              throw new Error('yt-dlp completed but output file was not found');
            }
          }
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
              const idleTimeoutMs = 180_000; // 3m
              const out = fs.createWriteStream(`${baseNoExt}.mp4`);
              const stream = ytdl(sourceUrl, { quality: itagOrQuality, filter: 'audioandvideo', highWaterMark: 1 << 25 });
              let lastData = Date.now();
              const timer = setInterval(() => {
                if (Date.now() - lastData > idleTimeoutMs) {
                  try { stream.destroy(new Error(`ytdl stalled for ${Math.round(idleTimeoutMs/1000)}s`)); } catch {}
                }
              }, 30_000);
              stream.on('data', () => { lastData = Date.now(); });
              stream.on('error', (e) => { clearInterval(timer); reject(e); });
              out.on('error', (e) => { clearInterval(timer); reject(e); });
              out.on('finish', () => { clearInterval(timer); resolve(); });
              stream.pipe(out);
            });
          } catch (err) {
            throw new Error('YouTube download failed via ytdl-core. Tip: install yt-dlp and ensure it is in PATH (winget install yt-dlp.yt-dlp or choco install yt-dlp).');
          }
        }
      } else {
        console.log('[ingest] HTTP download');
        const response = await axios.get(sourceUrl, { responseType: 'stream', timeout: 120_000, maxBodyLength: Infinity, maxContentLength: Infinity });
        await new Promise<void>((resolve, reject) => {
          const idleTimeoutMs = 180_000; // 3m
          const out = fs.createWriteStream(`${baseNoExt}.mp4`);
          const rs = response.data as Readable;
          let lastData = Date.now();
          const timer = setInterval(() => {
            if (Date.now() - lastData > idleTimeoutMs) {
              try { rs.destroy(new Error(`HTTP download stalled for ${Math.round(idleTimeoutMs/1000)}s`)); } catch {}
            }
          }, 30_000);
          rs.on('data', () => { lastData = Date.now(); });
          rs.on('error', (e) => { clearInterval(timer); reject(e); });
          out.on('error', (e) => { clearInterval(timer); reject(e); });
          out.on('finish', () => { clearInterval(timer); resolve(); });
          rs.pipe(out);
        });
      }
      // Determine actual output path
      let actualOutPath: string | null = null;
      const prefer = ['mp4', 'mkv', 'webm', 'mov', 'm4v'];
      for (const ext of prefer) {
        const p = `${baseNoExt}.${ext}`;
        if (fs.existsSync(p)) { actualOutPath = p; break; }
      }
      if (!actualOutPath) {
        const files = fs.readdirSync(downloadsDir)
          .filter((f) => f.startsWith(`${jobId}.`))
          .map((f) => path.join(downloadsDir, f));
        if (files.length) actualOutPath = files[0];
      }
      if (!actualOutPath) throw new Error('Download finished but file not found');
      // Clean up temporary fragment files like <jobId>.f251, <jobId>.f308, etc.
      try {
        const frags = fs.readdirSync(downloadsDir).filter((f) => f.startsWith(`${jobId}.f`));
        for (const f of frags) {
          try { fs.unlinkSync(path.join(downloadsDir, f)); } catch {}
        }
      } catch {}
      const stat = fs.statSync(actualOutPath);
      if (!stat.size || stat.size < 1024) {
        throw new Error('Downloaded file is too small');
      }

      // If file is not mp4, transcode to mp4 to normalize pipeline
      if (!/\.mp4$/i.test(actualOutPath)) {
        const normalizedMp4 = `${baseNoExt}.mp4`;
        const ffmpeg = require('fluent-ffmpeg');
        // Apply installer paths if present
        try {
          const ff = require('@ffmpeg-installer/ffmpeg');
          if (ff?.path) ffmpeg.setFfmpegPath(ff.path);
          const fp = require('@ffprobe-installer/ffprobe');
          if (fp?.path) ffmpeg.setFfprobePath(fp.path);
        } catch {}
        await new Promise<void>((resolve, reject) => {
          ffmpeg(actualOutPath)
            .outputOptions([
              '-c:v libx264',
              '-preset veryfast',
              '-crf 23',
              '-c:a aac',
              '-b:a 128k',
              '-movflags +faststart',
              '-y',
            ])
            .output(normalizedMp4)
            .on('end', () => resolve())
            .on('error', (e: any) => reject(e))
            .run();
        });
        actualOutPath = normalizedMp4;
      }
    } catch (e) {
      // Clean up and bubble the error to mark job failed
      // Try to remove any partial files
      try {
        const partials = fs.readdirSync(downloadsDir).filter((f) => f.startsWith(`${jobId}.`));
        for (const f of partials) {
          try { fs.unlinkSync(path.join(downloadsDir, f)); } catch {}
        }
      } catch {}
      const hint = ytdl.validateURL(sourceUrl)
        ? ' Tip: install yt-dlp and ensure it is in PATH (winget install yt-dlp.yt-dlp or choco install yt-dlp).'
        : '';
      const msg = (e as any)?.message || String(e);
      throw new Error(`${msg}${hint}`);
    }
    // Return the best available path
    for (const ext of ['mp4', 'mkv', 'webm', 'mov', 'm4v']) {
      const p = `${baseNoExt}.${ext}`;
      if (fs.existsSync(p)) return p;
    }
    // Fallback: pick any file matching jobId.*
    const leftovers = fs.readdirSync(downloadsDir).filter((f) => f.startsWith(`${jobId}.`));
    if (leftovers.length) return path.join(downloadsDir, leftovers[0]);
    // Should not happen
    throw new Error('Download finished but output file not found');
  },
};
