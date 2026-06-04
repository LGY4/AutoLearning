import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import { Menu, X } from "lucide-react";
import { useAppContext, EMPTY_PATH } from "./context/AppContext";
import { useAuth } from "./hooks/useAuth";
import { useLearning } from "./hooks/useLearning";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { Spinner } from "./components/common/Spinner";
import { Sidebar } from "./components/sidebar/Sidebar";
import { AuthModal } from "./components/modals/AuthModal";
import { CreateAgentModal } from "./components/modals/CreateAgentModal";
import { SelectAgentModal } from "./components/modals/SelectAgentModal";
import { ModelConfigModal } from "./components/modals/ModelConfigModal";
import { apiPost } from "./api/client";
import type { BaseAgentCreateRequest, BaseAgentProfile } from "./types/baseline";

const HomePage = lazy(() => import("./pages/HomePage").then((m) => ({ default: m.HomePage })));
const LearningPage = lazy(() => import("./pages/LearningPage").then((m) => ({ default: m.LearningPage })));
const DashboardPage = lazy(() => import("./pages/DashboardPage").then((m) => ({ default: m.DashboardPage })));
const LearningMapPage = lazy(() => import("./pages/LearningMapPage").then((m) => ({ default: m.LearningMapPage })));
const PracticePage = lazy(() => import("./pages/PracticePage").then((m) => ({ default: m.PracticePage })));
const GraphManagerPage = lazy(() => import("./pages/GraphManagerPage").then((m) => ({ default: m.GraphManagerPage })));
const ResourceLibraryPage = lazy(() => import("./pages/ResourceLibraryPage").then((m) => ({ default: m.ResourceLibraryPage })));
const VideoStudioPage = lazy(() => import("./pages/VideoStudioPage").then((m) => ({ default: m.VideoStudioPage })));
const CoursePage = lazy(() => import("./pages/CoursePage").then((m) => ({ default: m.CoursePage })));
const MediaStudioPage = lazy(() => import("./pages/MediaStudioPage").then((m) => ({ default: m.MediaStudioPage })));

const ALLOWED_INCOMPLETE = ["/", "/dashboard", "/courses", "/resources"];

