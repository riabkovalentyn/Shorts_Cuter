import Job from '../models/Job';
import { ingestService } from '../services/ingestService';
import { ffmpegService } from '../services/ffmpegService';
import { metadataService } from '../services/metadataService';

export async function ingestProject(input: { sourceUrl: string; clipLengthSec: number }) {
  const job = await Job.create({ sourceUrl: input.sourceUrl, status: 'processing' });

  // Fire-and-forget async pipeline (MVP). In production use queue.
  (async () => {
    try {
      const videoPath = await ingestService.download(input.sourceUrl, job.id);
      const clips = await ffmpegService.slice(videoPath, {
        clipLengthSec: input.clipLengthSec,
        jobId: job.id,
      });
      await metadataService.populate(clips);
      await Job.findByIdAndUpdate(job.id, { status: 'done' });
    } catch (e: any) {
      await Job.findByIdAndUpdate(job.id, { status: 'error', error: e?.message || 'error' });
      console.error('Ingest pipeline failed', e);
    }
  })();

  return job;
}
