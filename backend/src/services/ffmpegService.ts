import fs from 'node:fs';
import path from 'node:path';
import ffmpeg from 'fluent-ffmpeg';
import Clip from '../models/Clip';

const storageDir = process.env.STORAGE_DIR || path.resolve(process.cwd(), 'storage');
const clipsDir = path.join(storageDir, 'clips');

function ensureDirs() {
  fs.mkdirSync(clipsDir, { recursive: true });
}

export const ffmpegService = {
  async slice(inputPath: string, opts: { clipLengthSec: number; jobId: string }) {
    ensureDirs();
    const clipLength = Math.max(5, opts.clipLengthSec);

    // MVP: create 3 placeholder clips regardless of input length
    const clipDocs: any[] = [];
    for (let i = 0; i < 3; i++) {
      const clipPath = path.join(clipsDir, `${opts.jobId}_${i}.mp4`);
      const thumbPath = path.join(clipsDir, `${opts.jobId}_${i}.jpg`);

      // Try to use ffmpeg to extract a segment and a thumbnail; fallback to placeholders
      try {
        await new Promise<void>((resolve, reject) => {
          ffmpeg(inputPath)
            .setStartTime(i * clipLength)
            .setDuration(clipLength)
            .output(clipPath)
            .on('end', () => resolve())
            .on('error', reject)
            .run();
        });
        await new Promise<void>((resolve, reject) => {
          ffmpeg(inputPath)
            .screenshots({ count: 1, timemarks: [i * clipLength + 1], filename: path.basename(thumbPath), folder: clipsDir })
            .on('end', () => resolve())
            .on('error', reject);
        });
      } catch {
        fs.writeFileSync(clipPath, Buffer.alloc(0));
        fs.writeFileSync(thumbPath, Buffer.alloc(0));
      }

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
