import mongoose, { Schema, InferSchemaType } from 'mongoose';

const TokenSchema = new Schema({
  provider: { type: String, required: true, index: true },
  refreshToken: { type: String, required: true },
  accessToken: { type: String },
  scope: { type: String },
  tokenType: { type: String },
  expiryDate: { type: Number },
  createdAt: { type: Date, default: Date.now },
  updatedAt: { type: Date, default: Date.now },
});

export type TokenDoc = InferSchemaType<typeof TokenSchema> & { _id: string };

export default mongoose.model('Token', TokenSchema);
