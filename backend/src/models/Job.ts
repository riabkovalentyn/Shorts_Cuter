import mongoose, { Schema, InferSchemaType } from 'mongoose';

const JobSchema = new Schema({
  sourceUrl: { type: String, required: true },
  status: { type: String, enum: ['pending', 'processing', 'done', 'error'], default: 'pending' },
  error: { type: String },
  createdAt: { type: Date, default: Date.now },
});

export type JobDoc = InferSchemaType<typeof JobSchema> & { _id: string };

export default mongoose.model('Job', JobSchema);
