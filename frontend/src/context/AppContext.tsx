import { createContext, useContext, useMemo, useReducer, type ReactNode } from "react";
import type {
  AgentWorkflow,
  BaseAgentProfile,
  ConversationSession,
  LearningPath,
  LearningResource,
  Recommendation,
  StudentProfile,
  UserDTO,
} from "../types/baseline";

export interface AppState {
  user: UserDTO | null;
  profile: StudentProfile;
  profileLoaded: boolean;
  learningPath: LearningPath;
  resources: LearningResource[];
  recommendations: Recommendation[];
  conversations: ConversationSession[];
  baseAgents: BaseAgentProfile[];
  selectedBaseAgentId: string | null;
  selectedConversationId: string | null;
  activeMessages: ConversationSession["messages"];
  workflow: AgentWorkflow | null;
  loading: boolean;
  error: string | null;
  notice: string | null;
  pathVersion: number;
  pendingMessage: string | null;
}

type Action =
  | { type: "SET_USER"; payload: UserDTO | null }
  | { type: "SET_PROFILE"; payload: StudentProfile }
  | { type: "SET_PATH"; payload: LearningPath }
  | { type: "SET_RESOURCES"; payload: LearningResource[] }
  | { type: "SET_RECOMMENDATIONS"; payload: Recommendation[] }
  | { type: "SET_CONVERSATIONS"; payload: ConversationSession[] }
  | { type: "ADD_CONVERSATION"; payload: ConversationSession }
  | { type: "SET_AGENTS"; payload: BaseAgentProfile[] }
  | { type: "SET_SELECTED_AGENT"; payload: string | null }
  | { type: "SET_SELECTED_CONVERSATION"; payload: string | null }
  | { type: "SET_ACTIVE_MESSAGES"; payload: ConversationSession["messages"] }
  | { type: "SET_WORKFLOW"; payload: AgentWorkflow | null }
  | { type: "SET_LOADING"; payload: boolean }
  | { type: "SET_ERROR"; payload: string | null }
  | { type: "SET_NOTICE"; payload: string | null }
  | { type: "MARK_PROFILE_LOADED" }
  | { type: "BUMP_PATH_VERSION" }
  | { type: "SET_PENDING_MESSAGE"; payload: string | null }
  | { type: "LOGOUT" };

const EMPTY_PROFILE: StudentProfile = {
  profile_id: "00000000-0000-0000-0000-000000000000",
  user_id: "00000000-0000-0000-0000-000000000000",
  version: 1,
  completeness_score: 0,
  confidence_score: 0,
  basic_info: { major: "", grade: "", school: "" },
  knowledge_profile: { overall_level: "unknown", known_topics: [], weak_topics: [], mastery_level: {}, topic_dimensions: {} },
  learning_goal: { current_goal: "", target_course: "", target_level: "project_practice", deadline: "" },
  learning_preference: { learning_style: "mixed", resource_preference: {}, difficulty_preference: "step_by_step" },
  learning_behavior: {
    average_study_minutes: 45,
    active_period: "evening",
    completion_rate: 0,
    recent_scores: [],
    last_knowledge_point: "",
  },
  cognitive_profile: {
    cognitive_style: "mixed",
    abstract_understanding: "medium",
    hands_on_ability: "medium",
    reading_patience: "medium",
  },
  dynamic_update: { last_updated_at: "", update_source: "init", update_reason: "" },
};

const EMPTY_PATH: LearningPath = {
  path_id: "00000000-0000-0000-0000-000000000000",
  user_id: "00000000-0000-0000-0000-000000000000",
  title: "",
  goal: "",
  nodes: [],
  status: "active",
};

const initialState: AppState = {
  user: null,
  profile: EMPTY_PROFILE,
  profileLoaded: false,
  learningPath: EMPTY_PATH,
  resources: [],
  recommendations: [],
  conversations: [],
  baseAgents: [],
  selectedBaseAgentId: null,
  selectedConversationId: null,
  activeMessages: [],
  workflow: null,
  loading: false,
  error: null,
  notice: "请登录后开始学习。",
  pathVersion: 0,
  pendingMessage: null,
};

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "SET_USER":
      return { ...state, user: action.payload };
    case "SET_PROFILE":
      return { ...state, profile: action.payload };
    case "SET_PATH":
      return { ...state, learningPath: action.payload };
    case "SET_RESOURCES":
      return { ...state, resources: action.payload };
    case "SET_RECOMMENDATIONS":
      return { ...state, recommendations: action.payload };
    case "SET_CONVERSATIONS":
      return { ...state, conversations: action.payload };
    case "ADD_CONVERSATION":
      return { ...state, conversations: [action.payload, ...state.conversations.filter(c => c.conversation_id !== action.payload.conversation_id)] };
    case "SET_AGENTS":
      return { ...state, baseAgents: action.payload };
    case "SET_SELECTED_AGENT":
      return { ...state, selectedBaseAgentId: action.payload };
    case "SET_SELECTED_CONVERSATION":
      return { ...state, selectedConversationId: action.payload };
    case "SET_ACTIVE_MESSAGES":
      return { ...state, activeMessages: action.payload };
    case "SET_WORKFLOW":
      return { ...state, workflow: action.payload };
    case "SET_LOADING":
      return { ...state, loading: action.payload };
    case "SET_ERROR":
      return { ...state, error: action.payload };
    case "SET_NOTICE":
      return { ...state, notice: action.payload };
    case "MARK_PROFILE_LOADED":
      return { ...state, profileLoaded: true };
    case "BUMP_PATH_VERSION":
      return { ...state, pathVersion: state.pathVersion + 1 };
    case "SET_PENDING_MESSAGE":
      return { ...state, pendingMessage: action.payload };
    case "LOGOUT":
      return { ...initialState, notice: "请登录后开始学习。" };
    default:
      return state;
  }
}

interface AppContextValue {
  state: AppState;
  dispatch: React.Dispatch<Action>;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const value = useMemo(() => ({ state, dispatch }), [state, dispatch]);
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useAppContext() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useAppContext must be used within AppProvider");
  return ctx;
}

export { EMPTY_PROFILE, EMPTY_PATH };
export type { ConversationSession };
