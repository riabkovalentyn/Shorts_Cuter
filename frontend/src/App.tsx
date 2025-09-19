import { Routes, Route, NavLink } from 'react-router-dom';
import { useEffect, useState } from 'react';
import Dashboard from './pages/Dashboard';
import ClipsList from './pages/ClipsList';
import Settings from './pages/Settings';
import { getYouTubeStatus } from './lib/api';
import Toaster, { useToasts } from './shared/Toaster';

export default function App() {
  const [ytConnected, setYtConnected] = useState<boolean>(false);
  const [ytConfigured, setYtConfigured] = useState<boolean>(true);
  const { toasts } = useToasts();

  useEffect(() => {
    getYouTubeStatus().then((s) => {
      setYtConnected(Boolean(s.connected));
      setYtConfigured(Boolean(s.configured));
    }).catch(() => {});
  }, []);

  return (
    <div className="min-h-full">
      <header className="relative">
        <div className="absolute inset-0 bg-gradient-to-r from-blue-600 to-indigo-600" />
        <div className="relative container py-4 flex flex-wrap items-center gap-6 text-white">
          <div className="flex items-center gap-2 text-lg font-semibold">
            <span>🎬</span>
            <span>Shorts Cuter</span>
          </div>
          <nav className="flex gap-4">
            <NavLink to="/" className={({isActive}) => `hover:underline ${isActive ? 'font-semibold' : 'opacity-90'}`}>Dashboard</NavLink>
            <NavLink to="/clips" className={({isActive}) => `hover:underline ${isActive ? 'font-semibold' : 'opacity-90'}`}>Clips</NavLink>
            <NavLink to="/settings" className={({isActive}) => `hover:underline ${isActive ? 'font-semibold' : 'opacity-90'}`}>Settings</NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <span className={`text-xs px-2 py-0.5 rounded-full ${ytConnected ? 'bg-green-100 text-green-800' : 'bg-slate-100 text-slate-800'}`}>
              {ytConnected ? 'YouTube Connected' : (ytConfigured ? 'YouTube Not Connected' : 'YouTube Not Configured')}
            </span>
          </div>
        </div>
      </header>
      <main className="container py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/clips" element={<ClipsList />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
      <Toaster items={toasts} />
    </div>
  );
}
