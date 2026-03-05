import { useEffect, useState, useCallback } from 'react';
import { api } from '../api';
import type { Session, TraceEvent } from '../types';
import { fmtTime } from '../utils';

interface ChatMessage {
  role: 'user' | 'assistant' | 'tool';
  content: string;
}

type Tab = 'messages' | 'trace';

const EVENT_COLORS: Record<string, string> = {
  iteration_start: 'bg-blue/20 text-blue',
  tool_call: 'bg-amber/20 text-amber',
  tool_result: 'bg-green/20 text-green',
  agent_done: 'bg-red/20 text-red',
};

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) + '...' : s;
}

function eventSummary(ev: TraceEvent): string {
  const d = ev.data;
  if (!d) return ev.type;
  switch (ev.type) {
    case 'iteration_start':
      return `Iteration #${d.iteration ?? '?'}`;
    case 'tool_call':
      return `${d.name ?? 'tool'}(${truncate(JSON.stringify(d.args ?? {}), 80)})`;
    case 'tool_result':
      return truncate(String(d.result ?? d.output ?? ''), 120);
    case 'agent_done':
      return `Iteration ${d.iteration ?? '?'} | ${d.total_tokens ?? '?'} tokens`;
    default:
      return truncate(JSON.stringify(d), 100);
  }
}

function formatJsonTruncated(data: any): string {
  return JSON.stringify(data, (_key, value) => {
    if (typeof value === 'string' && value.length > 400) {
      return value.slice(0, 400) + '... [truncated]';
    }
    return value;
  }, 2);
}

