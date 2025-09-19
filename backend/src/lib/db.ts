import mongoose from 'mongoose';

export async function connectMongo(uri: string) {
  await mongoose.connect(uri, { 
    serverSelectionTimeoutMS: 5000,
  } as any);
  mongoose.connection.on('error', (err) => {
    console.error('Mongo connection error', err);
  });
  return mongoose.connection;
}
