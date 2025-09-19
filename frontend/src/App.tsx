import { Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import ClipsList from './pages/ClipsList';
import Settings from './pages/Settings.tsx';

export default function App() {
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
        </div>
      </header>
      <main className="container py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/clips" element={<ClipsList />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
