import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

interface ToastCtx {
  toast: (msg: string, duration?: number) => void;
}

const Ctx = createContext<ToastCtx>({ toast: () => {} });

export function useToast() {
  return useContext(Ctx).toast;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [msg, setMsg] = useState('');
  const [visible, setVisible] = useState(false);

  const toast = useCallback((text: string, duration = 2500) => {
    setMsg(text);
    setVisible(true);
    setTimeout(() => setVisible(false), duration);
  }, []);

  return (
    <Ctx.Provider value={{ toast }}>
      {children}
      <div
        className={`fixed bottom-12 right-6 bg-bg3 border border-border2 text-text px-4 py-2.5 rounded-sm text-xs z-50 transition-opacity duration-200 pointer-events-none ${
          visible ? 'opacity-100' : 'opacity-0'
        }`}
      >
        {msg}
      </div>
    </Ctx.Provider>
  );
}
