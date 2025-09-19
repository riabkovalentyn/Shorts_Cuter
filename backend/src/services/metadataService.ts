import Clip from '../models/Clip';
import Job from '../models/Job';

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
      const title = `Epic Moment #${n}${platform ? ` — from ${platform}` : ''}`;
      const description = `Auto-generated clip ${n}.${sourceUrl ? `\nSource: ${sourceUrl}` : ''}\nMade with Shorts Cuter.`;
      const hashtags = Array.from(new Set([...baseTags, '#Gaming']));
      await Clip.findByIdAndUpdate((clips[i] as any)._id, { title, description, hashtags });
    }
  },
};
