import mongoose, { Schema, InferSchemaType } from 'mongoose';

const ClipSchema = new Schema({
  jobId: { type: Schema.Types.ObjectId, ref: 'Job', index: true },
  filePath: { type: String, required: true },
  thumbPath: { type: String },
  title: { type: String },
  description: { type: String },
  hashtags: { type: [String], default: [] },
  status: { type: String, enum: ['ready', 'uploaded', 'error'], default: 'ready' },
  youtube: {
    id: { type: String },
    publishedAt: { type: String },
  },
});

export type ClipDoc = InferSchemaType<typeof ClipSchema> & { _id: string };

export default mongoose.model('Clip', ClipSchema);
