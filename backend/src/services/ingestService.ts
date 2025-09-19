import fs from 'node:fs';
import path from 'node:path';
import axios from 'axios';

const storageDir = process.env.STORAGE_DIR || path.resolve(process.cwd(), 'storage');
const downloadsDir = path.join(storageDir, 'downloads');

function ensureDirs() {
  fs.mkdirSync(downloadsDir, { recursive: true });
}

export const ingestService = {
  async download(sourceUrl: string, jobId: string): Promise<string> {
    ensureDirs();
    const outPath = path.join(downloadsDir, `${jobId}.mp4`);
    // MVP: if it's a direct mp4 URL, stream to file; otherwise placeholder creates empty file.
    try {
      const response = await axios.get(sourceUrl, { responseType: 'stream' });
      await new Promise<void>((resolve, reject) => {
        const stream = response.data.pipe(fs.createWriteStream(outPath));
        stream.on('finish', () => resolve());
        stream.on('error', reject);
      });
    } catch {
      // Placeholder: create empty file to unblock pipeline in dev
      fs.writeFileSync(outPath, Buffer.alloc(0));
    }
    return outPath;
  },
};
