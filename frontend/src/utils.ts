export function escHtml(s: string): string {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export function fmtTime(ts: string | null): string {
  if (!ts) return '\u2014';
  return new Date(ts.includes('T') ? ts : ts + 'Z').toLocaleTimeString();
}

export function fmtBytes(n: number | null): string {
  if (!n) return '';
  if (n < 1024) return n + 'B';
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + 'K';
  return (n / 1024 / 1024).toFixed(1) + 'M';
}
