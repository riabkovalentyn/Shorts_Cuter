import { createContext, useContext, useMemo, useState } from 'react';

type Toast = { id: string; kind: 'success' | 'error' | 'info'; text: string };

const ToastCtx = createContext<{
  toasts: Toast[];
  push: (t: Omit<Toast, 'id'>) => void;
  remove: (id: string) => void;
}>({ toasts: [], push: () => {}, remove: () => {} });

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const api = useMemo(() => ({
    toasts,
    push: (t: Omit<Toast, 'id'>) => {
      const id = Math.random().toString(36).slice(2);
      setToasts((prev) => [...prev, { id, ...t }]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((x) => x.id !== id));
      }, 3500);
    },
    remove: (id: string) => setToasts((prev) => prev.filter((x) => x.id !== id)),
  }), [toasts]);

  return <ToastCtx.Provider value={api}>{children}</ToastCtx.Provider>;
}

export function useToasts() {
  return useContext(ToastCtx);
}

export default function Toaster({ items }: { items: Toast[] }) {
  return (
    <div className="fixed bottom-4 right-4 space-y-2 z-50">
      {items.map((t) => (
        <div key={t.id} className={`px-4 py-2 rounded shadow text-sm ${
          t.kind === 'success' ? 'bg-green-600 text-white' : t.kind === 'error' ? 'bg-red-600 text-white' : 'bg-slate-800 text-white'
        }`}>{t.text}</div>
      ))}
    </div>
  );
}
