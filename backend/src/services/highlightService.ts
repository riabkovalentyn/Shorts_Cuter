import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

function getFfmpegPath(): string {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const ff = require('@ffmpeg-installer/ffmpeg');
    if (ff?.path) return ff.path as string;
  } catch {}
  return 'ffmpeg';
}

function getFfprobePath(): string {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const fp = require('@ffprobe-installer/ffprobe');
    if (fp?.path) return fp.path as string;
  } catch {}
  return 'ffprobe';
}

async function probeDuration(inputPath: string): Promise<number> {
  const ffprobe = getFfprobePath();
  return new Promise<number>((resolve, reject) => {
    const args = ['-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', inputPath];
    let out = '';
    const cp = spawn(ffprobe, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    cp.stdout.on('data', (d) => (out += d.toString()));
    cp.on('error', reject);
    cp.on('close', (code) => {
      if (code === 0) {
        const n = Number((out || '').trim());
        resolve(Number.isFinite(n) ? n : 0);
      } else reject(new Error('ffprobe failed'));
    });
  });
}

async function detectScenes(inputPath: string, threshold = 0.4): Promise<number[]> {
  const ffmpeg = getFfmpegPath();
  return new Promise<number[]>((resolve) => {
    const args = ['-i', inputPath, '-filter:v', `select='gt(scene,${threshold})',showinfo`, '-f', 'null', '-'];
    let err = '';
    const cp = spawn(ffmpeg, args, { stdio: ['ignore', 'ignore', 'pipe'] });
    cp.stderr.on('data', (d) => (err += d.toString()));
    cp.on('close', () => {
      const times: number[] = [];
      const re = /pts_time:([0-9]+\.[0-9]+)/g;
      let m: RegExpExecArray | null;
      while ((m = re.exec(err))) {
        times.push(parseFloat(m[1]));
      }
      resolve(times);
    });
  });
}

async function detectSilence(inputPath: string): Promise<Array<{ start: number; end: number }>> {
  const ffmpeg = getFfmpegPath();
  return new Promise((resolve) => {
    const args = ['-i', inputPath, '-af', 'silencedetect=noise=-30dB:d=0.5', '-f', 'null', '-'];
    let err = '';
    const cp = spawn(ffmpeg, args, { stdio: ['ignore', 'ignore', 'pipe'] });
    cp.stderr.on('data', (d) => (err += d.toString()));
    cp.on('close', () => {
      const silences: Array<{ start: number; end: number }> = [];
      const rs = /silence_start: ([0-9]+\.[0-9]+)/g;
      const re = /silence_end: ([0-9]+\.[0-9]+)/g;
      const starts: number[] = [];
      let m: RegExpExecArray | null;
      while ((m = rs.exec(err))) starts.push(parseFloat(m[1]));
      const ends: number[] = [];
      while ((m = re.exec(err))) ends.push(parseFloat(m[1]));
      const n = Math.min(starts.length, ends.length);
      for (let i = 0; i < n; i++) silences.push({ start: starts[i], end: ends[i] });
      resolve(silences);
    });
  });
}

export type HighlightWindow = { start: number; duration: number; score: number };

export const highlightService = {
  async detectHighlights(inputPath: string, opts: { clipLengthSec: number; maxClips?: number }) {
    const clipLen = Math.max(5, opts.clipLengthSec);
    const maxClips = Math.max(1, opts.maxClips || 5);
    const duration = await probeDuration(inputPath);
    if (!duration || duration < 1) return [] as HighlightWindow[];

    const [scenes, silences] = await Promise.all([
      detectScenes(inputPath, 0.35),
      detectSilence(inputPath),
    ]);

    // Build audio activity intervals = complement of silence
    const activity: Array<{ start: number; end: number }> = [];
    let cursor = 0;
    for (const s of silences) {
      const sStart = Math.max(0, s.start);
      const sEnd = Math.min(duration, s.end);
      if (sStart > cursor) activity.push({ start: cursor, end: sStart });
      cursor = Math.max(cursor, sEnd);
    }
    if (cursor < duration) activity.push({ start: cursor, end: duration });

    // Candidate window starts: scene times (and 0)
    const candidates = Array.from(new Set([0, ...scenes])).filter((t) => t < duration - 0.5);

    function windowScore(start: number): number {
      const end = Math.min(duration, start + clipLen);
      let active = 0;
      for (const a of activity) {
        const s = Math.max(start, a.start);
        const e = Math.min(end, a.end);
        if (e > s) active += e - s;
      }
      // scene density in window
      const sceneCount = scenes.filter((t) => t >= start && t < end).length;
      return active + sceneCount * 0.75; // weight scenes modestly
    }

    const scored = candidates.map((s) => ({ start: s, duration: clipLen, score: windowScore(s) }))
      .sort((a, b) => b.score - a.score);

    // Pick top non-overlapping windows
    const picked: HighlightWindow[] = [];
    for (const w of scored) {
      if (picked.length >= maxClips) break;
      if (picked.some((p) => !(w.start + w.duration <= p.start || p.start + p.duration <= w.start))) continue;
      picked.push(w);
    }
    // Fallback: if nothing picked for some reason, return evenly spaced windows
    if (!picked.length) {
      const count = Math.min(maxClips, Math.max(1, Math.floor(duration / clipLen)));
      for (let i = 0; i < count; i++) {
        const s = i * clipLen;
        if (s >= duration - 0.5) break;
        picked.push({ start: s, duration: Math.min(clipLen, duration - s), score: 0 });
      }
    }
    return picked.sort((a, b) => a.start - b.start);
  }
};
