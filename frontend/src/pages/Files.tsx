import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../components/Toast';
import { fmtBytes } from '../utils';

interface FileEntry {
  name: string;
  is_dir: boolean;
  size: number | null;
}

export default function Files() {
  const toast = useToast();
  const [cwd, setCwd] = useState('');
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [filePath, setFilePath] = useState('');
  const [content, setContent] = useState('');
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadDir = async (path: string) => {
    try {
      const d = await api<{ files: FileEntry[]; path: string }>('GET', `/files?path=${encodeURIComponent(path)}`);
      setEntries(d.files || []);
      setCwd(d.path || path);
    } catch (e: any) {
      toast('Failed to list: ' + e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadDir(''); }, []);

  const openFile = async (path: string) => {
    try {
      const d = await api<{ content: string }>('GET', `/file?path=${encodeURIComponent(path)}`);
      setFilePath(path);
      setContent(d.content);
      setDirty(false);
    } catch (e: any) {
      toast('Failed to open: ' + e.message);
    }
  };

  const saveFile = async () => {
    if (!filePath) return;
    try {
      await api('POST', '/file', { path: filePath, content });
      toast('Saved');
      setDirty(false);
    } catch (e: any) {
      toast('Save failed: ' + e.message);
    }
  };

  const deleteFile = async () => {
    if (!filePath) return;
    if (!confirm(`Delete ${filePath}?`)) return;
    try {
      await api('DELETE', `/file?path=${encodeURIComponent(filePath)}`);
      toast('Deleted');
      setFilePath('');
      setContent('');
      setDirty(false);
      loadDir(cwd);
    } catch (e: any) {
      toast('Delete failed: ' + e.message);
    }
  };

  const navigate = (entry: FileEntry) => {
    if (entry.is_dir) {
      const next = cwd ? cwd + '/' + entry.name : entry.name;
      loadDir(next);
    } else {
      const path = cwd ? cwd + '/' + entry.name : entry.name;
      openFile(path);
    }
  };

  const goUp = () => {
    const parts = cwd.split('/').filter(Boolean);
    parts.pop();
    loadDir(parts.join('/'));
  };

  return (
    <div className="flex-1 flex overflow-hidden font-mono">
      {/* Left Panel - File Tree */}
      <div className="w-[260px] flex-shrink-0 border-r border-border overflow-y-auto bg-bg1">
        <div className="text-[10px] font-bold tracking-widest uppercase text-text3 border-b border-border px-3 py-2">
          FILES {cwd && <span className="text-text3 font-normal ml-1">/ {cwd}</span>}
        </div>

        {cwd && (
          <button
            onClick={goUp}
            className="w-full text-left px-3 py-1.5 text-xs text-amber hover:bg-bg2 transition-colors"
          >
            ..
          </button>
        )}

        {loading ? (
          <div className="px-3 py-2 text-text3 text-xs">Loading...</div>
        ) : (
          entries.map(e => (
            <button
              key={e.name}
              onClick={() => navigate(e)}
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-bg2 transition-colors flex items-center gap-2 group"
            >
              <span className="text-text3 text-[10px]">
                {e.is_dir ? '\u25B6' : '\u25CF'}
              </span>
              <span className={e.is_dir ? 'font-bold text-text' : 'text-text2'}>
                {e.name}
              </span>
              {!e.is_dir && e.size != null && (
                <span className="ml-auto text-[10px] text-text3 opacity-0 group-hover:opacity-100">
                  {fmtBytes(e.size)}
                </span>
              )}
            </button>
          ))
        )}

        {!loading && entries.length === 0 && (
          <div className="px-3 py-2 text-text3 text-xs">Empty directory</div>
        )}
      </div>

      {/* Right Panel - Editor */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Toolbar */}
        <div className="flex items-center gap-3 px-4 h-[40px] border-b border-border bg-bg1 flex-shrink-0">
          {filePath ? (
            <>
              <span className="text-amber text-xs flex-1 truncate">{filePath}</span>
              <button
                onClick={saveFile}
                className="bg-amber text-black font-bold text-[10px] px-3 py-1 hover:brightness-110 transition-all"
              >
                SAVE
              </button>
              <button
                onClick={deleteFile}
                className="border border-border2 text-red text-[10px] px-3 py-1 hover:bg-red/10 transition-colors"
              >
                DELETE
              </button>
            </>
          ) : (
            <span className="text-text3 text-xs">Select a file to edit</span>
          )}
        </div>

        {/* Editor */}
        <textarea
          value={content}
          onChange={e => { setContent(e.target.value); setDirty(true); }}
          className="flex-1 w-full bg-bg text-text text-xs p-4 font-mono resize-none focus:outline-none"
          spellCheck={false}
          disabled={!filePath}
          placeholder={filePath ? '' : 'No file selected'}
        />

        {dirty && (
          <div className="px-4 py-1 bg-bg1 border-t border-border text-[10px] text-amber">
            unsaved changes
          </div>
        )}
      </div>
    </div>
  );
}
