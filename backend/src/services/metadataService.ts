import Clip from '../models/Clip';
import Job from '../models/Job';
import path from 'node:path';

export const metadataService = {
  async populate(clips: Array<{ _id: string } | any>) {
    if (!clips.length) return;

    // Try to derive platform from the job's sourceUrl using the first clip's jobId
    let sourceUrl: string | undefined;
    try {
      const firstClip = await Clip.findById((clips[0] as any)._id);
      if (firstClip?.jobId) {
        const job = await Job.findById(firstClip.jobId);
        sourceUrl = job?.sourceUrl;
      }
    } catch {}

    const platform = !sourceUrl ? undefined
      : /youtu\.?be|youtube/.test(sourceUrl) ? 'YouTube'
      : /twitch\.tv/.test(sourceUrl) ? 'Twitch'
      : /vk\.com/.test(sourceUrl) ? 'VK'
      : undefined;

    const baseTags = ['#Shorts', '#Stream'];
    if (platform === 'YouTube') baseTags.push('#YouTube');
    if (platform === 'Twitch') baseTags.push('#Twitch');
    if (platform === 'VK') baseTags.push('#VK');

    for (let i = 0; i < clips.length; i++) {
      const n = i + 1;
      const c = await Clip.findById((clips[i] as any)._id);
      if (!c) continue;

      // Build unique title/description using timing
      const mmss = (s?: number) => {
        if (typeof s !== 'number') return '0:00';
        const m = Math.floor(s / 60);
        const ss = Math.floor(s % 60).toString().padStart(2, '0');
        return `${m}:${ss}`;
      };
      const start = (c as any).startSec as number | undefined;
      const dur = (c as any).durationSec as number | undefined;
      const timing = start != null && dur != null ? `at ${mmss(start)} (${mmss(dur)})` : `part ${n}`;

      const title = `${platform ? `${platform} ` : ''}Highlight ${n} — ${timing}`;
      const description = [
        `Clip ${n} ${timing}.`,
        sourceUrl ? `Source: ${sourceUrl}` : undefined,
        `Generated on ${new Date().toLocaleDateString()} by Shorts Cuter.`,
      ].filter(Boolean).join('\n');

      const specificTags = [
        (platform && `#${platform}`) || undefined,
        start != null ? `#Start_${Math.floor(start)}s` : undefined,
        dur != null ? `#Duration_${Math.floor(dur)}s` : undefined,
        `#Clip${n}`,
      ].filter(Boolean) as string[];
      const hashtags = Array.from(new Set([...baseTags, ...specificTags]));

      await Clip.findByIdAndUpdate((clips[i] as any)._id, { title, description, hashtags });
    }
  },
};
