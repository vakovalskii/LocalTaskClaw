import { useState } from 'react';
import { tryLogin, setApiKey } from '../api';

interface Props {
  onLogin: () => void;
}

export default function Login({ onLogin }: Props) {
  const [key, setKey] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleLogin() {
    if (!key.trim()) { setError('Enter API key'); return; }
    setError('');
    setLoading(true);
    try {
      const ok = await tryLogin(key.trim());
      if (ok) {
        setApiKey(key.trim());
        onLogin();
      } else {
        setError('Invalid API Secret');
      }
    } catch {
      setError('Server unavailable');
    }
    setLoading(false);
  }

  return (
    <div className="fixed inset-0 z-[9999] bg-bg flex items-center justify-center">
      <div className="flex flex-col items-center gap-6 max-w-[380px] w-full px-6">
        <div className="text-lg font-bold text-amber tracking-wider">LocalTaskClaw</div>
        <div className="text-text2 text-xs text-center leading-relaxed">
          Enter API Secret to access the panel.<br />
          It was shown during installation, or find it in<br />
          <code className="text-amber bg-bg2 px-1.5 py-0.5 rounded-sm">~/.localtaskclaw/app/secrets/core.env</code>
        </div>
        <input
          type="password"
          value={key}
          onChange={e => setKey(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleLogin()}
          placeholder="API Secret"
          className="w-full bg-bg2 border border-border2 rounded-sm text-text font-mono text-sm px-4 py-3 text-center outline-none focus:border-amber transition-colors"
          autoFocus
        />
        <button
          onClick={handleLogin}
          disabled={loading}
          className="w-full h-11 bg-amber text-black font-mono font-bold text-sm tracking-wider rounded-sm hover:bg-amber2 disabled:bg-text3 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? '...' : 'LOGIN'}
        </button>
        {error && <div className="text-red text-xs">{error}</div>}
      </div>
    </div>
  );
}
