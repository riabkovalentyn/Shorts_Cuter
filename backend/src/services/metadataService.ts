import Clip from '../models/Clip';

export const metadataService = {
  async populate(clips: Array<{ _id: string } | any>) {
    for (let i = 0; i < clips.length; i++) {
      const title = `Epic Moment #${i + 1} | Shorts`;
      const description = `Auto-generated description for clip ${i + 1}.`;
      const hashtags = ['#Shorts', '#Gaming', '#stream'];
      await Clip.findByIdAndUpdate(clips[i]._id, { title, description, hashtags });
    }
  },
};
