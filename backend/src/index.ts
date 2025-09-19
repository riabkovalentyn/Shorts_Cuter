import { createServer } from './server';
import { connectMongo } from './lib/db';
import { loadEnv } from './lib/env';

async function main() {
  loadEnv();
  const port = Number(process.env.PORT || 4000);
  await connectMongo(process.env.MONGO_URI || 'mongodb://localhost:27017/shorts_cuter');
  const app = await createServer();
  app.listen(port, () => {
    console.log(`[backend] listening on http://localhost:${port}`);
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
