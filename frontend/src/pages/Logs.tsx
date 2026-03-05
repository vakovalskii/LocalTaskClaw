import { useEffect, useRef, useState, useCallback } from 'react';
import { api, API_BASE, getApiKey } from '../api';
import { useToast } from '../components/Toast';

const MAX_LINES = 2000;

function levelColor(line: string): string {
  if (/\bERROR\b/i.test(line)) return 'text-red';
  if (/\bWARN(ING)?\b/i.test(line)) return 'text-amber';
  if (/\bDEBUG\b/i.test(line)) return 'text-text3';
  return 'text-text2';
}

export default function Logs() {
  const toast = useToast();
  const [source, setSource] = useState<'core' | 'bot'>('core');
  const [lines, setLines] = useState<string[]>([]);
  const [paused, setPaused] = useState(false);
  const [connected, setConnected] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const pausedRef = useRef(false);
  const esRef = useRef<EventSource | null>(null);

  pausedRef.current = paused;

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'auto' });
  }, []);

  const loadTail = async (src: string) => {
    try {
      const d = await api<{ lines: string[] }>('GET', `/logs/tail?source=${src}&lines=300`);
      setLines(d.lines || []);
      setTimeout(scrollToBottom, 50);
    } catch (e: any) {
      toast('Failed to load logs: ' + e.message);
    }
  };

  const connectSSE = (src: string) => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }

    const key = getApiKey();
    const url = API_BASE + `/logs/stream?source=${src}&x_api_key=${encodeURIComponent(key)}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    es.onmessage = (ev) => {
      if (pausedRef.current) return;
      const text = ev.data;
      if (!text) return;
      setLines(prev => {
        const next = [...prev, text];
        return next.length > MAX_LINES ? next.slice(next.length - MAX_LINES) : next;
      });
      setTimeout(scrollToBottom, 10);
    };
  };

  useEffect(() => {
    loadTail(source);
    connectSSE(source);
    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, [source]);

  const clearLogs = () => {
    setLines([]);
    toast('Cleared');
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden font-mono">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 h-[40px] border-b border-border bg-bg1 flex-shrink-0">
        <span className="text-[10px] font-bold tracking-widest uppercase text-text3">LOGS</span>

        <select
          value={source}
          onChange={e => setSource(e.target.value as 'core' | 'bot')}
          className="bg-bg2 border border-border2 text-text text-xs px-2 py-1 font-mono focus:border-amber focus:outline-none"
        >
          <option value="core">core</option>
          <option value="bot">bot</option>
        </select>

        <button
          onClick={clearLogs}
          className="border border-border2 text-text2 text-[10px] px-3 py-1 hover:text-text hover:border-amber transition-colors"
        >
          CLEAR
        </button>

        <button
          onClick={() => setPaused(p => !p)}
          className={`border text-[10px] px-3 py-1 transition-colors ${
            paused
              ? 'border-amber text-amber hover:bg-amber/10'
              : 'border-border2 text-text2 hover:text-text hover:border-amber'
          }`}
        >
          {paused ? 'RESUME' : 'PAUSE'}
        </button>

        <div className="ml-auto flex items-center gap-2">
          <div className={`w-[6px] h-[6px] rounded-full ${connected ? 'bg-green' : 'bg-red'}`} />
          <span className="text-[10px] text-text3">
            {connected ? 'streaming' : 'disconnected'}
          </span>
          {paused && (
            <span className="text-[10px] text-amber ml-2">PAUSED</span>
          )}
        </div>
      </div>

      {/* Log Output */}
      <div className="flex-1 overflow-y-auto bg-bg p-4">
        {lines.length === 0 && (
          <div className="text-text3 text-xs">No log lines</div>
        )}
        {lines.map((line, i) => (
          <div key={i} className={`text-[11px] leading-5 whitespace-pre-wrap break-all ${levelColor(line)}`}>
            {line}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
