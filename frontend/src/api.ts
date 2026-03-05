const API_BASE = `${window.location.protocol}//${window.location.hostname}:11387`;

export function getApiKey(): string {
  return localStorage.getItem('lc_api_key') || '';
}

export function setApiKey(key: string) {
  localStorage.setItem('lc_api_key', key);
}

export function clearApiKey() {
  localStorage.removeItem('lc_api_key');
}

export function getChatId(): number {
  return parseInt(localStorage.getItem('lc_chat_id') || '0');
}

export function setChatId(id: number) {
  localStorage.setItem('lc_chat_id', String(id));
}

function headers(): Record<string, string> {
  return { 'Content-Type': 'application/json', 'X-Api-Key': getApiKey() };
}

export async function api<T = any>(method: string, path: string, body?: any): Promise<T> {
  const opts: RequestInit = { method, headers: headers() };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(API_BASE + path, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function tryLogin(key: string): Promise<boolean> {
  const r = await fetch(API_BASE + '/health', { headers: { 'X-Api-Key': key } });
  if (!r.ok) return false;
  const r2 = await fetch(API_BASE + '/settings', { headers: { 'X-Api-Key': key } });
  return r2.ok;
}

export function apiStreamUrl(path: string): string {
  return API_BASE + path;
}

export function sseUrl(path: string): string {
  const key = getApiKey();
  return API_BASE + path + (key ? `&x_api_key=${encodeURIComponent(key)}` : '');
}

export { API_BASE };
