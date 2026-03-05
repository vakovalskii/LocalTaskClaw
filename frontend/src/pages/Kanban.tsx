import { useState, useEffect, useRef, useCallback } from 'react';
import { api, API_BASE, getApiKey } from '../api';
import { useToast } from '../components/Toast';
import type { Agent, KanbanTask, Board } from '../types';

// ─── Constants ──────────────────────────────────────────────────────────────

const COLUMNS = ['backlog', 'in_progress', 'review', 'needs_human', 'done'] as const;
type Column = (typeof COLUMNS)[number];

const COL_META: Record<Column, { label: string; color: string; dot: string }> = {
  backlog: { label: 'Backlog', color: 'text-text3', dot: 'bg-text3' },
  in_progress: { label: 'In Progress', color: 'text-blue', dot: 'bg-blue' },
  review: { label: 'Review', color: 'text-amber', dot: 'bg-amber' },
  needs_human: { label: 'Needs Human', color: 'text-red', dot: 'bg-red' },
  done: { label: 'Done', color: 'text-green', dot: 'bg-green' },
};

const STATUS_COLORS: Record<string, string> = {
  idle: 'bg-bg3 text-text3',
  running: 'bg-blue/20 text-blue animate-blink-slow',
  done: 'bg-green/20 text-green',
  verified: 'bg-green/20 text-green',
  error: 'bg-red/20 text-red',
};

interface ToolDef {
  name: string;
  description: string;
}

// ─── Main Kanban Component ──────────────────────────────────────────────────

