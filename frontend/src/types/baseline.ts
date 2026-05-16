export type ResourceType =
  | "document"
  | "mindmap"
  | "quiz"
  | "reading"
  | "video"
  | "animation"
  | "code_case"
  | "flowchart";

export type AgentName =
  | "profile_agent"
  | "path_agent"
  | "document_agent"
  | "quiz_agent"
  | "mindmap_agent"
  | "video_agent"
  | "code_agent"
  | "quality_agent"
  | "recommendation_agent"
  | "tutor_agent";

export interface BaseAgentProfile {
  agent_id: string;
  user_id: string;
  name: string;
  description: string;
  system_prompt: string;
  applies_to: AgentName[];
  model_provider: string;
  output_style: string;
  is_system: boolean;
  created_at: string;
  updated_at: string;
}

export type AgentTaskStatus =
  | "pending"
  | "running"
  | "success"
  | "failed"
  | "retrying"
  | "cancelled"
  | "timeout";

export interface UserDTO {
  id: string;
  username: string;
  role: "student" | "teacher" | "admin";
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest extends LoginRequest {
  real_name?: string;
  email?: string;
  phone?: string;
  major?: string;
  grade?: string;
  school?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserDTO;
}

export interface StudentProfile {
  profile_id: string;
  user_id: string;
  version: number;
  completeness_score: number;
  confidence_score: number;
  basic_info: {
    major: string;
    grade: string;
    school?: string;
  };
  knowledge_profile: {
    overall_level: string;
    known_topics: string[];
    weak_topics: string[];
    mastery_level: Record<string, number>;
    topic_dimensions?: Record<string, { mastery: string; application: string; memory: string; understanding: string }>;
  };
  learning_goal: {
    current_goal: string;
    target_course: string;
    target_level: string;
    deadline?: string;
  };
  learning_preference: {
    learning_style: string;
    resource_preference: Partial<Record<ResourceType, number>>;
    difficulty_preference: string;
  };
  learning_behavior: {
    average_study_minutes: number;
    active_period: string;
    completion_rate: number;
    recent_scores: number[];
    last_knowledge_point?: string;
  };
  cognitive_profile: {
    cognitive_style: string;
    abstract_understanding: string;
    hands_on_ability: string;
    reading_patience: string;
  };
  dynamic_update: {
    last_updated_at: string;
    update_source: string;
    update_reason: string;
  };
}

export interface AgentTask {
  task_id: string;
  workflow_id: string;
  agent_name: AgentName;
  task_type: string;
  status: AgentTaskStatus;
  progress: number;
  input_payload?: Record<string, unknown>;
  output_payload: Record<string, unknown>;
  error_message?: string | null;
  retry_count?: number;
  duration_ms?: number | null;
}

export interface AgentEvent {
  event_id: string;
  workflow_id: string;
  task_id?: string | null;
  from_agent?: AgentName | null;
  to_agent?: AgentName | null;
  action: string;
  status: AgentTaskStatus;
  progress: number;
  input_snapshot: Record<string, unknown>;
  output_snapshot: Record<string, unknown>;
  duration_ms?: number | null;
  created_at: string;
}

export interface AgentWorkflow {
  workflow_id: string;
  user_id: string;
  status: AgentTaskStatus;
  current_agent?: AgentName | null;
  tasks: AgentTask[];
  events: AgentEvent[];
  logs: Record<string, unknown>[];
}

export interface LearningPathNode {
  node_id: string;
  order: number;
  knowledge_point: string;
  estimated_minutes: number;
  recommended_resource_types: ResourceType[];
  reason: string;
  status: "locked" | "available" | "learning" | "completed" | "skipped";
}

export interface LearningPath {
  path_id: string;
  user_id: string;
  title: string;
  goal: string;
  nodes: LearningPathNode[];
  status: string;
  strategy?: Record<string, unknown>;
}

export interface LearningResource {
  resource_id: string;
  user_id: string;
  knowledge_point: string;
  resource_type: ResourceType;
  title: string;
  difficulty: string;
  content: string;
  recommendation_reason: string;
  generated_by: string;
  quality_score: number;
  status: string;
  conversation_id?: string;
  metadata?: Record<string, unknown>;
}

export interface ResourceGenerateResponse {
  workflow_id: string;
  task_id: string;
  status: string;
  resources: LearningResource[];
}

export interface LearningStartResponse {
  task_id: string;
  workflow_id: string;
  conversation_id: string;
  status: string;
  stream_url: string;
  profile: StudentProfile;
  path: LearningPath;
  resources: LearningResource[];
  workflow: AgentWorkflow;
  recommendations: Recommendation[];
  messages: ConversationMessage[];
}

export interface BaseAgentCreateRequest {
  user_id: string;
  name: string;
  description: string;
  system_prompt: string;
  applies_to: AgentName[];
  model_provider: string;
  output_style: string;
}

export interface ConversationMessage {
  id: string;
  conversation_id: string;
  user_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  intent: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface AsyncResourceGenerateResponse {
  celery_task_id: string;
  status: string;
  message: string;
}

export interface AsyncTaskStatusResponse {
  celery_task_id: string;
  status: string;
  result?: Record<string, unknown> | null;
}

export interface Recommendation {
  recommendation_id: string;
  user_id: string;
  resource_id: string;
  title: string;
  score: number;
  recommend_reason: Record<string, unknown>;
}

export interface ResourceRecommendResponse {
  recommended_types: string[];
  existing_types: string[];
  reason: string;
  dimension_summary: Record<string, unknown>;
}

export interface LearningRecordResponse {
  record_id: string;
  profile_update_triggered: boolean;
  updated_weak_points: string[];
}

export interface RuntimeStatus {
  repository_backend: string;
  rag_backend: string;
  vector_store: string;
  object_storage: string;
  model: {
    provider: string;
    spark_ready?: boolean;
    spark_model?: string;
    websocket_ready?: boolean;
    mode: string;
    api_base?: string;
    model?: string;
    api_key_configured?: boolean;
    presets?: Record<string, { label: string; api_base: string; model: string }>;
  };
  knowledge?: {
    configured_backend: string;
    active_engine: string;
    source_chunks: number;
    indexed_chunks: number;
    subjects: string[];
    embedding?: {
      provider: string;
      model: string;
      api_configured: boolean;
      fallback: string;
      active_mode: string;
      dimension?: number | null;
      allow_fallback?: boolean;
      last_error?: string | null;
      timeout_seconds?: number;
    };
  };
}

export interface ConversationSession {
  conversation_id: string;
  user_id: string;
  title: string;
  conversation_type?: string;
  profile_id?: string | null;
  messages: ConversationMessage[];
  created_at: string;
  updated_at: string;
}
