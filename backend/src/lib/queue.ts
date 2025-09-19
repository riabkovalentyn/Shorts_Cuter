import { Queue, Worker, QueueEvents, JobsOptions, Job } from 'bullmq';

let queue: Queue | null = null;
let worker: Worker | null = null;
let events: QueueEvents | null = null;

function getConnection() {
  const url = process.env.REDIS_URL;
  if (!url) return null;
  return { connection: { url } } as const;
}

export function getIngestQueue(): Queue | null {
  if (queue) return queue;
  const conn = getConnection();
  if (!conn) return null;
  queue = new Queue('ingest', { ...conn });
  events = new QueueEvents('ingest', { ...conn });
  return queue;
}

export function initIngestWorker(processor: (data: any) => Promise<void>) {
  const conn = getConnection();
  if (!conn) return null;
  if (worker) return worker;
  worker = new Worker('ingest', async (job: Job) => {
    await processor(job.data);
  }, { ...(conn as any), concurrency: 1 });
  worker.on('ready', () => console.log('[queue] ingest worker ready'));
  worker.on('failed', (job: Job | undefined, err: Error) => console.error('[queue] job failed', job?.id, err?.message));
  worker.on('completed', (job: Job) => console.log('[queue] job completed', job?.id));
  return worker;
}

export async function enqueueIngest(data: { jobId: string; sourceUrl: string; clipLengthSec: number }, opts?: JobsOptions) {
  const q = getIngestQueue();
  if (!q) return null;
  return q.add('ingest', data, {
    removeOnComplete: 100,
    removeOnFail: 100,
    attempts: 1,
    ...(opts || {}),
  });
}
