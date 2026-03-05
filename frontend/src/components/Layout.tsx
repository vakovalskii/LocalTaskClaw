import { NavLink, Outlet } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { api, clearApiKey } from '../api';

const NAV_ITEMS = [
  { to: '/chat', label: 'CHAT' },
  { to: '/sessions', label: 'SESSIONS' },
  { to: '/kanban', label: 'KANBAN' },
  { to: '/tasks', label: 'TASKS' },
  { to: '/files', label: 'FILES' },
  { to: '/logs', label: 'LOGS' },
  { to: '/settings', label: 'SETTINGS' },
];

export default function Layout({ onLogout }: { onLogout: () => void }) {
  const [model, setModel] = useState('\u2014');
  const [status, setStatus] = useState<'online' | 'offline'>('offline');
  const [workspace, setWorkspace] = useState('\u2014');

  useEffect(() => {
    const check = async () => {
      try {
        const d = await api('GET', '/health');
        setStatus('online');
        setModel(d.model || '\u2014');
        setWorkspace(d.workspace || '\u2014');
      } catch {
        setStatus('offline');
      }
    };
    check();
    const id = setInterval(check, 15000);
    return () => clearInterval(id);
  }, []);

  function handleLogout() {
    clearApiKey();
    onLogout();
  }

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Top Bar */}
      <div className="flex items-center h-[42px] border-b border-border bg-bg1 flex-shrink-0">
        <div className="px-5 text-sm font-bold text-amber tracking-wider border-r border-border h-full flex items-center gap-2">
          <div className="w-[7px] h-[7px] rounded-full bg-amber animate-pulse-slow" />
          LOCALTASKCLAW
        </div>
        <div className="px-4 text-text2 text-[11px] border-r border-border h-full flex items-center">
          model <span className="text-text ml-1">{model}</span>
        </div>
        <nav className="flex h-full ml-auto">
          {NAV_ITEMS.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center px-[18px] text-xs font-medium tracking-wide border-l border-border transition-all relative ${
                  isActive
                    ? 'text-amber bg-bg2 after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-amber'
                    : 'text-text2 hover:text-text hover:bg-bg2'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
          <button
            onClick={handleLogout}
            className="flex items-center px-[18px] text-text3 text-[10px] border-l border-border hover:bg-bg2 hover:text-text2 transition-all"
            title="Logout"
          >
            LOGOUT
          </button>
        </nav>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden flex flex-col">
        <Outlet />
      </div>

      {/* Status Bar */}
      <div className="border-t border-border bg-bg1 px-4 flex items-center gap-4 text-[10px] text-text3 flex-shrink-0 h-[28px]">
        <span className={status === 'online' ? 'text-green' : 'text-red'}>
          {status === 'online' ? '\u25CF online' : '\u25CF offline'}
        </span>
        <span className="text-text3">|</span>
        <span>workspace: {workspace}</span>
      </div>
    </div>
  );
}
