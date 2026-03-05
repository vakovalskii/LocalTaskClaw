export interface Agent {
  id: number;
  name: string;
  emoji: string;
  color: string;
  role: string;
  system_prompt: string;
  allowed_tools: string[] | null;
  allowed_paths: string[] | null;
}

export interface KanbanTask {
  id: number;
  title: string;
  description: string;
  column: string;
  status: string;
  agent_id: number | null;
  agent_name: string | null;
  agent_emoji: string | null;
  agent_color: string | null;
  agent_role: string | null;
  artifact: string | null;
  repeat_minutes: number;
  last_action: string | null;
  board_id: number;
}

export interface Board {
  id: number;
  name: string;
  emoji: string;
}

export interface ScheduledTask {
  id: number;
  name: string;
  prompt: string;
  interval_minutes: number;
  cron: string | null;
  enabled: boolean;
  last_run: string | null;
  next_run: string | null;
}

export interface FileEntry {
  name: string;
  path: string;
  type: 'file' | 'dir';
  size: number | null;
}

export interface Session {
  session_key: string;
  updated_at: string;
}

export interface TraceEvent {
  type: string;
  data: any;
  at: string;
}

export interface ToolEvent {
  name: string;
  args: any;
  success: boolean;
  result: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'tool';
  content: string;
}
