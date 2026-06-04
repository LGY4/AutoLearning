import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { TrackedResourceRenderer } from "../resource/ResourceRenderer";
import { PracticePanel, LearningMapPanel, DashboardPanel, ResourceBrowsePanel, VideoPanel, MediaPanel, CourseGoalPanel, AnalyticsPanel } from "./inline/InlinePanels";
import { WelcomePanel } from "./inline/WelcomePanel";
import { ProfilePanel } from "../profile/ProfilePanel";
import { RecommendationPanel } from "../recommendation/RecommendationPanel";
import { AgentTrace } from "../agent/AgentTrace";
import { InlineQuiz } from "./InlineQuiz";
import { PostQuizPanel } from "./PostQuizPanel";
import type {
  AgentWorkflow,
  LearningPath,
  LearningResource,
  Recommendation,
  ResourceRecommendResponse,
  StudentProfile,
} from "../../types/baseline";

export interface IntentResult {
  intent: string;
  confidence: number;
  method: string;
  result: Record<string, unknown>;
  conversation_id?: string;
}

export interface TraceEntry {
  node: string;
  hint: string;
  status: string;
  duration_ms: number;
  timestamp: number;
}

export interface PendingRecommendation {
  knowledgePoint: string;
  response: ResourceRecommendResponse;
  onConfirm: (selectedTypes: string[]) => void;
  onCancel: () => void;
}

export interface ChatMsg {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  images?: string[];
  profile?: StudentProfile;
  path?: LearningPath;
  resources?: LearningResource[];
  recommendations?: Recommendation[];
  workflow?: AgentWorkflow;
  intentResult?: IntentResult;
  trace?: TraceEntry[];
  agentCards?: Array<{ agent_name: string; hint: string }>;
  currentAgent?: string;
  pendingRecommendation?: PendingRecommendation;
  postQuiz?: {
    question: Record<string, unknown>;
    quizSession: Record<string, unknown>;
    knowledgePoint: string;
    conversationId: string | null;
    onComplete?: () => void;
  };
  onQuizComplete?: (result: IntentResult) => void;
  onAction?: (action: string, payload?: string) => void;
}

interface Props {
  message: ChatMsg;
}

const RESOURCE_ICONS: Record<string, string> = {
  document: "📄", mindmap: "🧠", quiz: "📝", code_case: "💻",
  video: "🎬", animation: "🎞️", reading: "📖", flowchart: "🔷",
};

const INTENT_LABELS: Record<string, string> = {
  tutoring: "问答辅导",
  exercise: "练习生成",
  learning_path: "路径规划",
  resource_generation: "资源生成",
  assessment: "学习评估",
  general_chat: "闲聊",
  practice: "练习刷题",
  learning_map: "学习地图",
  video_generation: "知识视频",
  media_generation: "动画图片",
  dashboard: "学习看板",
  resource_browse: "资源浏览",
  course_goal: "课程目标",
  analytics: "学习分析",
  welcome: "今日学习",
};

function IntentBadge({ intent, confidence }: { intent: string; confidence: number }) {
  return (
    <div className="chat-intent-badge">
      <span className="chat-intent-label">{INTENT_LABELS[intent] || intent}</span>
      <span className="chat-intent-conf">{Math.round(confidence * 100)}%</span>
    </div>
  );
}

