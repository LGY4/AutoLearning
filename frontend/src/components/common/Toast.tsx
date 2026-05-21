import { useEffect, useState, useCallback, createContext, useContext, type ReactNode } from "react";
import { CheckCircle2, X, AlertCircle, Sparkles, Trophy } from "lucide-react";

type ToastType = "success" | "error" | "info" | "achievement";

interface ToastItem {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
}

interface ToastContextValue {
  toast: (type: ToastType, title: string, message?: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}

const ICONS: Record<ToastType, typeof CheckCircle2> = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Sparkles,
  achievement: Trophy,
};

const COLORS: Record<ToastType, string> = {
  success: "#4ade80",
  error: "#f87171",
  info: "#60a5fa",
  achievement: "#facc15",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const addToast = useCallback((type: ToastType, title: string, message?: string) => {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev.slice(-4), { id, type, title, message }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  return (
    <ToastContext.Provider value={{ toast: addToast }}>
      {children}
      <div className="toast-container">
        {toasts.map((t) => {
          const Icon = ICONS[t.type];
          return (
            <div key={t.id} className={`toast-item ${t.type}`} style={{ borderColor: COLORS[t.type] }}>
              <Icon size={18} color={COLORS[t.type]} />
              <div className="toast-content">
                <span className="toast-title">{t.title}</span>
                {t.message && <span className="toast-message">{t.message}</span>}
              </div>
              <button className="toast-close" onClick={() => setToasts((p) => p.filter((x) => x.id !== t.id))}>
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
