import { useEffect, useRef, useState, useCallback, type KeyboardEvent, type ChangeEvent } from 'react';
import { marked } from 'marked';
import { api, API_BASE, getApiKey, getChatId, setChatId } from '../api';
import { useToast } from '../components/Toast';
import type { ChatMessage, ToolEvent } from '../types';

interface DisplayMessage {
  role: 'user' | 'assistant';
  content: string;
  tools: ToolEvent[];
}

export default function Chat() {
  const toast = useToast();
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState('');
  const [streamTools, setStreamTools] = useState<ToolEvent[]>([]);
  const [runningTool, setRunningTool] = useState('');
  const [expandedTools, setExpandedTools] = useState<Record<string, boolean>>({});
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const scrollToBottom = useCallback(() => {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
  }, []);

  // Load history
  useEffect(() => {
    (async () => {
      try {
        let chatId = getChatId();
        if (!chatId) {
          const s = await api<any>('GET', '/settings');
          if (s.owner_id) {
            setChatId(s.owner_id);
            chatId = s.owner_id;
          }
        }
        if (!chatId) return;
        const history: ChatMessage[] = await api('GET', `/history?chat_id=${chatId}`);
        const display: DisplayMessage[] = [];
        for (const msg of history) {
          if (msg.role === 'user') {
            display.push({ role: 'user', content: msg.content, tools: [] });
          } else if (msg.role === 'assistant') {
            // Try to parse tool events from content if JSON array
            let content = msg.content;
            let tools: ToolEvent[] = [];
            try {
              const parsed = JSON.parse(content);
              if (Array.isArray(parsed)) {
                tools = parsed;
                content = '';
              }
            } catch {
              // not JSON, use as-is
            }
            if (display.length > 0 && display[display.length - 1].role === 'assistant') {
              // Merge with previous assistant message
              const prev = display[display.length - 1];
              if (content) prev.content += (prev.content ? '\n' : '') + content;
              prev.tools.push(...tools);
            } else {
              display.push({ role: 'assistant', content, tools });
            }
          }
        }
        setMessages(display);
        scrollToBottom();
      } catch (e: any) {
        toast('Failed to load history: ' + e.message);
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-resize textarea
  function autoResize(el: HTMLTextAreaElement) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  }

  function handleInputChange(e: ChangeEvent<HTMLTextAreaElement>) {
    setInput(e.target.value);
    autoResize(e.target);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  async function sendMessage() {
    const text = input.trim();
    if (!text || streaming) return;

    let chatId = getChatId();
    if (!chatId) {
      toast('No chat ID configured');
      return;
    }

    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    // Add user message
    setMessages(prev => [...prev, { role: 'user', content: text, tools: [] }]);
    scrollToBottom();

    // Start streaming
    setStreaming(true);
    setStreamText('');
    setStreamTools([]);
    setRunningTool('');

    const controller = new AbortController();
    abortRef.current = controller;

    let accText = '';
    let accTools: ToolEvent[] = [];

    try {
      const res = await fetch(API_BASE + '/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Api-Key': getApiKey(),
        },
        body: JSON.stringify({
          message: text,
          chat_id: chatId,
          stream: true,
          source: 'admin',
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        throw new Error(await res.text());
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (!raw || raw === '[DONE]') continue;

          try {
            const evt = JSON.parse(raw);

            if (evt.type === 'text') {
              accText += evt.content || '';
              setStreamText(accText);
              scrollToBottom();
            } else if (evt.type === 'tool_start') {
              setRunningTool(evt.name || 'tool');
            } else if (evt.type === 'tool_done') {
              const tool: ToolEvent = {
                name: evt.name || '',
                args: evt.args || {},
                success: evt.success ?? true,
                result: evt.result || '',
              };
              accTools = [...accTools, tool];
              setStreamTools([...accTools]);
              setRunningTool('');
            } else if (evt.type === 'error') {
              accText += '\n\n**Error:** ' + (evt.content || evt.message || 'Unknown error');
              setStreamText(accText);
            }
          } catch {
            // ignore parse errors
          }
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        accText += '\n\n**Error:** ' + e.message;
        setStreamText(accText);
        toast('Stream error: ' + e.message);
      }
    } finally {
      // Finalize message
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: accText, tools: accTools },
      ]);
      setStreaming(false);
      setStreamText('');
      setStreamTools([]);
      setRunningTool('');
      abortRef.current = null;
      scrollToBottom();
    }
  }

  async function handleClear() {
    const chatId = getChatId();
    if (!chatId) return;
    try {
      await api('POST', '/clear', { chat_id: chatId });
      setMessages([]);
      toast('Chat cleared');
    } catch (e: any) {
      toast('Failed to clear: ' + e.message);
    }
  }

  function toggleTool(key: string) {
    setExpandedTools(prev => ({ ...prev, [key]: !prev[key] }));
  }

  function renderMarkdown(text: string): string {
    if (!text) return '';
    return marked.parse(text, { async: false }) as string;
  }

  function renderToolEvents(tools: ToolEvent[], keyPrefix: string) {
    if (!tools.length) return null;
    return (
      <div className="mt-3 space-y-1">
        {tools.map((t, i) => {
          const key = `${keyPrefix}-${i}`;
          const isOpen = expandedTools[key];
          const argsPreview = typeof t.args === 'string'
            ? t.args.slice(0, 80)
            : JSON.stringify(t.args || {}).slice(0, 80);
          return (
            <div key={key} className="border border-border rounded-sm">
              <button
                className="w-full text-left px-3 py-1.5 flex items-center gap-2 text-[11px] hover:bg-bg2 transition-colors"
                onClick={() => toggleTool(key)}
              >
                <span className="text-text3">{isOpen ? '\u25BC' : '\u25B6'}</span>
                <span className="text-amber font-medium">{t.name}</span>
                <span className="text-text3 truncate flex-1">{argsPreview}</span>
                <span className={t.success ? 'text-green' : 'text-red'}>
                  {t.success ? 'OK' : 'ERR'}
                </span>
              </button>
              {isOpen && (
                <div className="px-3 py-2 border-t border-border bg-bg1 text-[11px]">
                  <div className="mb-1.5">
                    <span className="text-text3">args: </span>
                    <span className="text-text2 break-all">
                      {typeof t.args === 'string' ? t.args : JSON.stringify(t.args, null, 2)}
                    </span>
                  </div>
                  {t.result && (
                    <div>
                      <span className="text-text3">result: </span>
                      <pre className="text-text2 whitespace-pre-wrap break-all mt-0.5 max-h-[200px] overflow-y-auto">
                        {t.result}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden font-mono">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[760px] mx-auto px-4 py-6 space-y-5">
          {messages.length === 0 && !streaming && (
            <div className="text-center text-text3 text-xs py-20">
              No messages yet. Start a conversation.
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i}>
              {msg.role === 'user' ? (
                <div>
                  <div className="text-[10px] text-amber font-bold tracking-wider mb-1.5">YOU</div>
                  <div className="text-text text-[13px] whitespace-pre-wrap">{msg.content}</div>
                </div>
              ) : (
                <div>
                  <div className="text-[10px] text-green font-bold tracking-wider mb-1.5">AGENT</div>
                  <div
                    className="text-text text-[13px] prose prose-invert prose-sm max-w-none
                      [&_pre]:bg-bg1 [&_pre]:border [&_pre]:border-border [&_pre]:rounded-sm [&_pre]:p-3 [&_pre]:text-[12px] [&_pre]:overflow-x-auto
                      [&_code]:text-amber [&_code]:text-[12px]
                      [&_a]:text-blue [&_a]:underline
                      [&_p]:mb-2 [&_ul]:mb-2 [&_ol]:mb-2 [&_li]:mb-0.5
                      [&_h1]:text-text [&_h2]:text-text [&_h3]:text-text
                      [&_blockquote]:border-l-2 [&_blockquote]:border-amber [&_blockquote]:pl-3 [&_blockquote]:text-text2"
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
                  />
                  {renderToolEvents(msg.tools, `msg-${i}`)}
                </div>
              )}
            </div>
          ))}

          {/* Streaming message */}
          {streaming && (
            <div>
              <div className="text-[10px] text-green font-bold tracking-wider mb-1.5">AGENT</div>
              {streamText ? (
                <div
                  className="text-text text-[13px] prose prose-invert prose-sm max-w-none streaming-cursor
                    [&_pre]:bg-bg1 [&_pre]:border [&_pre]:border-border [&_pre]:rounded-sm [&_pre]:p-3 [&_pre]:text-[12px] [&_pre]:overflow-x-auto
                    [&_code]:text-amber [&_code]:text-[12px]
                    [&_a]:text-blue [&_a]:underline
                    [&_p]:mb-2 [&_ul]:mb-2 [&_ol]:mb-2 [&_li]:mb-0.5"
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(streamText) }}
                />
              ) : (
                <div className="flex items-center gap-2 text-text3 text-xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber animate-pulse-dot" />
                  {runningTool ? `running ${runningTool}...` : 'thinking...'}
                </div>
              )}
              {runningTool && streamText && (
                <div className="flex items-center gap-2 text-text3 text-xs mt-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber animate-pulse-dot" />
                  running {runningTool}...
                </div>
              )}
              {renderToolEvents(streamTools, 'stream')}
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input area */}
      <div className="border-t border-border bg-bg1 flex-shrink-0">
        <div className="max-w-[760px] mx-auto px-4 py-3 flex items-end gap-3">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            disabled={streaming}
            rows={1}
            className="flex-1 bg-bg2 border border-border rounded-sm px-3 py-2 text-text text-[13px] font-mono
              placeholder:text-text3 resize-none outline-none focus:border-border2
              disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <button
            onClick={sendMessage}
            disabled={streaming || !input.trim()}
            className="px-4 py-2 bg-amber text-bg text-xs font-bold tracking-wider rounded-sm
              hover:bg-amber2 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            SEND
          </button>
          <button
            onClick={handleClear}
            disabled={streaming}
            className="px-3 py-2 border border-border text-text3 text-xs tracking-wider rounded-sm
              hover:text-red hover:border-red transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            CLEAR
          </button>
        </div>
      </div>
    </div>
  );
}
