import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../components/Toast';
import { fmtTime } from '../utils';

interface Task {
  id: number;
  name: string;
  schedule: string;
  enabled: boolean;
  last_run: string | null;
  next_run: string | null;
}

export default function Tasks() {
  const toast = useToast();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [name, setName] = useState('');
  const [interval, setInterval_] = useState('');
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const d = await api<{ tasks: Task[] }>('GET', '/tasks');
      setTasks(d.tasks);
    } catch (e: any) {
      toast('Failed to load tasks: ' + e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const toggle = async (id: number) => {
    try {
      await api('PATCH', `/tasks/${id}/toggle`);
      toast('Task toggled');
      load();
    } catch (e: any) {
      toast('Toggle failed: ' + e.message);
    }
  };

  const del = async (id: number) => {
    if (!confirm('Delete this task?')) return;
    try {
      await api('DELETE', `/tasks/${id}`);
      toast('Task deleted');
      load();
    } catch (e: any) {
      toast('Delete failed: ' + e.message);
    }
  };

  const add = async () => {
    if (!name.trim() || !prompt.trim()) { toast('Name and prompt required'); return; }
    const body: any = { name: name.trim(), prompt: prompt.trim() };
    const v = interval.trim();
    if (/^\d+$/.test(v)) {
      body.interval_minutes = parseInt(v);
    } else if (v) {
      body.cron = v;
    }
    try {
      await api('POST', '/tasks', body);
      toast('Task created');
      setName('');
      setInterval_('');
      setPrompt('');
      load();
    } catch (e: any) {
      toast('Create failed: ' + e.message);
    }
  };

  return (
    <div className="flex-1 overflow-auto p-6 font-mono">
      <h2 className="text-[10px] font-bold tracking-widest uppercase text-text3 border-b border-border pb-2 mb-3">
        SCHEDULED TASKS
      </h2>

      {loading ? (
        <div className="text-text3 text-xs">Loading...</div>
      ) : (
        <div className="overflow-x-auto mb-8">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-text3 text-[10px] uppercase tracking-wider border-b border-border">
                <th className="text-left py-2 px-2 font-medium">ID</th>
                <th className="text-left py-2 px-2 font-medium">NAME</th>
                <th className="text-left py-2 px-2 font-medium">SCHEDULE</th>
                <th className="text-left py-2 px-2 font-medium">STATUS</th>
                <th className="text-left py-2 px-2 font-medium">LAST RUN</th>
                <th className="text-left py-2 px-2 font-medium">NEXT RUN</th>
                <th className="text-right py-2 px-2 font-medium">ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {tasks.length === 0 && (
                <tr><td colSpan={7} className="text-text3 py-4 px-2">No tasks</td></tr>
              )}
              {tasks.map(t => (
                <tr key={t.id} className="border-b border-border/50 hover:bg-bg1">
                  <td className="py-2 px-2 text-text3">{t.id}</td>
                  <td className="py-2 px-2 text-text">{t.name}</td>
                  <td className="py-2 px-2 text-text2">{t.schedule}</td>
                  <td className="py-2 px-2">
                    <span className={`inline-block px-2 py-0.5 text-[10px] font-bold rounded-sm ${
                      t.enabled ? 'bg-green/20 text-green' : 'bg-red/20 text-red'
                    }`}>
                      {t.enabled ? 'ON' : 'OFF'}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-text3">{fmtTime(t.last_run)}</td>
                  <td className="py-2 px-2 text-text3">{fmtTime(t.next_run)}</td>
                  <td className="py-2 px-2 text-right">
                    <button
                      onClick={() => toggle(t.id)}
                      className="px-2 py-1 text-[10px] border border-border2 text-text2 hover:text-text hover:border-amber mr-2 transition-colors"
                    >
                      TOGGLE
                    </button>
                    <button
                      onClick={() => del(t.id)}
                      className="px-2 py-1 text-[10px] border border-border2 text-red hover:bg-red/10 transition-colors"
                    >
                      DEL
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* New Task Form */}
      <h2 className="text-[10px] font-bold tracking-widest uppercase text-text3 border-b border-border pb-2 mb-3">
        NEW TASK
      </h2>
      <div className="max-w-2xl space-y-3">
        <div className="flex gap-3">
          <input
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="Task name"
            className="flex-1 bg-bg2 border border-border2 text-text text-xs px-3 py-2 font-mono focus:border-amber focus:outline-none"
          />
          <input
            value={interval}
            onChange={e => setInterval_(e.target.value)}
            placeholder="Interval (min) or cron"
            className="w-52 bg-bg2 border border-border2 text-text text-xs px-3 py-2 font-mono focus:border-amber focus:outline-none"
          />
        </div>
        <textarea
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          placeholder="Task prompt..."
          rows={4}
          className="w-full bg-bg2 border border-border2 text-text text-xs px-3 py-2 font-mono resize-y focus:border-amber focus:outline-none"
        />
        <button
          onClick={add}
          className="bg-amber text-black font-bold text-xs px-4 py-2 hover:brightness-110 transition-all"
        >
          ADD TASK
        </button>
      </div>
    </div>
  );
}
