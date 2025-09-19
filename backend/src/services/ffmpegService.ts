import fs from 'node:fs';
import path from 'node:path';
import ffmpeg from 'fluent-ffmpeg';
// Try to set ffmpeg/ffprobe paths from installer packages when available
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const ffmpegInstaller = require('@ffmpeg-installer/ffmpeg');
  if (ffmpegInstaller?.path) ffmpeg.setFfmpegPath(ffmpegInstaller.path);
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const ffprobeInstaller = require('@ffprobe-installer/ffprobe');
  if (ffprobeInstaller?.path) ffmpeg.setFfprobePath(ffprobeInstaller.path);
} catch {}
import Clip from '../models/Clip';

const storageDir = process.env.STORAGE_DIR || path.resolve(__dirname, '..', '..', '..', 'storage');
const clipsDir = path.join(storageDir, 'clips');

function toPublicPath(absPath: string) {
  // Convert absolute storage path to /storage-relative URL path
  const rel = absPath.replace(storageDir + path.sep, '').replace(/\\/g, '/');
  return `/storage/${rel}`;
}

function ensureDirs() {
  fs.mkdirSync(clipsDir, { recursive: true });
}

export const ffmpegService = {
  async sliceWindows(inputPath: string, opts: { windows: Array<{ start: number; duration: number; score?: number }>; jobId: string }) {
    ensureDirs();
    const clipDocs: any[] = [];
    for (let i = 0; i < opts.windows.length; i++) {
      const { start, duration, score } = opts.windows[i];
      if (duration < 0.5) continue;
      const base = `${opts.jobId}_${i}`;
      const clipPath = path.join(clipsDir, `${base}.mp4`);
      const thumbPath = path.join(clipsDir, `${base}.jpg`);
      try {
        await new Promise<void>((resolve, reject) => {
          ffmpeg(inputPath)
            .inputOptions([`-ss ${start.toFixed(3)}`])
            .outputOptions([
              `-t ${duration.toFixed(3)}`,
              '-c:v libx264',
              '-preset veryfast',
              '-crf 23',
              '-c:a aac',
              '-b:a 128k',
              '-movflags +faststart',
              '-y',
            ])
            .output(clipPath)
            .on('end', () => resolve())
            .on('error', (err) => reject(err))
            .run();
        });
      } catch (err: any) {
        const msg = String(err?.message || err);
        if (/does not contain any stream/i.test(msg) || /Invalid argument/i.test(msg)) continue;
        throw err;
      }
      const thumbTime = Math.max(0.5, Math.min(1, duration / 2));
      await new Promise<void>((resolve, reject) => {
        ffmpeg(clipPath)
          .inputOptions([`-ss ${thumbTime.toFixed(3)}`])
          .frames(1)
          .output(thumbPath)
          .on('end', () => resolve())
          .on('error', (err) => reject(err))
          .run();
      });
      const doc = await Clip.create({
        jobId: opts.jobId,
        index: i,
        startSec: start,
        durationSec: duration,
        score: score ?? null,
        filePath: clipPath,
        thumbPath,
        title: `Clip ${i + 1}`,
        description: `Auto-generated clip ${i + 1}`,
        hashtags: ['#Shorts', '#stream'],
      });
      clipDocs.push(doc);
    }
    return clipDocs;
  },
  async slice(inputPath: string, opts: { clipLengthSec: number; jobId: string }) {
    ensureDirs();
    const clipLength = Math.max(5, opts.clipLengthSec);

    // Ensure ffmpeg/ffprobe binaries are available
    const ensureBinaries = async () => {
      // Allow override via env vars
      if (process.env.FFMPEG_PATH) ffmpeg.setFfmpegPath(process.env.FFMPEG_PATH);
      if (process.env.FFPROBE_PATH) ffmpeg.setFfprobePath(process.env.FFPROBE_PATH);
      await new Promise<void>((resolve, reject) => {
        ffmpeg.getAvailableFormats((err) => {
          if (err) return reject(err);
          resolve();
        });
      }).catch(() => {
        throw new Error('ffmpeg/ffprobe not found. Install FFmpeg and ensure ffmpeg/ffprobe are in PATH. Windows: choco install ffmpeg or download from https://www.gyan.dev/ffmpeg/builds/.');
      });
    };
    await ensureBinaries();

    // Probe duration
    const durationSec: number = await new Promise((resolve, reject) => {
      ffmpeg.ffprobe(inputPath, (err, data) => {
        if (err) return reject(err);
        const d = Number(data.format?.duration) || 0;
        resolve(d);
      });
    });

    if (!durationSec || durationSec < 1) {
      throw new Error('Input video duration is 0. Check download step or source URL.');
    }

    const clipsCount = Math.max(1, Math.ceil(durationSec / clipLength));
  const clipDocs: any[] = [];

    for (let i = 0; i < clipsCount; i++) {
      const start = i * clipLength;
      // Skip if we're too close to the end (< 0.5s remaining)
      if (start > durationSec - 0.5) break;
      const duration = Math.min(clipLength, durationSec - start);
      if (duration < 0.5) continue;

  const base = `${opts.jobId}_${i}`;
      const clipPath = path.join(clipsDir, `${base}.mp4`);
      const thumbPath = path.join(clipsDir, `${base}.jpg`);

      try {
        await new Promise<void>((resolve, reject) => {
          ffmpeg(inputPath)
            .inputOptions([`-ss ${start.toFixed(3)}`])
            .outputOptions([
              `-t ${duration.toFixed(3)}`,
              '-c:v libx264',
              '-preset veryfast',
              '-crf 23',
              '-c:a aac',
              '-b:a 128k',
              '-movflags +faststart',
              '-y',
            ])
            .output(clipPath)
            .on('end', () => resolve())
            .on('error', (err) => reject(err))
            .run();
        });
      } catch (err: any) {
        const msg = String(err?.message || err);
        // Common near-end seek error: skip this segment instead of failing whole job
        if (/does not contain any stream/i.test(msg) || /Invalid argument/i.test(msg)) {
          continue;
        }
        throw err;
      }

      // Generate thumbnail roughly at 1s into the segment (or halfway if shorter)
      const thumbTime = Math.max(0.5, Math.min(1, duration / 2));
      await new Promise<void>((resolve, reject) => {
        ffmpeg(clipPath)
          .inputOptions([`-ss ${thumbTime.toFixed(3)}`])
          .frames(1)
          .output(thumbPath)
          .on('end', () => resolve())
          .on('error', (err) => reject(err))
          .run();
      });

      const doc = await Clip.create({
        jobId: opts.jobId,
        index: i,
        startSec: start,
        durationSec: duration,
        filePath: clipPath,
        thumbPath,
        // Title/description/hashtags will be enriched by metadataService
        title: `Clip ${i + 1}`,
        description: `Auto-generated clip ${i + 1}`,
        hashtags: ['#Shorts', '#stream'],
      });
      clipDocs.push(doc);
    }

    return clipDocs;
  },
};
