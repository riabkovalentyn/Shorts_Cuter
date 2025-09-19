import Job from '../models/Job';
import { ingestService } from '../services/ingestService';
import { ffmpegService } from '../services/ffmpegService';
import { metadataService } from '../services/metadataService';
import { highlightService } from '../services/highlightService';
import { enqueueIngest, initIngestWorker } from '../lib/queue';

export async function ingestProject(input: { sourceUrl: string; clipLengthSec: number }) {
  const job = await Job.create({ sourceUrl: input.sourceUrl, status: 'processing' });

  const useQueue = Boolean(process.env.REDIS_URL);
  if (useQueue) {
    // Ensure worker is started once per process
    initIngestWorker(async (data) => {
      const { jobId, sourceUrl, clipLengthSec } = data as { jobId: string; sourceUrl: string; clipLengthSec: number };
      try {
        const videoPath = await ingestService.download(sourceUrl, jobId);
        const windows = await highlightService.detectHighlights(videoPath, { clipLengthSec, maxClips: 10 });
        const clips = windows.length
          ? await ffmpegService.sliceWindows(videoPath, { windows, jobId })
          : await ffmpegService.slice(videoPath, { clipLengthSec, jobId });
        await metadataService.populate(clips);
        await Job.findByIdAndUpdate(jobId, { status: 'done' });
      } catch (e: any) {
        await Job.findByIdAndUpdate(jobId, { status: 'error', error: e?.message || 'error' });
        console.error('Ingest pipeline failed', e);
      }
    });
    await enqueueIngest({ jobId: job.id, sourceUrl: input.sourceUrl, clipLengthSec: input.clipLengthSec });
  } else {
    // Fire-and-forget async pipeline (MVP fallback)
    (async () => {
      try {
        const videoPath = await ingestService.download(input.sourceUrl, job.id);
        const windows = await highlightService.detectHighlights(videoPath, { clipLengthSec: input.clipLengthSec, maxClips: 10 });
        const clips = windows.length
          ? await ffmpegService.sliceWindows(videoPath, { windows, jobId: job.id })
          : await ffmpegService.slice(videoPath, { clipLengthSec: input.clipLengthSec, jobId: job.id });
        await metadataService.populate(clips);
        await Job.findByIdAndUpdate(job.id, { status: 'done' });
      } catch (e: any) {
        await Job.findByIdAndUpdate(job.id, { status: 'error', error: e?.message || 'error' });
        console.error('Ingest pipeline failed', e);
      }
    })();
  }

  return job;
}
