import { useEffect, useState } from 'react';
import { api, API_BASE } from '../api';
import { useToast } from '../components/Toast';

interface SettingsData {
  model?: string;
  llm_base_url?: string;
  llm_api_key?: string;
  brave_api_key?: string;
  memory_enabled?: boolean;
  max_iterations?: number;
  command_timeout?: number;
  workspace?: string;
  owner_id?: string;
}

export default function Settings() {
  const toast = useToast();
  const [orig, setOrig] = useState<SettingsData>({});
  const [form, setForm] = useState<SettingsData>({});
  const [saving, setSaving] = useState(false);
  const [restarting, setRestarting] = useState(false);

  // Update state
  const [localHash, setLocalHash] = useState('');
  const [remoteHash, setRemoteHash] = useState('');
  const [updateAvailable, setUpdateAvailable] = useState(false);
  const [checking, setChecking] = useState(false);
  const [updating, setUpdating] = useState(false);

  const load = async () => {
    try {
      const d = await api<SettingsData>('GET', '/settings');
      setOrig(d);
      setForm(d);
    } catch (e: any) {
      toast('Failed to load settings: ' + e.message);
    }
  };

  useEffect(() => { load(); }, []);

  const set = (key: keyof SettingsData, value: any) => {
    setForm(prev => ({ ...prev, [key]: value }));
  };

  const save = async () => {
    setSaving(true);
    try {
      const body: Record<string, any> = {};
      for (const [k, v] of Object.entries(form)) {
        if (v !== (orig as any)[k] && v !== '' && v != null) {
          body[k] = v;
        }
      }
      if (Object.keys(body).length === 0) {
        toast('No changes');
        setSaving(false);
        return;
      }
      await api('POST', '/settings', body);
      toast('Settings saved');
      load();
    } catch (e: any) {
      toast('Save failed: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  const restart = async () => {
    setRestarting(true);
    try {
      await api('POST', '/restart');
      toast('Restarting core...');
      await pollHealth();
      toast('Core is back online');
    } catch (e: any) {
      toast('Restart failed: ' + e.message);
    } finally {
      setRestarting(false);
    }
  };

  const pollHealth = (): Promise<void> => {
    return new Promise((resolve) => {
      const check = () => {
        fetch(API_BASE + '/health')
          .then(r => { if (r.ok) resolve(); else setTimeout(check, 1000); })
          .catch(() => setTimeout(check, 1000));
      };
      setTimeout(check, 2000);
    });
  };

  const checkForUpdates = async () => {
    setChecking(true);
    try {
      const r = await fetch(API_BASE + '/version');
      const d = await r.json();
      setLocalHash(d.local_hash || d.hash || '');
      setRemoteHash(d.remote_hash || '');
      setUpdateAvailable(!!d.update_available);
      if (d.update_available) {
        toast('New version available');
      } else {
        toast('Already up to date');
      }
    } catch (e: any) {
      toast('Version check failed: ' + e.message);
    } finally {
      setChecking(false);
    }
  };

  const updateAndRestart = async () => {
    setUpdating(true);
    try {
      await api('POST', '/update');
      toast('Updating and restarting...');
      await pollHealth();
      toast('Update complete, core is back');
      setUpdateAvailable(false);
    } catch (e: any) {
      toast('Update failed: ' + e.message);
    } finally {
      setUpdating(false);
    }
  };

  const inputCls = 'w-full bg-bg2 border border-border2 text-text text-xs px-3 py-2 font-mono focus:border-amber focus:outline-none';
  const labelCls = 'text-[10px] text-text3 uppercase tracking-wide mb-1 block';

  return (
    <div className="flex-1 overflow-auto p-6 font-mono">
      <div className="max-w-[960px] mx-auto space-y-6">

        {/* MODEL */}
        <section>
          <h2 className="text-[10px] font-bold tracking-widest uppercase text-text3 border-b border-border pb-2 mb-3">
            MODEL
          </h2>
          <div className="space-y-3">
            <div>
              <label className={labelCls}>Model ID</label>
              <input
                value={form.model || ''}
                onChange={e => set('model', e.target.value)}
                className={inputCls}
                placeholder="e.g. qwen2.5:7b"
              />
            </div>
            <div>
              <label className={labelCls}>Base URL</label>
              <input
                value={form.llm_base_url || ''}
                onChange={e => set('llm_base_url', e.target.value)}
                className={inputCls}
                placeholder="http://localhost:11434/v1"
              />
            </div>
            <div>
              <label className={labelCls}>API Key</label>
              <input
                type="password"
                value={form.llm_api_key || ''}
                onChange={e => set('llm_api_key', e.target.value)}
                className={inputCls}
                placeholder="API key"
              />
            </div>
          </div>
        </section>

        {/* TOOLS */}
        <section>
          <h2 className="text-[10px] font-bold tracking-widest uppercase text-text3 border-b border-border pb-2 mb-3">
            TOOLS
          </h2>
          <div className="space-y-3">
            <div>
              <label className={labelCls}>Brave API Key</label>
              <input
                type="password"
                value={form.brave_api_key || ''}
                onChange={e => set('brave_api_key', e.target.value)}
                className={inputCls}
                placeholder="Brave Search API key (optional)"
              />
            </div>
            <div className="flex items-center gap-3">
              <label className={labelCls + ' mb-0'}>Memory Enabled</label>
              <button
                onClick={() => set('memory_enabled', !form.memory_enabled)}
                className={`w-10 h-5 rounded-sm relative transition-colors ${
                  form.memory_enabled ? 'bg-amber' : 'bg-bg3'
                }`}
              >
                <div className={`absolute top-0.5 w-4 h-4 bg-black rounded-sm transition-all ${
                  form.memory_enabled ? 'left-5' : 'left-0.5'
                }`} />
              </button>
              <span className="text-xs text-text2">{form.memory_enabled ? 'ON' : 'OFF'}</span>
            </div>
          </div>
        </section>

        {/* LIMITS */}
        <section>
          <h2 className="text-[10px] font-bold tracking-widest uppercase text-text3 border-b border-border pb-2 mb-3">
            LIMITS
          </h2>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Max Iterations</label>
              <input
                type="number"
                value={form.max_iterations ?? ''}
                onChange={e => set('max_iterations', parseInt(e.target.value) || 0)}
                className={inputCls}
              />
            </div>
            <div>
              <label className={labelCls}>Command Timeout (s)</label>
              <input
                type="number"
                value={form.command_timeout ?? ''}
                onChange={e => set('command_timeout', parseInt(e.target.value) || 0)}
                className={inputCls}
              />
            </div>
          </div>
        </section>

        {/* INFO */}
        <section>
          <h2 className="text-[10px] font-bold tracking-widest uppercase text-text3 border-b border-border pb-2 mb-3">
            INFO
          </h2>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Workspace</label>
              <input
                value={form.workspace || ''}
                readOnly
                className={inputCls + ' opacity-60 cursor-not-allowed'}
              />
            </div>
            <div>
              <label className={labelCls}>Owner ID</label>
              <input
                value={form.owner_id || ''}
                readOnly
                className={inputCls + ' opacity-60 cursor-not-allowed'}
              />
            </div>
          </div>
        </section>

        {/* ACTIONS */}
        <div className="flex items-center gap-3 pt-2">
          <button
            onClick={save}
            disabled={saving}
            className="bg-amber text-black font-bold text-xs px-5 py-2 hover:brightness-110 transition-all disabled:opacity-50"
          >
            {saving ? 'SAVING...' : 'SAVE'}
          </button>
          <button
            onClick={restart}
            disabled={restarting}
            className="border border-border2 text-text2 text-xs px-5 py-2 font-bold hover:text-text hover:border-amber transition-colors disabled:opacity-50"
          >
            {restarting ? 'RESTARTING...' : 'RESTART CORE'}
          </button>
          {restarting && (
            <span className="text-[10px] text-amber animate-pulse-slow">waiting for core...</span>
          )}
        </div>

        {/* UPDATE */}
        <section className="mt-4">
          <h2 className="text-[10px] font-bold tracking-widest uppercase text-text3 border-b border-border pb-2 mb-3">
            UPDATE
          </h2>
          <div className="space-y-3">
            {localHash && (
              <div className="text-xs text-text3">
                Local: <span className="text-text2">{localHash.slice(0, 12)}</span>
                {updateAvailable ? (
                  <span className="ml-4 text-amber">
                    new version available <span className="text-text3">({remoteHash.slice(0, 12)})</span>
                  </span>
                ) : (
                  <span className="ml-4 text-green">up to date</span>
                )}
              </div>
            )}
            <div className="flex items-center gap-3">
              <button
                onClick={checkForUpdates}
                disabled={checking}
                className="border border-border2 text-text2 text-xs px-4 py-2 font-bold hover:text-text hover:border-amber transition-colors disabled:opacity-50"
              >
                {checking ? 'CHECKING...' : 'CHECK FOR UPDATES'}
              </button>
              {updateAvailable && (
                <button
                  onClick={updateAndRestart}
                  disabled={updating}
                  className="bg-amber text-black font-bold text-xs px-4 py-2 hover:brightness-110 transition-all disabled:opacity-50"
                >
                  {updating ? 'UPDATING...' : 'UPDATE & RESTART'}
                </button>
              )}
              {updating && (
                <span className="text-[10px] text-amber animate-pulse-slow">updating and restarting...</span>
              )}
            </div>
          </div>
        </section>

      </div>
    </div>
  );
}
