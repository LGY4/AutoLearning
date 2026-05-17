import { lazy, Suspense, useEffect, useState } from "react";
import { Routes, Route, useNavigate, useLocation } from "react-router-dom";
import { Menu, X } from "lucide-react";
import { useAppContext, EMPTY_PROFILE, EMPTY_PATH } from "./context/AppContext";
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
const TutorPage = lazy(() => import("./pages/TutorPage").then((m) => ({ default: m.TutorPage })));
const VideoStudioPage = lazy(() => import("./pages/VideoStudioPage").then((m) => ({ default: m.VideoStudioPage })));
const CoursePage = lazy(() => import("./pages/CoursePage").then((m) => ({ default: m.CoursePage })));
const ProfileEditPage = lazy(() => import("./pages/ProfileEditPage").then((m) => ({ default: m.ProfileEditPage })));
const MediaStudioPage = lazy(() => import("./pages/MediaStudioPage").then((m) => ({ default: m.MediaStudioPage })));
const LearningPathPage = lazy(() => import("./pages/LearningPathPage").then((m) => ({ default: m.LearningPathPage })));

function App() {
  const { state, dispatch } = useAppContext();
  const { login, register, logout, initAuth, loadUserBundle } = useAuth();
  const { loadConversation } = useLearning();
  const navigate = useNavigate();
  const location = useLocation();
  const [authOpen, setAuthOpen] = useState(false);
  const [createAgentOpen, setCreateAgentOpen] = useState(false);
  const [selectAgentOpen, setSelectAgentOpen] = useState(false);
  const [modelConfigOpen, setModelConfigOpen] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  useEffect(() => {
    initAuth().then((ok) => {
      if (!ok) setAuthOpen(true);
    });
  }, []);

  // Redirect to home if profile is incomplete (force diagnostic)
  const ALLOWED_INCOMPLETE = ["/", "/profile-edit"];
  useEffect(() => {
    if (state.user && state.profile.completeness_score <= 0.5 && !ALLOWED_INCOMPLETE.includes(location.pathname)) {
      navigate("/", { replace: true });
    }
  }, [state.user, state.profile.completeness_score, location.pathname]);

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

  const pageProps = {
    onAuth: () => setAuthOpen(true),
    onCreateAgent: () => setCreateAgentOpen(true),
    onSelectAgent: () => setSelectAgentOpen(true),
    onModelConfig: () => setModelConfigOpen(true),
  };

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
        onAuth={() => setAuthOpen(true)}
        onNewSession={() => {
          navigate("/chat");
          dispatch({ type: "SET_SELECTED_CONVERSATION", payload: null });
          dispatch({ type: "SET_ACTIVE_MESSAGES", payload: [] });
          dispatch({ type: "SET_PROFILE", payload: EMPTY_PROFILE });
          dispatch({ type: "SET_PATH", payload: EMPTY_PATH });
          dispatch({ type: "SET_RESOURCES", payload: [] });
          dispatch({ type: "SET_RECOMMENDATIONS", payload: [] });
          dispatch({ type: "SET_WORKFLOW", payload: null });
          dispatch({ type: "SET_ERROR", payload: null });
          setMobileSidebarOpen(false);
        }}
        onLoadHistory={() => loadUserBundle()}
        onLoadConversation={(id, _conversationType) => {
          navigate("/chat");
          loadConversation(id);
          setMobileSidebarOpen(false);
        }}
        onNavigate={(path) => { navigate(path); setMobileSidebarOpen(false); }}
        activePath={location.pathname}
        mobileOpen={mobileSidebarOpen}
      />

      <section className="learning-main">
        <ErrorBoundary>
          <Suspense fallback={<div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100%" }}><Spinner /></div>}>
            <Routes>
              <Route path="/" element={<HomePage onAuth={() => setAuthOpen(true)} />} />
              <Route path="/chat" element={<LearningPage {...pageProps} />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/map" element={<LearningMapPage />} />
              <Route path="/practice" element={<PracticePage />} />
              <Route path="/graphs" element={<GraphManagerPage />} />
              <Route path="/resources" element={<ResourceLibraryPage />} />
              <Route path="/tutor" element={<TutorPage />} />
              <Route path="/video-studio" element={<VideoStudioPage />} />
              <Route path="/courses" element={<CoursePage />} />
              <Route path="/profile-edit" element={<ProfileEditPage />} />
              <Route path="/media-studio" element={<MediaStudioPage />} />
              <Route path="/learning-path" element={<LearningPathPage />} />
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
    </main>
  );
}

export default App;