function IntentResultView({ intentResult, onQuizComplete, onAction }: { intentResult: IntentResult; onQuizComplete?: (result: IntentResult) => void; onAction?: (action: string, payload?: string) => void }) {
  const { intent, confidence, result } = intentResult;

  if (intent === "tutoring" && result.quiz_pending) {
    const q = result.question as { id: number; topic: string; difficulty: number; dimension_test: string; question: string; options: string[]; answer: string; explanation: string };
    const kp = result.knowledge_point as string;
    const origQ = (result.original_question as string) || "";
    const convId = (result.conversation_id as string) || null;
    const isKnown = (result.is_known_kp as boolean) || false;
    const isPostTest = (result.is_post_test as boolean) || false;
    const session = result.quiz_session as {
      knowledge_point: string;
      original_question: string;
      is_known_kp: boolean;
      questions: Array<{ id: number; topic: string; difficulty: number; dimension_test: string; question: string; options: string[]; answer: string; explanation: string }>;
      answers: Record<number, string>;
      correct_count: number;
      wrong_count: number;
      status: string;
    };
    return (
      <>
        <IntentBadge intent={intent} confidence={confidence} />
        <InlineQuiz
          question={q}
          quizSession={session}
          knowledgePoint={kp}
          originalQuestion={origQ}
          conversationId={convId}
          isKnownKp={isKnown}
          isPostTest={isPostTest}
          onComplete={(answerResult) => onQuizComplete?.(answerResult)}
        />
      </>
    );
  }

  if (intent === "tutoring") {
    const answer = (result.answer as string) || "";
    const markdown = (result.markdown as string) || answer;
    const refs = (result.rag_references as Array<{ title?: string; source?: string }>) || [];
    const nextStep = result.next_step as string | undefined;
    const rec = result.resource_recommendation as { knowledge_point?: string; recommended_types?: string[]; reason?: string; decision?: string } | undefined;
    const showRec = rec && rec.recommended_types && rec.recommended_types.length > 0 && rec.decision !== "silent";
    return (
      <>
        <IntentBadge intent={intent} confidence={confidence} />
        <div className="chat-content chat-tutor-answer">
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>{markdown}</ReactMarkdown>
        </div>
        {refs.length > 0 && (
          <div className="chat-refs">
            {refs.map((r, i) => (
              <span key={i} className="chat-ref-tag">{r.title || r.source || `参考${i + 1}`}</span>
            ))}
          </div>
        )}
        {nextStep && <div className="chat-next-step">建议：{nextStep}</div>}
        {showRec && (
          <div className={`chat-resource-recommend ${rec.decision === "ask" ? "ask-mode" : ""}`}>
            {rec.reason && <div className="chat-resource-recommend-reason">{rec.reason}</div>}
            <div className="chat-resource-recommend-types">
              {rec.recommended_types!.map((t, i) => (
                <button
                  key={i}
                  type="button"
                  className="chat-resource-recommend-tag"
                  onClick={() => onAction?.("generate_resource", `${rec.knowledge_point || ""}|${t}`)}
                >
                  {t}
                </button>
              ))}
            </div>
            {rec.decision === "auto" && (
              <button
                type="button"
                className="chat-resource-recommend-gen"
                onClick={() => onAction?.("generate_resource", `${rec.knowledge_point || ""}|${rec.recommended_types!.join(",")}`)}
              >
                一键生成
              </button>
            )}
          </div>
        )}
        {result.knowledge_point && (
          <button
            type="button"
            className="chat-post-test-btn"
            onClick={() => onAction?.("post_test", result.knowledge_point as string)}
          >
            检验学习效果
          </button>
        )}
      </>
    );
  }

  if (intent === "exercise") {
    const title = (result.title as string) || "练习题";
    const content = (result.content as string) || "";
    return (
      <>
        <IntentBadge intent={intent} confidence={confidence} />
        <div className="chat-content"><strong>{title}</strong></div>
        <div className="chat-content chat-exercise-content">
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>{content}</ReactMarkdown>
        </div>
      </>
    );
  }

  if (intent === "assessment") {
    const mastery = result.mastery_score as number | undefined;
    const weak = (result.weak_points as string[]) || [];
    const suggestions = (result.next_suggestions as string[]) || [];
    return (
      <>
        <IntentBadge intent={intent} confidence={confidence} />
        <div className="chat-content">
          {mastery != null && <div>掌握度：<strong>{Math.round(mastery * 100)}%</strong></div>}
          {weak.length > 0 && (
            <div className="chat-assessment-weak">
              薄弱点：
              {weak.map((w, i) => (
                <span key={i}>
                  {i > 0 && "、"}
                  <a href={`/practice?knowledge_point=${encodeURIComponent(w)}`} className="chat-assessment-weak-link">{w}</a>
                </span>
              ))}
            </div>
          )}
          {suggestions.length > 0 && <div>建议：{suggestions.join("；")}</div>}
        </div>
      </>
    );
  }

  if (intent === "learning_path") {
    const title = (result.title as string) || "学习路径";
    const nodes = (result.nodes as Array<{ knowledge_point?: string; name?: string; status?: string; order?: number }>) || [];
    return (
      <>
        <IntentBadge intent={intent} confidence={confidence} />
        <div className="chat-content">
          <strong>{title}</strong>
          {nodes.length > 0 && (
            <div className="chat-path-nodes">
              {nodes.map((n, i) => (
                <div key={i} className="chat-path-node">
                  <span className="chat-path-idx">{n.order ?? i + 1}</span>
                  <span>{n.knowledge_point || n.name || `节点${i + 1}`}</span>
                  {n.status && <span className="chat-path-status">{n.status}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      </>
    );
  }

  if (intent === "resource_generation") {
    const resList = (result.resources as LearningResource[]) || [];
    const status = result.status as string | undefined;
    return (
      <>
        <IntentBadge intent={intent} confidence={confidence} />
        {resList.length > 0 ? (
          <div className="chat-resources">
            {resList.map((r, i) => (
              <details className="chat-resource-card" key={r.resource_id || `res-${i}`}>
                <summary className="chat-resource-header">
                  <span className="chat-resource-icon">{RESOURCE_ICONS[r.resource_type] ?? "📄"}</span>
                  <div className="chat-resource-info">
                    <span className="chat-resource-title">{r.title}</span>
                    <span className="chat-resource-meta">{r.resource_type} · {r.knowledge_point}</span>
                  </div>
                  <span className="chat-resource-expand">展开</span>
                </summary>
                <div className="chat-resource-body">
                  <TrackedResourceRenderer resource={r} />
                </div>
              </details>
            ))}
          </div>
        ) : (
          <div className="chat-content">
            {status === "failed" || status === "degraded"
              ? "资源生成失败，请稍后重试或直接输入知识点名称重新请求。"
              : "资源生成中，请稍候..."}
          </div>
        )}
      </>
    );
  }

  if (intent === "practice") {
    return (
      <>
        <IntentBadge intent={intent} confidence={confidence} />
        <PracticePanel result={result} />
      </>
    );
  }

  if (intent === "learning_map") {
    return (
      <>
        <IntentBadge intent={intent} confidence={confidence} />
        <LearningMapPanel result={result} />
      </>
    );
  }

  if (intent === "dashboard") {
    return (
      <>
        <IntentBadge intent={intent} confidence={confidence} />
        <DashboardPanel result={result} />
      </>
    );
  }

  if (intent === "resource_browse") {
    return (
      <>
        <IntentBadge intent={intent} confidence={confidence} />
        <ResourceBrowsePanel result={result} />
      </>
    );
  }

  if (intent === "video_generation") {
    return (
      <>
        <IntentBadge intent={intent} confidence={confidence} />
        <VideoPanel result={result} />
      </>
    );
  }

  if (intent === "media_generation") {
    return (
      <>
        <IntentBadge intent={intent} confidence={confidence} />
        <MediaPanel result={result} />
      </>
    );
  }

  if (intent === "course_goal") {
    return (
      <>
        <IntentBadge intent={intent} confidence={confidence} />
        <CourseGoalPanel result={result} />
      </>
    );
  }

  if (intent === "analytics") {
    return (
      <>
        <IntentBadge intent={intent} confidence={confidence} />
        <AnalyticsPanel result={result} />
      </>
    );
  }

  if (intent === "welcome") {
    return <WelcomePanel result={result} />;
  }

  if (intent === "general_chat") {
    return <div className="chat-content">{(result.reply as string) || ""}</div>;
  }

  // fallback
  return (
    <>
      <IntentBadge intent={intent} confidence={confidence} />
      <div className="chat-content">{(result.content as string) || (result.reply as string) || JSON.stringify(result, null, 2)}</div>
    </>
  );
}

function ResourceRecommendCard({ rec, knowledgePoint, onConfirm, onCancel }: {
  rec: ResourceRecommendResponse;
  knowledgePoint: string;
  onConfirm: (selectedTypes: string[]) => void;
  onCancel: () => void;
}) {
  const [selected, setSelected] = useState<string[]>(rec.recommended_types);

  const TYPE_LABELS: Record<string, string> = {
    document: "文档", mindmap: "思维导图", quiz: "测验", reading: "阅读",
    video: "视频", animation: "动画", code_case: "代码实操",
  };

  const toggle = (t: string) => {
    setSelected((prev) => prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]);
  };

  return (
    <div className="resource-recommend-card">
      <div className="resource-recommend-header">
        <span className="resource-recommend-title">资源推荐</span>
        <span className="resource-recommend-kp">{knowledgePoint}</span>
      </div>
      <div className="resource-recommend-reason">{rec.reason}</div>
      {rec.dimension_summary && Object.keys(rec.dimension_summary).length > 0 && (
        <div className="resource-recommend-dims">
          {Object.entries(rec.dimension_summary).map(([k, v]) => (
            <span key={k} className="resource-recommend-dim">{k}: {String(v)}</span>
          ))}
        </div>
      )}
      <div className="resource-recommend-types">
        {(["document", "mindmap", "quiz", "reading", "video", "animation", "code_case"] as string[]).map((t) => {
          const isRec = rec.recommended_types.includes(t);
          const isSel = selected.includes(t);
          const exists = rec.existing_types.includes(t);
          return (
            <button
              key={t}
              type="button"
              className={`resource-recommend-type ${isSel ? "selected" : ""} ${isRec ? "recommended" : ""} ${exists ? "existing" : ""}`}
              onClick={() => toggle(t)}
              disabled={exists}
            >
              {TYPE_LABELS[t] || t}
              {exists && <span className="resource-recommend-exists">已有</span>}
            </button>
          );
        })}
      </div>
      <div className="resource-recommend-actions">
        <button type="button" className="resource-recommend-confirm" onClick={() => onConfirm(selected)} disabled={selected.length === 0}>
          开始生成 ({selected.length})
        </button>
        <button type="button" className="resource-recommend-cancel" onClick={onCancel}>
          取消
        </button>
      </div>
    </div>
  );
}

export const ChatMessage = React.memo(function ChatMessage({ message }: Props) {
  const { role, content, streaming, images, profile, path, resources, recommendations, intentResult, trace, agentCards, currentAgent, pendingRecommendation, postQuiz, onQuizComplete, onAction } = message;

  return (
    <div className={`chat-message ${role}`}>
      <div className="chat-bubble">
        {images && images.length > 0 && (
          <div className="chat-message-images">
            {images.filter(img => /^https?:\/\//.test(img) || img.startsWith('data:image/')).map((img, i) => (
              <img key={i} src={img} alt={`upload-${i}`} className="chat-message-image" />
            ))}
          </div>
        )}

        {postQuiz ? (
          <PostQuizPanel
            question={postQuiz.question as any}
            quizSession={postQuiz.quizSession as any}
            knowledgePoint={postQuiz.knowledgePoint}
            conversationId={postQuiz.conversationId}
            onComplete={() => postQuiz.onComplete?.()}
            onGenerateResource={(kp, rt) => onAction?.("generate_resource", `${kp}|${rt}`)}
          />
        ) : pendingRecommendation ? (
          <ResourceRecommendCard
            rec={pendingRecommendation.response}
            knowledgePoint={pendingRecommendation.knowledgePoint}
            onConfirm={pendingRecommendation.onConfirm}
            onCancel={pendingRecommendation.onCancel}
          />
        ) : intentResult ? (
          <IntentResultView intentResult={intentResult} onQuizComplete={onQuizComplete} onAction={onAction} />
        ) : (
          <div className="chat-content">
            {streaming && !content && !agentCards?.length && !currentAgent ? "正在思考..." : null}
            {content ? <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>{content}</ReactMarkdown> : null}
          </div>
        )}

        {agentCards && agentCards.length > 0 && (
          <div className="agent-result-cards">
            {agentCards.map((card, i) => (
              <div className="agent-result-card" key={i}>
                <span className="agent-result-check">&#10003;</span>
                <span className="agent-result-hint">{card.hint}</span>
              </div>
            ))}
          </div>
        )}

        {currentAgent && streaming && (
          <div className="agent-current-status">
            <span className="agent-current-spinner" />
            <span>{currentAgent}</span>
          </div>
        )}

        {profile && (
          <div className="chat-inline-panel">
            <ProfilePanel profile={profile} />
          </div>
        )}

        {path && path.nodes.length > 0 && (
          <div className="chat-inline-panel">
            <div className="chat-path-summary">
              <strong>{path.title || "学习路径"}</strong>
              <span>{path.nodes.length} 个节点</span>
            </div>
          </div>
        )}

        {resources && resources.length > 0 && (
          <div className="chat-resources">
            {resources.map((r) => (
              <details className="chat-resource-card" key={r.resource_id}>
                <summary className="chat-resource-header">
                  <span className="chat-resource-icon">{RESOURCE_ICONS[r.resource_type] ?? "📄"}</span>
                  <div className="chat-resource-info">
                    <span className="chat-resource-title">{r.title}</span>
                    <span className="chat-resource-meta">{r.resource_type} · {r.knowledge_point}</span>
                  </div>
                  <span className="chat-resource-expand">展开</span>
                </summary>
                <div className="chat-resource-body">
                  <TrackedResourceRenderer resource={r} />
                </div>
              </details>
            ))}
          </div>
        )}

        {recommendations && recommendations.length > 0 && (
          <div className="chat-inline-panel">
            <RecommendationPanel recommendations={recommendations} />
          </div>
        )}

        {trace && trace.length > 0 && <AgentTrace trace={trace} />}

        {streaming && (
          <div className="chat-streaming-dots">
            <span /><span /><span />
          </div>
        )}
      </div>
    </div>
  );
});