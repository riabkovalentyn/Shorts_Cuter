import fs from 'node:fs';
import path from 'node:path';
import ffmpeg from 'fluent-ffmpeg';
import Clip from '../models/Clip';

const storageDir = process.env.STORAGE_DIR || path.resolve(__dirname, '..', '..', 'storage');
const clipsDir = path.join(storageDir, 'clips');

function ensureDirs() {
  fs.mkdirSync(clipsDir, { recursive: true });
}

export const ffmpegService = {
  async slice(inputPath: string, opts: { clipLengthSec: number; jobId: string }) {
    ensureDirs();
    const clipLength = Math.max(5, opts.clipLengthSec);

    // Ensure ffmpeg/ffprobe binaries are available
    const ensureBinaries = async () => {
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
        const d = data.format?.duration || 0;
        resolve(Math.floor(d));
      });
    });

    if (!durationSec || durationSec < 1) {
      throw new Error('Input video duration is 0. Check download step or source URL.');
    }

    const clipsCount = Math.max(1, Math.floor(durationSec / clipLength));
    const clipDocs: any[] = [];

    for (let i = 0; i < clipsCount; i++) {
      const start = i * clipLength;
      if (start >= durationSec) break;
      const duration = Math.min(clipLength, durationSec - start);

      const base = `${opts.jobId}_${String(i).padStart(2, '0')}`;
      const clipPath = path.join(clipsDir, `${base}.mp4`);
      const thumbPath = path.join(clipsDir, `${base}.jpg`);

      await new Promise<void>((resolve, reject) => {
        ffmpeg(inputPath)
          .inputOptions([`-ss ${start}`])
          .outputOptions([
            `-t ${duration}`,
            '-c:v libx264',
            '-preset veryfast',
            '-crf 23',
            '-c:a aac',
            '-b:a 128k',
            '-movflags +faststart',
          ])
          .output(clipPath)
          .on('end', () => resolve())
          .on('error', (err) => reject(err))
          .run();
      });

      // Generate thumbnail roughly at 1s into the segment (or halfway if shorter)
      const thumbTime = Math.max(0.5, Math.min(1, duration / 2));
      await new Promise<void>((resolve, reject) => {
        ffmpeg(inputPath)
          .inputOptions([`-ss ${start + thumbTime}`])
          .frames(1)
          .output(thumbPath)
          .on('end', () => resolve())
          .on('error', (err) => reject(err))
          .run();
      });

      const doc = await Clip.create({
        jobId: opts.jobId,
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
};