export default function Kanban() {
  const toast = useToast();

  // Data
  const [boards, setBoards] = useState<Board[]>([]);
  const [activeBoard, setActiveBoard] = useState<number>(0);
  const [tasks, setTasks] = useState<KanbanTask[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const prevSnap = useRef('');

  // UI state
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [editingTask, setEditingTask] = useState<KanbanTask | null>(null);
  const [showAgentsPanel, setShowAgentsPanel] = useState(false);
  const [showAgentEditor, setShowAgentEditor] = useState(false);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);
  const [showArtifactModal, setShowArtifactModal] = useState(false);
  const [artifactContent, setArtifactContent] = useState('');
  const [showSpawnModal, setShowSpawnModal] = useState(false);
  const [renamingBoard, setRenamingBoard] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState('');

  // Drag state
  const draggedId = useRef<number | null>(null);
  const [dragOverCol, setDragOverCol] = useState<string | null>(null);

  // ─── Data Loading ───────────────────────────────────────────────────────

  const loadBoards = useCallback(async () => {
    try {
      const d = await api<{ boards: Board[] }>('GET', '/kanban/boards');
      setBoards(d.boards);
      if (d.boards.length > 0 && activeBoard === 0) {
        setActiveBoard(d.boards[0].id);
      }
    } catch { /* ignore */ }
  }, [activeBoard]);

  const loadTasks = useCallback(async () => {
    if (!activeBoard) return;
    try {
      const d = await api<{ tasks: KanbanTask[] }>('GET', `/kanban/boards/${activeBoard}/tasks`);
      const snap = JSON.stringify(d.tasks.map(t => ({ id: t.id, status: t.status, column: t.column, last_action: t.last_action })));
      if (snap !== prevSnap.current) {
        prevSnap.current = snap;
        setTasks(d.tasks);
      }
    } catch { /* ignore */ }
  }, [activeBoard]);

  const loadAgents = useCallback(async () => {
    try {
      const d = await api<{ agents: Agent[] }>('GET', '/agents');
      setAgents(d.agents);
    } catch { /* ignore */ }
  }, []);

  // Initial load
  useEffect(() => { loadBoards(); loadAgents(); }, []);
  useEffect(() => { if (activeBoard) loadTasks(); }, [activeBoard, loadTasks]);

  // Polling
  useEffect(() => {
    if (!activeBoard) return;
    const id = setInterval(() => { loadTasks(); }, 3000);
    return () => clearInterval(id);
  }, [activeBoard, loadTasks]);

  // ─── Board Actions ──────────────────────────────────────────────────────

  async function createBoard() {
    const name = prompt('Board name:');
    if (!name) return;
    try {
      const d = await api<{ board: Board }>('POST', '/kanban/boards', { name, emoji: '' });
      setBoards(b => [...b, d.board]);
      setActiveBoard(d.board.id);
      toast('Board created');
    } catch (e: any) { toast(e.message); }
  }

  async function deleteBoard(id: number) {
    if (!confirm('Delete this board and all its tasks?')) return;
    try {
      await api('DELETE', `/kanban/boards/${id}`);
      setBoards(b => b.filter(x => x.id !== id));
      if (activeBoard === id) {
        const remaining = boards.filter(x => x.id !== id);
        setActiveBoard(remaining.length > 0 ? remaining[0].id : 0);
      }
      toast('Board deleted');
    } catch (e: any) { toast(e.message); }
  }

  async function renameBoard(id: number, name: string) {
    try {
      await api('PATCH', `/kanban/boards/${id}`, { name });
      setBoards(b => b.map(x => x.id === id ? { ...x, name } : x));
      toast('Board renamed');
    } catch (e: any) { toast(e.message); }
  }

  // ─── Task Actions ───────────────────────────────────────────────────────

  async function createOrUpdateTask(data: {
    title: string; description: string; agent_id: number | null;
    column: string; repeat_minutes: number;
  }) {
    try {
      if (editingTask) {
        await api('PATCH', `/kanban/tasks/${editingTask.id}`, data);
        toast('Task updated');
      } else {
        await api('POST', `/kanban/boards/${activeBoard}/tasks`, data);
        toast('Task created');
      }
      setShowTaskModal(false);
      setEditingTask(null);
      loadTasks();
    } catch (e: any) { toast(e.message); }
  }

  async function deleteTask(id: number) {
    if (!confirm('Delete task?')) return;
    try {
      await api('DELETE', `/kanban/tasks/${id}`);
      loadTasks();
      toast('Task deleted');
    } catch (e: any) { toast(e.message); }
  }

  async function moveTask(id: number, column: string) {
    try {
      await api('PATCH', `/kanban/tasks/${id}`, { column });
      if (column === 'in_progress') {
        await api('POST', `/kanban/tasks/${id}/run`);
      }
      loadTasks();
    } catch (e: any) { toast(e.message); }
  }

  async function runTask(id: number) {
    try {
      await api('POST', `/kanban/tasks/${id}/run`);
      toast('Task started');
      loadTasks();
    } catch (e: any) { toast(e.message); }
  }

  async function stopTask(id: number) {
    try {
      await api('POST', `/kanban/tasks/${id}/stop`);
      toast('Task stopped');
      loadTasks();
    } catch (e: any) { toast(e.message); }
  }

  function moveTaskDir(task: KanbanTask, dir: -1 | 1) {
    const idx = COLUMNS.indexOf(task.column as Column);
    const newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= COLUMNS.length) return;
    moveTask(task.id, COLUMNS[newIdx]);
  }

  // ─── Drag & Drop ───────────────────────────────────────────────────────

  function onDragStart(taskId: number) {
    draggedId.current = taskId;
  }

  function onDragOver(e: React.DragEvent, col: string) {
    e.preventDefault();
    setDragOverCol(col);
  }

  function onDragLeave() {
    setDragOverCol(null);
  }

  function onDrop(col: string) {
    setDragOverCol(null);
    if (draggedId.current !== null) {
      moveTask(draggedId.current, col);
      draggedId.current = null;
    }
  }

  // ─── Render ─────────────────────────────────────────────────────────────

  const colTasks = (col: string) => tasks.filter(t => t.column === col);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Board Tabs */}
      <div className="flex items-center h-[36px] border-b border-border bg-bg1 flex-shrink-0 overflow-x-auto">
        {boards.map(b => (
          <div
            key={b.id}
            className={`flex items-center gap-1.5 px-4 h-full text-[11px] font-medium tracking-wide border-r border-border cursor-pointer transition-all relative group ${
              b.id === activeBoard
                ? 'text-amber bg-bg2 after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-amber'
                : 'text-text2 hover:text-text hover:bg-bg2'
            }`}
            onClick={() => { setActiveBoard(b.id); prevSnap.current = ''; }}
            onDoubleClick={() => { setRenamingBoard(b.id); setRenameValue(b.name); }}
          >
            {renamingBoard === b.id ? (
              <input
                autoFocus
                className="bg-transparent border-b border-amber text-amber text-[11px] w-20 outline-none"
                value={renameValue}
                onChange={e => setRenameValue(e.target.value)}
                onBlur={() => { renameBoard(b.id, renameValue); setRenamingBoard(null); }}
                onKeyDown={e => {
                  if (e.key === 'Enter') { renameBoard(b.id, renameValue); setRenamingBoard(null); }
                  if (e.key === 'Escape') setRenamingBoard(null);
                }}
                onClick={e => e.stopPropagation()}
              />
            ) : (
              <>
                {b.emoji && <span>{b.emoji}</span>}
                <span>{b.name}</span>
              </>
            )}
            {boards.length > 1 && b.id !== boards[0]?.id && (
              <button
                className="ml-1 text-text3 hover:text-red opacity-0 group-hover:opacity-100 transition-opacity"
                onClick={e => { e.stopPropagation(); deleteBoard(b.id); }}
                title="Delete board"
              >x</button>
            )}
          </div>
        ))}
        <button
          className="px-4 h-full text-[11px] text-text3 hover:text-amber border-r border-border hover:bg-bg2 transition-all"
          onClick={createBoard}
        >+ Board</button>
      </div>

      {/* Toolbar */}
      <div className="flex items-center h-[38px] border-b border-border bg-bg1 px-4 gap-3 flex-shrink-0">
        <span className="text-[11px] font-bold tracking-wider text-text2">KANBAN</span>
        <div className="flex-1" />
        <button
          className="px-3 py-1 text-[10px] font-medium border border-border text-text2 hover:text-text hover:bg-bg2 transition-all"
          onClick={() => { setShowAgentsPanel(true); loadAgents(); }}
        >AGENTS</button>
        <button
          className="px-3 py-1 text-[10px] font-medium border border-amber/30 text-amber hover:bg-amber/10 transition-all"
          onClick={() => setShowSpawnModal(true)}
        >SPAWN PROJECT</button>
        <button
          className="px-3 py-1 text-[10px] font-medium border border-border text-text2 hover:text-amber hover:border-amber/30 hover:bg-bg2 transition-all"
          onClick={() => { setEditingTask(null); setShowTaskModal(true); }}
        >+ NEW TASK</button>
      </div>

      {/* Columns */}
      <div className="flex-1 overflow-x-auto overflow-y-hidden p-4 flex gap-4">
        {COLUMNS.map(col => {
          const meta = COL_META[col];
          const ct = colTasks(col);
          return (
            <div
              key={col}
              className={`flex-shrink-0 w-[300px] flex flex-col bg-bg1 border border-border rounded-sm overflow-hidden transition-all ${
                dragOverCol === col ? 'border-amber/50 bg-bg2' : ''
              }`}
              onDragOver={e => onDragOver(e, col)}
              onDragLeave={onDragLeave}
              onDrop={() => onDrop(col)}
            >
              {/* Column Header */}
              <div className="flex items-center px-3 py-2.5 border-b border-border gap-2">
                <div className={`w-2 h-2 rounded-full ${meta.dot}`} />
                <span className={`text-[11px] font-medium tracking-wide ${meta.color}`}>{meta.label}</span>
                <span className="text-[10px] text-text3 bg-bg3 px-1.5 rounded-sm">{ct.length}</span>
                {col === 'backlog' && (
                  <button
                    className="ml-auto text-text3 hover:text-amber text-xs transition-colors"
                    onClick={() => { setEditingTask(null); setShowTaskModal(true); }}
                    title="Add task"
                  >+</button>
                )}
              </div>

              {/* Cards */}
              <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-2">
                {ct.map(task => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    onDragStart={() => onDragStart(task.id)}
                    onMoveLeft={() => moveTaskDir(task, -1)}
                    onMoveRight={() => moveTaskDir(task, 1)}
                    onRun={() => runTask(task.id)}
                    onStop={() => stopTask(task.id)}
                    onEdit={() => { setEditingTask(task); setShowTaskModal(true); }}
                    onDelete={() => deleteTask(task.id)}
                    onArtifact={() => { setArtifactContent(task.artifact || ''); setShowArtifactModal(true); }}
                    onDone={() => moveTask(task.id, 'done')}
                    showDone={col === 'review'}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Modals / Panels */}
      {showTaskModal && (
        <TaskModal
          task={editingTask}
          agents={agents}
          boardId={activeBoard}
          onSave={createOrUpdateTask}
          onClose={() => { setShowTaskModal(false); setEditingTask(null); }}
        />
      )}

      {showAgentsPanel && (
        <AgentsPanel
          agents={agents}
          onClose={() => setShowAgentsPanel(false)}
          onEdit={agent => { setEditingAgent(agent); setShowAgentEditor(true); }}
          onRefresh={loadAgents}
        />
      )}

      {showAgentEditor && (
        <AgentEditorModal
          agent={editingAgent}
          onClose={() => { setShowAgentEditor(false); setEditingAgent(null); }}
          onSaved={() => { loadAgents(); setShowAgentEditor(false); setEditingAgent(null); }}
        />
      )}

      {showArtifactModal && (
        <ArtifactModal
          content={artifactContent}
          onClose={() => setShowArtifactModal(false)}
        />
      )}

      {showSpawnModal && (
        <SpawnModal
          onClose={() => setShowSpawnModal(false)}
          onComplete={(boardId: number) => {
            setShowSpawnModal(false);
            loadBoards().then(() => {
              setActiveBoard(boardId);
              prevSnap.current = '';
            });
          }}
        />
      )}
    </div>
  );
}

// ─── Task Card ────────────────────────────────────────────────────────────────

function TaskCard({
  task, onDragStart, onMoveLeft, onMoveRight, onRun, onStop,
  onEdit, onDelete, onArtifact, onDone, showDone,
}: {
  task: KanbanTask;
  onDragStart: () => void;
  onMoveLeft: () => void;
  onMoveRight: () => void;
  onRun: () => void;
  onStop: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onArtifact: () => void;
  onDone: () => void;
  showDone: boolean;
}) {
  return (
    <div
      draggable
      onDragStart={onDragStart}
      className="bg-bg2 border border-border rounded-sm p-2.5 cursor-grab active:cursor-grabbing hover:border-border2 transition-all group"
    >
      {/* Agent badge */}
      {task.agent_name && (
        <div className="flex items-center gap-1.5 mb-1.5">
          <span
            className="text-[10px] px-1.5 py-0.5 rounded-sm border"
            style={{ borderColor: task.agent_color || '#534d42', color: task.agent_color || '#534d42' }}
          >
            {task.agent_emoji || ''} {task.agent_name}
          </span>
        </div>
      )}

      {/* Title + repeat */}
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-[12px] font-medium text-text leading-tight">{task.title}</span>
        {task.repeat_minutes > 0 && (
          <span className="text-[10px] text-text3" title={`Repeats every ${task.repeat_minutes}m`}>
            {/* recycle icon */}
            <svg className="w-3 h-3 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </span>
        )}
      </div>

      {/* Description */}
      {task.description && (
        <p className="text-[10px] text-text2 leading-relaxed mb-1.5 line-clamp-3">{task.description}</p>
      )}

      {/* Status badge */}
      <div className="flex items-center gap-1.5 mb-1">
        <span className={`text-[9px] px-1.5 py-0.5 rounded-sm font-medium ${STATUS_COLORS[task.status] || STATUS_COLORS.idle}`}>
          {task.status}
        </span>
      </div>

      {/* Activity line */}
      {task.status === 'running' && task.last_action && (
        <div className="flex items-center gap-1.5 mb-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-blue animate-pulse-dot" />
          <span className="text-[9px] text-text3 truncate">{task.last_action}</span>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-1 mt-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
        <ActionBtn title="Move left" onClick={onMoveLeft}>
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
        </ActionBtn>
        <ActionBtn title="Move right" onClick={onMoveRight}>
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
        </ActionBtn>
        <div className="w-px h-3 bg-border mx-0.5" />
        <ActionBtn title="Run" onClick={onRun} className="hover:text-green">
          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
        </ActionBtn>
        <ActionBtn title="Stop" onClick={onStop} className="hover:text-red">
          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" /></svg>
        </ActionBtn>
        <ActionBtn title="Edit" onClick={onEdit}>
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
        </ActionBtn>
        {task.artifact && (
          <ActionBtn title="Artifact" onClick={onArtifact} className="hover:text-amber">
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" strokeWidth={2} /></svg>
          </ActionBtn>
        )}
        <ActionBtn title="Delete" onClick={onDelete} className="hover:text-red">
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
        </ActionBtn>
        {showDone && (
          <ActionBtn title="Mark done" onClick={onDone} className="hover:text-green">
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
          </ActionBtn>
        )}
      </div>
    </div>
  );
}

function ActionBtn({ children, onClick, title, className = '' }: {
  children: React.ReactNode; onClick: () => void; title: string; className?: string;
}) {
  return (
    <button
      className={`p-1 text-text3 hover:text-text transition-colors ${className}`}
      onClick={e => { e.stopPropagation(); onClick(); }}
      title={title}
    >{children}</button>
  );
}

// ─── Task Modal ───────────────────────────────────────────────────────────────

function TaskModal({
  task, agents, boardId: _boardId, onSave, onClose,
}: {
  task: KanbanTask | null;
  agents: Agent[];
  boardId: number;
  onSave: (data: { title: string; description: string; agent_id: number | null; column: string; repeat_minutes: number }) => void;
  onClose: () => void;
}) {
  void _boardId;
  const [title, setTitle] = useState(task?.title || '');
  const [description, setDescription] = useState(task?.description || '');
  const [agentId, setAgentId] = useState<number | null>(task?.agent_id || null);
  const [column, setColumn] = useState(task?.column || 'backlog');
  const [repeatMinutes, setRepeatMinutes] = useState(task?.repeat_minutes || 0);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    onSave({ title: title.trim(), description, agent_id: agentId, column, repeat_minutes: repeatMinutes });
  }

  return (
    <Overlay onClose={onClose}>
      <div className="bg-bg1 border border-border rounded-sm w-[460px] max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <span className="text-[12px] font-bold text-text tracking-wide">{task ? 'EDIT TASK' : 'NEW TASK'}</span>
          <button className="text-text3 hover:text-text" onClick={onClose}>x</button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 flex flex-col gap-3">
          <Field label="Title">
            <input
              className="w-full bg-bg2 border border-border text-text text-[12px] px-3 py-2 outline-none focus:border-amber/50"
              value={title}
              onChange={e => setTitle(e.target.value)}
              autoFocus
            />
          </Field>
          <Field label="Description">
            <textarea
              className="w-full bg-bg2 border border-border text-text text-[12px] px-3 py-2 outline-none focus:border-amber/50 resize-none h-20"
              value={description}
              onChange={e => setDescription(e.target.value)}
            />
          </Field>
          <Field label="Agent">
            <select
              className="w-full bg-bg2 border border-border text-text text-[12px] px-3 py-2 outline-none"
              value={agentId || ''}
              onChange={e => setAgentId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">None</option>
              {agents.map(a => (
                <option key={a.id} value={a.id}>{a.emoji} {a.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Column">
            <select
              className="w-full bg-bg2 border border-border text-text text-[12px] px-3 py-2 outline-none"
              value={column}
              onChange={e => setColumn(e.target.value)}
            >
              {COLUMNS.map(c => (
                <option key={c} value={c}>{COL_META[c].label}</option>
              ))}
            </select>
          </Field>
          <Field label="Repeat (minutes, 0 = off)">
            <input
              type="number"
              min={0}
              className="w-full bg-bg2 border border-border text-text text-[12px] px-3 py-2 outline-none focus:border-amber/50"
              value={repeatMinutes}
              onChange={e => setRepeatMinutes(Number(e.target.value))}
            />
          </Field>
          <div className="flex justify-end gap-2 mt-2">
            <button type="button" className="px-4 py-1.5 text-[11px] text-text3 border border-border hover:bg-bg2" onClick={onClose}>Cancel</button>
            <button type="submit" className="px-4 py-1.5 text-[11px] text-amber border border-amber/30 hover:bg-amber/10">{task ? 'Save' : 'Create'}</button>
          </div>
        </form>
      </div>
    </Overlay>
  );
}

// ─── Agents Side Panel ────────────────────────────────────────────────────────

function AgentsPanel({
  agents, onClose, onEdit, onRefresh,
}: {
  agents: Agent[];
  onClose: () => void;
  onEdit: (agent: Agent) => void;
  onRefresh: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState('');
  const [emoji, setEmoji] = useState('');
  const [role, setRole] = useState('');

  async function addAgent(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await api('POST', '/agents', { name: name.trim(), emoji: emoji || '🤖', color: '#60a5fa', role: role || 'worker', system_prompt: '', allowed_tools: null, allowed_paths: null });
      setName(''); setEmoji(''); setRole('');
      onRefresh();
      toast('Agent created');
    } catch (err: any) { toast(err.message); }
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end" onClick={onClose}>
      <div className="w-[340px] h-full bg-bg1 border-l border-border flex flex-col overflow-hidden animate-slide-in" onClick={e => e.stopPropagation()}>
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <span className="text-[12px] font-bold text-text tracking-wide">AGENTS</span>
          <button className="text-text3 hover:text-text" onClick={onClose}>x</button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
          {agents.map(a => (
            <div key={a.id} className="flex items-center gap-2 px-3 py-2 bg-bg2 border border-border rounded-sm">
              <span className="text-base">{a.emoji || '🤖'}</span>
              <div className="flex-1 min-w-0">
                <div className="text-[11px] font-medium text-text truncate">{a.name}</div>
                <span className="text-[9px] px-1.5 py-0.5 rounded-sm bg-bg3 text-text3">{a.role}</span>
              </div>
              <button
                className="text-text3 hover:text-amber text-[10px] transition-colors"
                onClick={() => onEdit(a)}
              >edit</button>
            </div>
          ))}
        </div>

        {/* Add agent form */}
        <form onSubmit={addAgent} className="p-3 border-t border-border flex flex-col gap-2">
          <span className="text-[10px] text-text3 tracking-wide">ADD AGENT</span>
          <div className="flex gap-2">
            <input
              className="w-10 bg-bg2 border border-border text-text text-[12px] px-2 py-1.5 outline-none text-center"
              placeholder="🤖"
              value={emoji}
              onChange={e => setEmoji(e.target.value)}
            />
            <input
              className="flex-1 bg-bg2 border border-border text-text text-[12px] px-2 py-1.5 outline-none focus:border-amber/50"
              placeholder="Name"
              value={name}
              onChange={e => setName(e.target.value)}
            />
          </div>
          <input
            className="w-full bg-bg2 border border-border text-text text-[12px] px-2 py-1.5 outline-none focus:border-amber/50"
            placeholder="Role"
            value={role}
            onChange={e => setRole(e.target.value)}
          />
          <button type="submit" className="px-3 py-1.5 text-[11px] text-amber border border-amber/30 hover:bg-amber/10 transition-all">Add</button>
        </form>
      </div>
    </div>
  );
}

// ─── Agent Editor Modal (Full Screen) ─────────────────────────────────────────

function AgentEditorModal({
  agent, onClose, onSaved,
}: {
  agent: Agent | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [tab, setTab] = useState<'identity' | 'prompt' | 'tools' | 'files'>('identity');
  const [name, setName] = useState(agent?.name || '');
  const [emoji, setEmoji] = useState(agent?.emoji || '');
  const [color, setColor] = useState(agent?.color || '#60a5fa');
  const [role, setRole] = useState(agent?.role || '');
  const [systemPrompt, setSystemPrompt] = useState(agent?.system_prompt || '');
  const [allowedTools, setAllowedTools] = useState<string[]>(agent?.allowed_tools || []);
  const [allowedPaths, setAllowedPaths] = useState((agent?.allowed_paths || []).join('\n'));
  const [availableTools, setAvailableTools] = useState<ToolDef[]>([]);
  const [promptPreview, setPromptPreview] = useState('');
  const [toolsCount, setToolsCount] = useState(0);

  useEffect(() => {
    api<{ tools: ToolDef[] }>('GET', '/agents/tools').then(d => setAvailableTools(d.tools)).catch(() => {});
  }, []);

  useEffect(() => {
    if (agent && tab === 'prompt') {
      api<{ full_prompt: string; tools_count: number }>('GET', `/agents/${agent.id}/prompt-preview`)
        .then(d => { setPromptPreview(d.full_prompt); setToolsCount(d.tools_count); })
        .catch(() => {});
    }
  }, [agent, tab]);

  async function handleSave() {
    const paths = allowedPaths.trim() ? allowedPaths.split('\n').map(p => p.trim()).filter(Boolean) : null;
    const tools = allowedTools.length > 0 ? allowedTools : null;
    const body = { name, emoji, color, role, system_prompt: systemPrompt, allowed_tools: tools, allowed_paths: paths };
    try {
      if (agent) {
        await api('PATCH', `/agents/${agent.id}`, body);
      } else {
        await api('POST', '/agents', body);
      }
      toast('Agent saved');
      onSaved();
    } catch (e: any) { toast(e.message); }
  }

  async function handleDelete() {
    if (!agent || !confirm('Delete this agent?')) return;
    try {
      await api('DELETE', `/agents/${agent.id}`);
      toast('Agent deleted');
      onSaved();
    } catch (e: any) { toast(e.message); }
  }

  function toggleTool(name: string) {
    setAllowedTools(prev =>
      prev.includes(name) ? prev.filter(t => t !== name) : [...prev, name]
    );
  }

  const TABS = [
    { key: 'identity', label: 'Identity' },
    { key: 'prompt', label: 'System Prompt' },
    { key: 'tools', label: 'Tools' },
    { key: 'files', label: 'File Access' },
  ] as const;

  return (
    <div className="fixed inset-0 z-50 bg-bg flex flex-col">
      {/* Header */}
      <div className="flex items-center h-[42px] border-b border-border bg-bg1 px-4 flex-shrink-0">
        <span className="text-[12px] font-bold text-text tracking-wide">{agent ? 'EDIT AGENT' : 'NEW AGENT'}</span>
        <span className="ml-3 text-base">{emoji || '🤖'}</span>
        <span className="ml-2 text-[11px] text-text2">{name || 'Unnamed'}</span>
        <div className="flex-1" />
        <button className="text-text3 hover:text-text text-[11px]" onClick={onClose}>Close</button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border bg-bg1 flex-shrink-0">
        {TABS.map(t => (
          <button
            key={t.key}
            className={`px-5 py-2 text-[11px] font-medium tracking-wide border-r border-border transition-all relative ${
              tab === t.key
                ? 'text-amber bg-bg2 after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-amber'
                : 'text-text2 hover:text-text hover:bg-bg2'
            }`}
            onClick={() => setTab(t.key)}
          >{t.label}</button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {tab === 'identity' && (
          <div className="max-w-lg flex flex-col gap-4">
            <Field label="Name">
              <input className="w-full bg-bg2 border border-border text-text text-[12px] px-3 py-2 outline-none focus:border-amber/50" value={name} onChange={e => setName(e.target.value)} />
            </Field>
            <Field label="Emoji">
              <input className="w-full bg-bg2 border border-border text-text text-[12px] px-3 py-2 outline-none focus:border-amber/50" value={emoji} onChange={e => setEmoji(e.target.value)} />
            </Field>
            <Field label="Color">
              <div className="flex items-center gap-3">
                <input type="color" value={color} onChange={e => setColor(e.target.value)} className="w-8 h-8 bg-transparent border border-border cursor-pointer" />
                <input className="flex-1 bg-bg2 border border-border text-text text-[12px] px-3 py-2 outline-none focus:border-amber/50" value={color} onChange={e => setColor(e.target.value)} />
              </div>
            </Field>
            <Field label="Role">
              <input className="w-full bg-bg2 border border-border text-text text-[12px] px-3 py-2 outline-none focus:border-amber/50" value={role} onChange={e => setRole(e.target.value)} />
            </Field>
          </div>
        )}

        {tab === 'prompt' && (
          <div className="flex flex-col gap-4 max-w-3xl">
            <Field label="System Prompt">
              <textarea
                className="w-full bg-bg2 border border-border text-text text-[12px] px-3 py-2 outline-none focus:border-amber/50 resize-none h-64 font-mono"
                value={systemPrompt}
                onChange={e => setSystemPrompt(e.target.value)}
              />
            </Field>
            {promptPreview && (
              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-text3 tracking-wide">PREVIEW (tools: {toolsCount})</span>
                <pre className="bg-bg2 border border-border text-[10px] text-text2 p-3 max-h-64 overflow-y-auto whitespace-pre-wrap">{promptPreview}</pre>
              </div>
            )}
          </div>
        )}

        {tab === 'tools' && (
          <div className="max-w-lg flex flex-col gap-2">
            <span className="text-[10px] text-text3 mb-2">Select tools this agent can use (empty = all tools)</span>
            {availableTools.map(t => (
              <label key={t.name} className="flex items-start gap-2 px-3 py-2 bg-bg2 border border-border rounded-sm cursor-pointer hover:border-border2 transition-all">
                <input
                  type="checkbox"
                  checked={allowedTools.includes(t.name)}
                  onChange={() => toggleTool(t.name)}
                  className="mt-0.5 accent-amber"
                />
                <div className="flex-1 min-w-0">
                  <div className="text-[11px] text-text font-medium">{t.name}</div>
                  <div className="text-[9px] text-text3">{t.description}</div>
                </div>
              </label>
            ))}
          </div>
        )}

        {tab === 'files' && (
          <div className="max-w-lg flex flex-col gap-4">
            <Field label="Allowed Paths (one per line, empty = all)">
              <textarea
                className="w-full bg-bg2 border border-border text-text text-[12px] px-3 py-2 outline-none focus:border-amber/50 resize-none h-48 font-mono"
                value={allowedPaths}
                onChange={e => setAllowedPaths(e.target.value)}
                placeholder="/path/to/allowed/dir&#10;/another/path"
              />
            </Field>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center gap-2 px-6 py-3 border-t border-border bg-bg1 flex-shrink-0">
        {agent && (
          <button className="px-4 py-1.5 text-[11px] text-red border border-red/30 hover:bg-red/10 transition-all" onClick={handleDelete}>Delete</button>
        )}
        <div className="flex-1" />
        <button className="px-4 py-1.5 text-[11px] text-text3 border border-border hover:bg-bg2 transition-all" onClick={onClose}>Cancel</button>
        <button className="px-4 py-1.5 text-[11px] text-amber border border-amber/30 hover:bg-amber/10 transition-all" onClick={handleSave}>Save</button>
      </div>
    </div>
  );
}

// ─── Artifact Modal ───────────────────────────────────────────────────────────

function ArtifactModal({ content, onClose }: { content: string; onClose: () => void }) {
  return (
    <Overlay onClose={onClose}>
      <div className="bg-bg1 border border-border rounded-sm w-[600px] max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <span className="text-[12px] font-bold text-text tracking-wide">ARTIFACT</span>
          <button className="text-text3 hover:text-text" onClick={onClose}>x</button>
        </div>
        <pre className="p-4 text-[11px] text-text2 whitespace-pre-wrap overflow-y-auto flex-1 font-mono">{content || '(empty)'}</pre>
      </div>
    </Overlay>
  );
}

// ─── Spawn Project Modal ──────────────────────────────────────────────────────

function SpawnModal({
  onClose, onComplete,
}: {
  onClose: () => void;
  onComplete: (boardId: number) => void;
}) {
  const [description, setDescription] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const logRef = useRef<HTMLDivElement>(null);
  const [boardId, setBoardId] = useState<number | null>(null);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [log]);

  async function handleSpawn() {
    if (!description.trim() || streaming) return;
    setStreaming(true);
    setLog([]);
    setBoardId(null);

    try {
      const resp = await fetch(`${API_BASE}/spawn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Api-Key': getApiKey() },
        body: JSON.stringify({ description: description.trim(), stream: true }),
      });

      if (!resp.ok) {
        const errText = await resp.text();
        setLog(prev => [...prev, `[error] ${errText}`]);
        setStreaming(false);
        return;
      }

      const reader = resp.body?.getReader();
      if (!reader) { setStreaming(false); return; }

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
          const raw = line.slice(6);
          try {
            const evt = JSON.parse(raw);
            if (evt.type === 'text') {
              setLog(prev => [...prev, evt.content]);
            } else if (evt.type === 'tool_start') {
              setLog(prev => [...prev, `[tool] ${evt.name}...`]);
            } else if (evt.type === 'tool_end') {
              setLog(prev => [...prev, `[tool] ${evt.name} done`]);
            } else if (evt.type === 'done') {
              if (evt.board_id) setBoardId(evt.board_id);
              setLog(prev => [...prev, '[done] Project spawned successfully']);
            }
          } catch { /* non-JSON line */ }
        }
      }
    } catch (e: any) {
      setLog(prev => [...prev, `[error] ${e.message}`]);
    }

    setStreaming(false);
  }

  return (
    <Overlay onClose={streaming ? undefined : onClose}>
      <div className="bg-bg1 border border-border rounded-sm w-[560px] max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <span className="text-[12px] font-bold text-text tracking-wide">SPAWN PROJECT</span>
          {!streaming && <button className="text-text3 hover:text-text" onClick={onClose}>x</button>}
        </div>

        <div className="p-4 flex flex-col gap-3">
          <Field label="Describe your project">
            <textarea
              className="w-full bg-bg2 border border-border text-text text-[12px] px-3 py-2 outline-none focus:border-amber/50 resize-none h-24 font-mono"
              value={description}
              onChange={e => setDescription(e.target.value)}
              disabled={streaming}
              placeholder="e.g. Build a REST API for managing inventory with CRUD endpoints..."
            />
          </Field>

          {log.length > 0 && (
            <div ref={logRef} className="bg-bg2 border border-border p-3 max-h-56 overflow-y-auto">
              {log.map((line, i) => (
                <div key={i} className={`text-[10px] leading-relaxed font-mono ${
                  line.startsWith('[error]') ? 'text-red' :
                  line.startsWith('[tool]') ? 'text-blue' :
                  line.startsWith('[done]') ? 'text-green' :
                  'text-text2'
                }`}>{line}</div>
              ))}
              {streaming && <span className="inline-block w-1.5 h-3 bg-amber animate-blink ml-1" />}
            </div>
          )}

          <div className="flex justify-end gap-2">
            {!streaming && (
              <button className="px-4 py-1.5 text-[11px] text-text3 border border-border hover:bg-bg2" onClick={onClose}>Cancel</button>
            )}
            {!streaming && !boardId && (
              <button
                className="px-4 py-1.5 text-[11px] text-amber border border-amber/30 hover:bg-amber/10 disabled:opacity-40"
                onClick={handleSpawn}
                disabled={!description.trim()}
              >Spawn</button>
            )}
            {boardId && (
              <button
                className="px-4 py-1.5 text-[11px] text-green border border-green/30 hover:bg-green/10"
                onClick={() => onComplete(boardId)}
              >Open Board</button>
            )}
          </div>
        </div>
      </div>
    </Overlay>
  );
}

// ─── Shared UI helpers ────────────────────────────────────────────────────────

function Overlay({ children, onClose }: { children: React.ReactNode; onClose?: () => void }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center" onClick={onClose}>
      {children}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-[10px] text-text3 tracking-wide uppercase">{label}</label>
      {children}
    </div>
  );
}
