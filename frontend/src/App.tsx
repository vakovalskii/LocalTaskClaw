import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { getApiKey, tryLogin } from './api';
import { ToastProvider } from './components/Toast';
import Layout from './components/Layout';
import Login from './components/Login';
import { lazy, Suspense } from 'react';

const Chat = lazy(() => import('./pages/Chat'));
const Sessions = lazy(() => import('./pages/Sessions'));
const Kanban = lazy(() => import('./pages/Kanban'));
const Tasks = lazy(() => import('./pages/Tasks'));
const Files = lazy(() => import('./pages/Files'));
const Logs = lazy(() => import('./pages/Logs'));
const Settings = lazy(() => import('./pages/Settings'));

function Loading() {
  return (
    <div className="flex-1 flex items-center justify-center text-text3 text-xs">
      Loading...
    </div>
  );
}

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    const key = getApiKey();
    if (!key) { setAuthed(false); return; }
    tryLogin(key).then(ok => {
      if (!ok) setAuthed(false);
      else setAuthed(true);
    }).catch(() => setAuthed(false));
  }, []);

  if (authed === null) {
    return <div className="h-screen bg-bg flex items-center justify-center text-text3 text-xs">Connecting...</div>;
  }

  if (!authed) {
    return (
      <ToastProvider>
        <Login onLogin={() => setAuthed(true)} />
      </ToastProvider>
    );
  }

  return (
    <ToastProvider>
      <BrowserRouter basename="/admin">
        <Routes>
          <Route element={<Layout onLogout={() => setAuthed(false)} />}>
            <Route path="/chat" element={<Suspense fallback={<Loading />}><Chat /></Suspense>} />
            <Route path="/sessions" element={<Suspense fallback={<Loading />}><Sessions /></Suspense>} />
            <Route path="/kanban" element={<Suspense fallback={<Loading />}><Kanban /></Suspense>} />
            <Route path="/tasks" element={<Suspense fallback={<Loading />}><Tasks /></Suspense>} />
            <Route path="/files" element={<Suspense fallback={<Loading />}><Files /></Suspense>} />
            <Route path="/logs" element={<Suspense fallback={<Loading />}><Logs /></Suspense>} />
            <Route path="/settings" element={<Suspense fallback={<Loading />}><Settings /></Suspense>} />
            <Route path="*" element={<Navigate to="/chat" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  );
}
