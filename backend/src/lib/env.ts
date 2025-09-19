import dotenv from 'dotenv';

let loaded = false;
export function loadEnv() {
  if (loaded) return;
  dotenv.config();
  loaded = true;
}