function App() {
  const { state, dispatch } = useAppContext();
  const { login, register, logout, initAuth, loadUserBundle } = useAuth();
  const { loadConversation } = useLearning();
  const navigate = useNavigate();
  const location = useLocation();
  const corePagePreloaders = useMemo(
    () => [
      () => import("./pages/LearningPage"),
      () => import("./pages/DashboardPage"),
      () => import("./pages/LearningMapPage"),
      () => import("./pages/PracticePage"),
    ],
    []
  );
  const [authOpen, setAuthOpen] = useState(false);
  const [createAgentOpen, setCreateAgentOpen] = useState(false);
  const [selectAgentOpen, setSelectAgentOpen] = useState(false);
  const [modelConfigOpen, setModelConfigOpen] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [appInitializing, setAppInitializing] = useState(true);

  useEffect(() => {
    let mounted = true;
    void initAuth().then((ok) => {
      if (!mounted) return;
      if (!ok) { dispatch({ type: "SET_ERROR", payload: null }); setAuthOpen(true); }
      setAppInitializing(false);
    });
    return () => {
      mounted = false;
    };
  }, [initAuth]);

  // Redirect to home if profile is incomplete (force diagnostic).
  // Bypasses redirect if user already completed diagnostic (localStorage flag).
  // Only fires after profile has actually been loaded from server.
  useEffect(() => {
    if (!state.user || !state.profileLoaded) return;
    if (ALLOWED_INCOMPLETE.includes(location.pathname)) return;
    if (state.profile.completeness_score > 0.5) return;
    if (localStorage.getItem(`diagnostic_completed_${state.user.id}`)) return;
    navigate("/", { replace: true });
  }, [location.pathname, navigate, state.profile.completeness_score, state.profileLoaded, state.user]);

  useEffect(() => {
    setMobileSidebarOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (appInitializing || !state.user) return;
    corePagePreloaders.forEach((preload) => {
      void preload();
    });
  }, [appInitializing, corePagePreloaders, state.user]);

  useEffect(() => {
    if (!mobileSidebarOpen) return;

    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileSidebarOpen(false);
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [mobileSidebarOpen]);

  const handleAuthSubmit = async (payload: {
    username: string;
    password: string;
    real_name?: string;
    major?: string;
    grade?: string;
    school?: string;
    isLogin: boolean;
  }) => {
    try {
      if (payload.isLogin) {
        await login(payload.username, payload.password);
      } else {
        await register(payload);
      }
      setAuthOpen(false);
    } catch (err) {
      dispatch({ type: "SET_ERROR", payload: err instanceof Error ? err.message : "登录失败" });
    }
  };

  const handleCreateAgent = async (payload: { name: string; description: string; system_prompt: string; applies_to: string[] }) => {
    if (!state.user) return;
    try {
      const req: BaseAgentCreateRequest = {
        user_id: state.user.id,
        name: payload.name,
        description: payload.description,
        system_prompt: payload.system_prompt,
        applies_to: payload.applies_to as BaseAgentCreateRequest["applies_to"],
        model_provider: "spark",
        output_style: "structured",
      };
      const created = await apiPost<BaseAgentProfile>("/agents/base-agents", req);
      dispatch({ type: "SET_AGENTS", payload: [...state.baseAgents, created] });
      dispatch({ type: "SET_SELECTED_AGENT", payload: created.agent_id });
      setCreateAgentOpen(false);
      dispatch({ type: "SET_NOTICE", payload: `已创建并选中：${created.name}` });
    } catch (err) {
      dispatch({ type: "SET_ERROR", payload: err instanceof Error ? err.message : "创建失败" });
    }
  };

  const handleNewSession = useCallback(() => {
    navigate("/chat");
    dispatch({ type: "SET_SELECTED_CONVERSATION", payload: null });
    dispatch({ type: "SET_ACTIVE_MESSAGES", payload: [] });
    dispatch({ type: "SET_WORKFLOW", payload: null });
    dispatch({ type: "SET_ERROR", payload: null });
    setMobileSidebarOpen(false);
  }, [dispatch, navigate]);

  const handleLoadHistory = useCallback(() => {
    void loadUserBundle();
  }, [loadUserBundle]);

  const handleLoadConversation = useCallback((id: string, _conversationType?: string) => {
    navigate("/chat");
    void loadConversation(id);
    setMobileSidebarOpen(false);
  }, [loadConversation, navigate]);

  const handleNavigate = useCallback((path: string) => {
    navigate(path);
    setMobileSidebarOpen(false);
  }, [navigate]);

  const pageProps = {
    onAuth: () => { dispatch({ type: "SET_ERROR", payload: null }); setAuthOpen(true); },
    onCreateAgent: () => setCreateAgentOpen(true),
    onSelectAgent: () => setSelectAgentOpen(true),
    onModelConfig: () => setModelConfigOpen(true),
  };

  if (appInitializing) {
    return (
      <main className="app-shell-loading" aria-busy="true" aria-live="polite">
        <div className="app-shell-loading-card">
          <div className="loading-logo">
            <span className="loading-logo-icon">A</span>
          </div>
          <h1>AutoLearning</h1>
          <p className="loading-subtitle">AI 自适应学习平台</p>
          <div className="loading-steps">
            <div className="loading-step active">
              <span className="loading-step-dot" />
              <span>验证身份</span>
            </div>
            <div className="loading-step active">
              <span className="loading-step-dot" />
              <span>加载画像</span>
            </div>
            <div className="loading-step active">
              <span className="loading-step-dot" />
              <span>同步数据</span>
            </div>
          </div>
          <Spinner />
        </div>
      </main>
    );
  }

  return (
    <main className="learning-shell dark-layout">
      <button
        className="sidebar-mobile-toggle"
        type="button"
        onClick={() => setMobileSidebarOpen(!mobileSidebarOpen)}
        aria-label="Toggle sidebar"
      >
        {mobileSidebarOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      <div
        className={`sidebar-mobile-overlay ${mobileSidebarOpen ? "open" : ""}`}
        onClick={() => setMobileSidebarOpen(false)}
      />

      <Sidebar
        onAuth={() => { dispatch({ type: "SET_ERROR", payload: null }); setAuthOpen(true); }}
        onNewSession={handleNewSession}
        onLoadHistory={handleLoadHistory}
        onLoadConversation={(id, type) => handleLoadConversation(id, type)}
        onNavigate={handleNavigate}
        onSendMessage={(msg) => {
          if (location.pathname === "/chat") {
            dispatch({ type: "SET_PENDING_MESSAGE", payload: msg });
          } else {
            navigate("/chat");
            setTimeout(() => dispatch({ type: "SET_PENDING_MESSAGE", payload: msg }), 300);
          }
        }}
        activePath={location.pathname}
        mobileOpen={mobileSidebarOpen}
      />

      <section className="learning-main">
        <ErrorBoundary>
          <Suspense
            fallback={
              <div className="route-fallback" aria-live="polite">
                <Spinner />
                <p>页面加载中...</p>
              </div>
            }
          >
            <Routes>
              <Route path="/" element={<HomePage onAuth={() => { dispatch({ type: "SET_ERROR", payload: null }); setAuthOpen(true); }} />} />
              <Route path="/chat" element={<LearningPage {...pageProps} />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/map" element={<LearningMapPage />} />
              <Route path="/practice" element={<PracticePage />} />
              <Route path="/graphs" element={<GraphManagerPage />} />
              <Route path="/resources" element={<ResourceLibraryPage />} />
              <Route path="/tutor" element={<Navigate to="/chat" replace />} />
              <Route path="/video-studio" element={<VideoStudioPage />} />
              <Route path="/courses" element={<CoursePage />} />
              <Route path="/profile-edit" element={<Navigate to="/dashboard" replace />} />
              <Route path="/media-studio" element={<MediaStudioPage />} />
              <Route path="/learning-path" element={<Navigate to="/map" replace />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </section>

      <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} onSubmit={handleAuthSubmit} error={state.error} />

      <CreateAgentModal
        open={createAgentOpen}
        onClose={() => setCreateAgentOpen(false)}
        onSubmit={handleCreateAgent}
      />

      <SelectAgentModal
        open={selectAgentOpen}
        onClose={() => setSelectAgentOpen(false)}
        agents={state.baseAgents}
        selectedId={state.selectedBaseAgentId}
        onSelect={(id) => {
          dispatch({ type: "SET_SELECTED_AGENT", payload: id });
          setSelectAgentOpen(false);
        }}
      />

      <ModelConfigModal open={modelConfigOpen} onClose={() => setModelConfigOpen(false)} />

      {/* Global toast notification */}
      {state.notice && (
        <div
          className="global-toast"
          onClick={() => dispatch({ type: "SET_NOTICE", payload: null })}
          role="alert"
        >
          {state.notice}
        </div>
      )}
      {state.error && !authOpen && (
        <div
          className="global-toast error"
          onClick={() => dispatch({ type: "SET_ERROR", payload: null })}
          role="alert"
        >
          {state.error}
        </div>
      )}
    </main>
  );
}

export default App;
