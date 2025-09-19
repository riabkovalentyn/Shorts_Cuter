import { Router } from 'express';
import projects from './routes/projects';
import jobs from './routes/jobs';
import clips from './routes/clips';
import auth from './routes/auth';

export const router = Router();

router.use('/projects', projects);
router.use('/jobs', jobs);
router.use('/clips', clips);
router.use('/auth/youtube', auth);