export default function Sessions() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('messages');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [expandedEvents, setExpandedEvents] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);
  const [sessionsLoading, setSessionsLoading] = useState(true);

  // Load sessions
  useEffect(() => {
    setSessionsLoading(true);
    api<Session[]>('GET', '/sessions')
      .then(setSessions)
      .catch(() => setSessions([]))
      .finally(() => setSessionsLoading(false));
  }, []);

  // Load messages or events when session/tab changes
  const loadData = useCallback(async (key: string, currentTab: Tab) => {
    setLoading(true);
    try {
      if (currentTab === 'messages') {
        const chatId = key.replace('owner_', '');
        const msgs = await api<ChatMessage[]>('GET', `/history?chat_id=${chatId}`);
        setMessages(msgs);
      } else {
        const evts = await api<TraceEvent[]>('GET', `/events?session_key=${key}&limit=200`);
        setEvents(evts);
      }
    } catch {
      if (currentTab === 'messages') setMessages([]);
      else setEvents([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedKey) {
      setExpandedEvents(new Set());
      loadData(selectedKey, tab);
    }
  }, [selectedKey, tab, loadData]);

  function toggleEvent(idx: number) {
    setExpandedEvents(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left Sidebar */}
      <div className="w-[280px] flex-shrink-0 border-r border-border bg-bg1 flex flex-col">
        <div className="px-4 py-3 border-b border-border text-[11px] text-text2 font-medium tracking-wide">
          SESSIONS
        </div>
        <div className="flex-1 overflow-y-auto">
          {sessionsLoading ? (
            <div className="flex flex-col items-center justify-center h-full text-text3 text-xs">
              <span className="animate-pulse-slow">Loading...</span>
            </div>
          ) : sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-text3 text-xs gap-2">
              <svg className="w-8 h-8 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
              </svg>
              No sessions
            </div>
          ) : (
            sessions.map(s => (
              <button
                key={s.session_key}
                onClick={() => setSelectedKey(s.session_key)}
                className={`w-full text-left px-4 py-3 border-b border-border/50 transition-colors ${
                  selectedKey === s.session_key
                    ? 'bg-bg2 border-l-2 border-l-amber'
                    : 'hover:bg-bg2/50 border-l-2 border-l-transparent'
                }`}
              >
                <div className="text-xs text-text truncate">{s.session_key}</div>
                <div className="text-[10px] text-text3 mt-1">{fmtTime(s.updated_at)}</div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Right Panel */}
      <div className="flex-1 flex flex-col overflow-hidden bg-bg">
        {!selectedKey ? (
          <div className="flex flex-col items-center justify-center h-full text-text3 text-xs gap-2">
            <svg className="w-10 h-10 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
            </svg>
            Select a session
          </div>
        ) : (
          <>
            {/* Tab Buttons */}
            <div className="flex border-b border-border bg-bg1 flex-shrink-0">
              <button
                onClick={() => setTab('messages')}
                className={`px-6 py-2.5 text-[11px] font-medium tracking-wide transition-colors relative ${
                  tab === 'messages'
                    ? 'text-amber after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-amber'
                    : 'text-text2 hover:text-text'
                }`}
              >
                MESSAGES
              </button>
              <button
                onClick={() => setTab('trace')}
                className={`px-6 py-2.5 text-[11px] font-medium tracking-wide transition-colors relative ${
                  tab === 'trace'
                    ? 'text-amber after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-amber'
                    : 'text-text2 hover:text-text'
                }`}
              >
                TRACE
              </button>
            </div>

            {/* Tab Content */}
            <div className="flex-1 overflow-y-auto p-4">
              {loading ? (
                <div className="flex items-center justify-center h-full text-text3 text-xs">
                  <span className="animate-pulse-slow">Loading...</span>
                </div>
              ) : tab === 'messages' ? (
                <MessagesView messages={messages} />
              ) : (
                <TraceView events={events} expandedEvents={expandedEvents} onToggle={toggleEvent} />
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function MessagesView({ messages }: { messages: ChatMessage[] }) {
  if (messages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-text3 text-xs gap-2">
        <svg className="w-8 h-8 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
        </svg>
        No messages
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {messages
        .filter(m => m.role === 'user' || m.role === 'assistant')
        .map((m, i) => (
          <div
            key={i}
            className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] px-4 py-2.5 rounded text-xs leading-relaxed whitespace-pre-wrap break-words ${
                m.role === 'user'
                  ? 'bg-amber/15 text-text border border-amber/20'
                  : 'bg-bg2 text-text border border-border'
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
    </div>
  );
}

function TraceView({
  events,
  expandedEvents,
  onToggle,
}: {
  events: TraceEvent[];
  expandedEvents: Set<number>;
  onToggle: (idx: number) => void;
}) {
  if (events.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-text3 text-xs gap-2">
        <svg className="w-8 h-8 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 010 3.75H5.625a1.875 1.875 0 010-3.75z" />
        </svg>
        No events
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      {events.map((ev, i) => {
        const colorClass = EVENT_COLORS[ev.type] || 'bg-bg3 text-text2';
        const expanded = expandedEvents.has(i);
        return (
          <div key={i} className="border border-border rounded bg-bg1">
            <button
              onClick={() => onToggle(i)}
              className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-bg2/50 transition-colors"
            >
              {/* Type badge */}
              <span className={`px-2 py-0.5 rounded text-[10px] font-medium flex-shrink-0 ${colorClass}`}>
                {ev.type}
              </span>
              {/* Summary */}
              <span className="text-xs text-text2 truncate flex-1">
                {eventSummary(ev)}
              </span>
              {/* Timestamp */}
              <span className="text-[10px] text-text3 flex-shrink-0 ml-auto">
                {fmtTime(ev.at)}
              </span>
              {/* Chevron */}
              <svg
                className={`w-3 h-3 text-text3 flex-shrink-0 transition-transform ${expanded ? 'rotate-180' : ''}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
              </svg>
            </button>
            {expanded && (
              <div className="px-3 pb-3 border-t border-border/50">
                <pre className="text-[11px] text-text2 overflow-x-auto mt-2 leading-relaxed whitespace-pre-wrap break-words">
                  {formatJsonTruncated(ev.data)}
                </pre>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
