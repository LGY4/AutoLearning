import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Search, X } from "lucide-react";
import { Virtuoso } from "react-virtuoso";
import { useAppContext } from "../../context/AppContext";
import { apiGet, apiPatch, apiPost, apiPostStream, getFriendlyError } from "../../api/client";

/** Safely cast API response data to a typed shape */
function asType<T>(data: unknown): T {
  return data as T;
}
import { useRecordLearning } from "../../hooks/useRecordLearning";
import { ChatMessage, type ChatMsg, type IntentResult, type TraceEntry } from "./ChatMessage";
import { ErrorBoundary } from "../common/ErrorBoundary";
import { ChatInput } from "./ChatInput";
import { PostQuizPanel } from "./PostQuizPanel";
import { PlusMenu } from "../plus-menu/PlusMenu";
import { PipelineBar } from "../pipeline/PipelineBar";
import type {
  AgentWorkflow,
  LearningPath,
  LearningResource,
  Recommendation,
  ResourceType,
  StudentProfile,
} from "../../types/baseline";

type ChatMode = "intent" | "pipeline";

function generateTitle(content: string): string {
  const clean = content.replace(/[#*`\n\r]+/g, " ").trim();
  return clean.length > 10 ? clean.slice(0, 10) + "…" : clean || "新对话";
}

interface Props {
  onAuth: () => void;
  onCreateAgent: () => void;
  onSelectAgent: () => void;
  onModelConfig?: () => void;
}

export function ChatPanel({ onAuth, onCreateAgent, onSelectAgent, onModelConfig }: Props) {
  const { state, dispatch } = useAppContext();
  const { user, baseAgents, selectedBaseAgentId, loading } = state;

  const [searchParams] = useSearchParams();
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState(() => searchParams.get("topic") || "");
  const [mode, setMode] = useState<ChatMode>("intent");

  // RAG knowledge search
  const [ragPanelOpen, setRagPanelOpen] = useState(false);
  const [ragQuery, setRagQuery] = useState("");
  const [ragResults, setRagResults] = useState<Array<{ chunk_id: string; title: string; content: string; subject: string; score: number }> | null>(null);
  const [ragLoading, setRagLoading] = useState(false);
  const [ragContext, setRagContext] = useState<Array<{ chunk_id: string; title: string; content: string; subject: string }>>([]);
  const ragContextRef = useRef(ragContext);
  ragContextRef.current = ragContext;
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const loadingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const titleGeneratedRef = useRef(false);
  const resourcesRef = useRef(state.resources);
  resourcesRef.current = state.resources;
  const conversationsRef = useRef(state.conversations);
  conversationsRef.current = state.conversations;
  const convIdRef = useRef(state.selectedConversationId);
  convIdRef.current = state.selectedConversationId;
  const profileRef = useRef(state.profile);
  profileRef.current = state.profile;
  const prevConvIdRef = useRef<string | null>(null);

  const selectedAgent = baseAgents.find((a) => a.agent_id === selectedBaseAgentId) ?? null;
  const recordLearning = useRecordLearning();
  const workspaceStats = [
    { label: "当前画像", value: state.profile.knowledge_profile.overall_level || "待评估" },
    { label: "学习路径", value: state.learningPath.nodes.length > 0 ? `${state.learningPath.nodes.length} 步` : "待生成" },
    { label: "资源数量", value: state.resources.length > 0 ? `${state.resources.length} 项` : "待生成" },
    { label: "推荐内容", value: state.recommendations.length > 0 ? `${state.recommendations.length} 条` : "待生成" }
  ];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Load messages from global state when switching conversations
  useEffect(() => {
    if (state.activeMessages.length > 0) {
      const converted: ChatMsg[] = state.activeMessages.map((msg) => {
        const chatMsg: ChatMsg = {
          id: msg.id,
          role: msg.role as ChatMsg["role"],
          content: msg.content,
          streaming: false,
        };
        // Reconstruct intentResult from persisted metadata
        const ir = msg.metadata?.intent_result as Record<string, unknown> | undefined;
        if (ir && typeof ir === "object") {
          chatMsg.intentResult = {
            intent: String(ir.intent || msg.intent || "tutoring"),
            confidence: Number(ir.confidence ?? 1),
            method: String(ir.method || "loaded"),
            result: (ir.result || {}) as Record<string, unknown>,
          };
        }
        return chatMsg;
      });
      setMessages(converted);
    } else {
      setMessages([]);
    }
  }, [state.activeMessages]);

  // Consume pending message from sidebar navigation
  useEffect(() => {
    if (state.pendingMessage) {
      const msg = state.pendingMessage;
      dispatch({ type: "SET_PENDING_MESSAGE", payload: null });
      setInput(msg);
      setTimeout(() => sendIntentMessage(msg), 50);
    }
  }, [state.pendingMessage, dispatch, sendIntentMessage]);

  // Listen for quick action messages from WelcomePanel
  useEffect(() => {
    const handler = (e: Event) => {
      const msg = (e as CustomEvent).detail;
      if (msg) {
        setInput(msg);
        setTimeout(() => sendIntentMessage(msg), 50);
      }
    };
    window.addEventListener("chat-send-message", handler);
    return () => window.removeEventListener("chat-send-message", handler);
  }, [sendIntentMessage]);

  // Auto-send welcome on new empty conversation
  useEffect(() => {
    if (messages.length === 0 && user && !state.selectedConversationId) {
      apiGet<Record<string, unknown>>("/learning/welcome").then((welcomeData) => {
        if (welcomeData) {
          const welcomeMsg: ChatMsg = {
            id: crypto.randomUUID(),
            role: "assistant",
            content: "",
            streaming: false,
            intentResult: { intent: "welcome", confidence: 1.0, method: "auto", result: welcomeData },
          };
          setMessages([welcomeMsg]);
        }
      }).catch(() => {});
    }
  }, [user]); // only on mount / user change

  useEffect(() => {
    titleGeneratedRef.current = false;
    abortRef.current?.abort();
    // End previous conversation to merge its profile back to master
    const prevId = prevConvIdRef.current;
    if (prevId && prevId !== state.selectedConversationId) {
      apiPost(`/conversations/${prevId}/end`, {}).catch(() => {});
    }
    prevConvIdRef.current = state.selectedConversationId;
  }, [state.selectedConversationId]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (prevConvIdRef.current) {
        apiPost(`/conversations/${prevConvIdRef.current}/end`, {}).catch(() => {});
      }
    };
  }, []);

  const sendIntentMessage = useCallback(async (content: string) => {
    if (!user) { onAuth(); return; }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const userMsg: ChatMsg = { id: crypto.randomUUID(), role: "user", content };
    const streamMsg: ChatMsg = { id: crypto.randomUUID(), role: "assistant", content: "", streaming: true };
    setMessages((prev) => [...prev, userMsg, streamMsg]);
    dispatch({ type: "SET_LOADING", payload: true });
    // Safety timeout: force-clear loading if SSE stalls (5 min)
    if (loadingTimerRef.current) clearTimeout(loadingTimerRef.current);
    loadingTimerRef.current = setTimeout(() => {
      dispatch({ type: "SET_LOADING", payload: false });
      setMessages((prev) => prev.map((m) => (m.id === streamMsg.id && m.streaming ? { ...m, streaming: false, content: m.content || "响应超时，请重试" } : m)));
    }, 300_000);

    // Use SSE streaming for tutor answers
    let usedStreaming = false;
    let streamedContent = "";
    try {
      let resultData: Record<string, unknown> | null = null;

      let streamError: string | null = null;
      await apiPostStream("/learning/chat-stream", {
        message: content,
        conversation_id: convIdRef.current,
        base_agent_id: selectedBaseAgentId,
        rag_context: ragContextRef.current.length > 0 ? ragContextRef.current : undefined,
      }, (evt) => {
        if (evt.type === "error") {
          const errData = evt.data as Record<string, unknown>;
          const errMsg = String(errData.message || "AI 服务暂时不可用，请重试");
          const errCode = errData.error_code ? String(errData.error_code) : undefined;
          streamError = getFriendlyError(errMsg, errCode);
        } else if (evt.type === "text_delta" && typeof (evt.data as Record<string, unknown>).content === "string") {
          streamedContent += (evt.data as Record<string, unknown>).content;
          setMessages((prev) => prev.map((m) => m.id === streamMsg.id ? { ...m, content: streamedContent } : m));
        } else if (evt.type === "result") {
          resultData = evt.data as Record<string, unknown>;
        } else if (evt.type === "quiz_followup") {
          const quizData = evt.data as Record<string, unknown>;
          const quizMsgId = crypto.randomUUID();
          const quizMsg: ChatMsg = {
            id: quizMsgId,
            role: "assistant",
            content: "",
            streaming: false,
            intentResult: { intent: "tutoring", confidence: 1.0, method: "streaming", result: quizData },
            onQuizComplete: (answerResult: IntentResult) => {
              setMessages((prev) => prev.map((m) =>
                m.id === quizMsgId ? { ...m, intentResult: answerResult, onQuizComplete: undefined } : m,
              ));
              const ar = answerResult.result;
              if (ar.updated_dimension) {
                apiGet<StudentProfile>("/profiles/me")
                  .then((p) => dispatch({ type: "SET_PROFILE", payload: p }))
                  .catch(() => {});
                apiGet<Recommendation[]>("/recommendations/")
                  .then((recs) => dispatch({ type: "SET_RECOMMENDATIONS", payload: recs }))
                  .catch(() => {});
              }
            },
          };
          setMessages((prev) => [...prev, quizMsg]);
        }
      }, controller.signal);

      usedStreaming = true;
      setRagContext([]);

      if (streamError) {
        const errMsg = streamError;
        setMessages((prev) => prev.map((m) =>
          m.id === streamMsg.id ? { ...m, content: errMsg, streaming: false } : m
        ));
        dispatch({ type: "SET_LOADING", payload: false });
        return;
      }

      const res: IntentResult = resultData
        ? {
            intent: String((resultData as Record<string, unknown>).intent || "tutoring"),
            confidence: Number((resultData as Record<string, unknown>).confidence || 1.0),
            method: "streaming",
            result: (resultData as Record<string, unknown>).result as Record<string, unknown> || resultData,
          }
        : { intent: "tutoring", confidence: 1.0, method: "streaming", result: { answer: streamedContent, markdown: streamedContent, question: content } };

      const finalMsg: ChatMsg = { id: streamMsg.id, role: "assistant", content: "", streaming: false, intentResult: res };

      // Handle quiz_pending from streaming result
      if (res.intent === "tutoring" && res.result.quiz_pending) {
        finalMsg.onQuizComplete = (answerResult: IntentResult) => {
          setMessages((prev) => prev.map((m) =>
            m.id === streamMsg.id ? { ...m, intentResult: answerResult, onQuizComplete: undefined } : m,
          ));
          const ar = answerResult.result;
          if (ar.updated_dimension) {
            apiGet<StudentProfile>("/profiles/me")
              .then((p) => dispatch({ type: "SET_PROFILE", payload: p }))
              .catch(() => {});
            apiGet<Recommendation[]>("/recommendations/")
              .then((recs) => dispatch({ type: "SET_RECOMMENDATIONS", payload: recs }))
              .catch(() => {});
          }
        };
      }

      setMessages((prev) => prev.map((m) => (m.id === streamMsg.id ? finalMsg : m)));

      // Sync intent results to global state for right panels
      const r = res.result;
      if (res.intent === "resource_generation") {
        if (r.profile) dispatch({ type: "SET_PROFILE", payload: r.profile as StudentProfile });
        if (r.path) dispatch({ type: "SET_PATH", payload: r.path as LearningPath });
        if (r.resources) dispatch({ type: "SET_RESOURCES", payload: r.resources as LearningResource[] });
        if (r.recommendations) dispatch({ type: "SET_RECOMMENDATIONS", payload: r.recommendations as Recommendation[] });
        if (r.workflow) dispatch({ type: "SET_WORKFLOW", payload: r.workflow as AgentWorkflow });
        if (r.conversation_id) dispatch({ type: "SET_SELECTED_CONVERSATION", payload: String(r.conversation_id) });
      } else if (res.intent === "learning_path" && r.path_id) {
        dispatch({ type: "SET_PATH", payload: asType<LearningPath>(r) });
      } else if (res.intent === "exercise" && r.resource_id) {
        dispatch({ type: "SET_RESOURCES", payload: [...resourcesRef.current, asType<LearningResource>(r)] });
      } else if (res.intent === "tutoring") {
        // Refresh recommendations after tutor answer (backend invalidates cache)
        apiGet<Recommendation[]>("/recommendations/")
          .then((recs) => dispatch({ type: "SET_RECOMMENDATIONS", payload: recs }))
          .catch(() => {});
      }

      // Add new conversation to sidebar in real-time
      const newConvId = res.conversation_id || (typeof r.conversation_id === "string" ? r.conversation_id : null);
      if (newConvId && !conversationsRef.current.some((c) => c.conversation_id === newConvId)) {
        dispatch({ type: "SET_SELECTED_CONVERSATION", payload: newConvId });
        convIdRef.current = newConvId;
        dispatch({
          type: "ADD_CONVERSATION",
          payload: {
            conversation_id: newConvId,
            user_id: user!.id,
            title: "新对话",
            messages: [],
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        });
      }

      // React to backend auto-generation changes
      const changes = r.changes as Record<string, unknown> | undefined;
      if (changes?.path_generated) {
        dispatch({ type: "SET_NOTICE", payload: "学习路径已自动生成，可在学习地图中查看" });
        dispatch({ type: "BUMP_PATH_VERSION" });
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        if (loadingTimerRef.current) { clearTimeout(loadingTimerRef.current); loadingTimerRef.current = null; }
        dispatch({ type: "SET_LOADING", payload: false });
        setMessages((prev) =>
          prev.map((m) =>
            m.id === streamMsg.id
              ? { ...m, content: m.content || "已停止", streaming: false }
              : m
          )
        );
        return;
      }
      // Fall through to sync endpoint
    }

    if (usedStreaming) {
      // Auto-generate conversation title from streamed content
      if (!titleGeneratedRef.current && convIdRef.current && streamedContent) {
        titleGeneratedRef.current = true;
        const title = generateTitle(streamedContent);
        dispatch({
          type: "SET_CONVERSATIONS",
          payload: conversationsRef.current.map((c) =>
            c.conversation_id === convIdRef.current ? { ...c, title } : c
          ),
        });
        apiPatch(`/conversations/${convIdRef.current}`, { title }).catch(() => {});
      }
      if (loadingTimerRef.current) { clearTimeout(loadingTimerRef.current); loadingTimerRef.current = null; }
      dispatch({ type: "SET_LOADING", payload: false });
      setMessages((prev) => prev.map((m) => (m.id === streamMsg.id && m.streaming ? { ...m, streaming: false } : m)));
      return;
    }

    // Fallback: sync POST
    try {
      const res = await apiPost<IntentResult>("/learning/chat", {
        message: content,
        conversation_id: convIdRef.current,
        base_agent_id: selectedBaseAgentId,
      });
      const finalMsg: ChatMsg = {
        id: streamMsg.id,
        role: "assistant",
        content: "",
        streaming: false,
        intentResult: res,
      };

      // Handle quiz_pending: set up callback for when user completes the quiz
      if (res.intent === "tutoring" && res.result.quiz_pending) {
        finalMsg.onQuizComplete = (answerResult: IntentResult) => {
          setMessages((prev) => prev.map((m) =>
            m.id === streamMsg.id ? { ...m, intentResult: answerResult, onQuizComplete: undefined } : m,
          ));
          const ar = answerResult.result;
          if (ar.updated_dimension) {
            apiGet<StudentProfile>("/profiles/me")
              .then((p) => dispatch({ type: "SET_PROFILE", payload: p }))
              .catch(() => {});
            apiGet<Recommendation[]>("/recommendations/")
              .then((recs) => dispatch({ type: "SET_RECOMMENDATIONS", payload: recs }))
              .catch(() => {});
          }
        };
      }

      setMessages((prev) => prev.map((m) => (m.id === streamMsg.id ? finalMsg : m)));

      // Sync intent results to global state for right panels
      const r = res.result;
      if (res.intent === "resource_generation") {
        if (r.profile) dispatch({ type: "SET_PROFILE", payload: r.profile as StudentProfile });
        if (r.path) dispatch({ type: "SET_PATH", payload: r.path as LearningPath });
        if (r.resources) dispatch({ type: "SET_RESOURCES", payload: r.resources as LearningResource[] });
        if (r.recommendations) dispatch({ type: "SET_RECOMMENDATIONS", payload: r.recommendations as Recommendation[] });
        if (r.workflow) dispatch({ type: "SET_WORKFLOW", payload: r.workflow as AgentWorkflow });
        if (r.conversation_id) dispatch({ type: "SET_SELECTED_CONVERSATION", payload: String(r.conversation_id) });
      } else if (res.intent === "learning_path" && r.path_id) {
        dispatch({ type: "SET_PATH", payload: asType<LearningPath>(r) });
      } else if (res.intent === "exercise" && r.resource_id) {
        dispatch({ type: "SET_RESOURCES", payload: [...resourcesRef.current, asType<LearningResource>(r)] });
      }

      // React to backend auto-generation changes
      const changes = r.changes as Record<string, unknown> | undefined;
      if (changes?.path_generated) {
        dispatch({ type: "SET_NOTICE", payload: "学习路径已自动生成，可在学习地图中查看" });
        dispatch({ type: "BUMP_PATH_VERSION" });
      }

      // Record learning activity (only for resource generation, not tutoring/exercise which need real assessment)
      const kp = profileRef.current?.learning_goal?.current_goal || content.slice(0, 50);
      // Add new conversation to sidebar in real-time
      const newConvId = res.conversation_id || (typeof r.conversation_id === "string" ? r.conversation_id : null);
      if (newConvId && !conversationsRef.current.some((c) => c.conversation_id === newConvId)) {
        dispatch({ type: "SET_SELECTED_CONVERSATION", payload: newConvId });
        convIdRef.current = newConvId; // update ref immediately for title generation below
        dispatch({
          type: "ADD_CONVERSATION",
          payload: {
            conversation_id: newConvId,
            user_id: user!.id,
            title: "新对话",
            messages: [],
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        });
      }

      // Auto-generate conversation title from first assistant response
      if (!titleGeneratedRef.current && convIdRef.current) {
        titleGeneratedRef.current = true;
        let titleContent = "";
        if (res.intent === "general_chat" && r.reply) titleContent = String(r.reply);
        else if (res.intent === "tutoring" && r.answer) titleContent = String(r.answer);
        else if (typeof r.content === "string") titleContent = r.content;
        else if (typeof r.reply === "string") titleContent = r.reply;
        if (titleContent) {
          const title = generateTitle(titleContent);
          dispatch({
            type: "SET_CONVERSATIONS",
            payload: conversationsRef.current.map((c) =>
              c.conversation_id === convIdRef.current ? { ...c, title } : c
            ),
          });
          apiPatch(`/conversations/${convIdRef.current}`, { title }).catch(() => {});
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setMessages((prev) =>
          prev.map((m) => (m.id === streamMsg.id ? { ...m, content: m.content || "已停止", streaming: false } : m))
        );
        return;
      }
      const errMsg = err instanceof Error ? getFriendlyError(err.message) : "请求失败，请重试";
      setMessages((prev) =>
        prev.map((m) => (m.id === streamMsg.id ? { ...m, content: errMsg, streaming: false } : m))
      );
    } finally {
      if (loadingTimerRef.current) { clearTimeout(loadingTimerRef.current); loadingTimerRef.current = null; }
      dispatch({ type: "SET_LOADING", payload: false });
      setMessages((prev) =>
        prev.map((m) => (m.id === streamMsg.id && m.streaming ? { ...m, streaming: false } : m))
      );
    }
  }, [user, selectedBaseAgentId, dispatch, onAuth, recordLearning]);

  const pipelineBusyRef = useRef(false);
  const sendPipelineMessage = useCallback(async (content: string, images?: string[]) => {
    if (!user) { onAuth(); return; }
    if (pipelineBusyRef.current) return;
    pipelineBusyRef.current = true;
    const displayContent = content + (images?.length ? ` [${images.length}张图片]` : "");
    const userMsg: ChatMsg = { id: crypto.randomUUID(), role: "user", content: displayContent, images };
    const assistantMsg: ChatMsg = { id: crypto.randomUUID(), role: "assistant", content: "正在启动学习流程...", streaming: true, trace: [] };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const trace: TraceEntry[] = [];
    let resultData: Record<string, unknown> | null = null;
    let streamError: string | null = null;

    try {
      await apiPostStream("/learning/start-stream", {
        message: content,
        conversation_id: convIdRef.current,
        base_agent_id: selectedBaseAgentId,
      }, (evt) => {
        const data = evt.data as Record<string, unknown>;
        if (evt.type === "error") {
          streamError = String(data.message || "学习流程执行失败，请重试");
        } else if (evt.type === "agent_step" && data.node) {
          const entry: TraceEntry = {
            node: String(data.node),
            hint: String(data.hint || ""),
            status: String(data.status || "running"),
            duration_ms: Number(data.duration_ms || 0),
            timestamp: Date.now(),
          };
          const existing = trace.findIndex((t) => t.node === entry.node);
          if (existing >= 0) trace[existing] = entry;
          else trace.push(entry);
          setMessages((prev) => prev.map((m) => m.id === assistantMsg.id ? {
            ...m, trace: [...trace], currentAgent: String(data.node),
          } : m));
        } else if (evt.type === "result") {
          resultData = data;
        }
      }, controller.signal);

      if (streamError) {
        const errMsg = streamError;
        setMessages((prev) => prev.map((m) => m.id === assistantMsg.id ? {
          ...m, content: errMsg, streaming: false, trace: [...trace],
        } : m));
        return;
      }

      // Pipeline complete — update global state
      if (resultData) {
        const r: Record<string, unknown> = resultData;
        if (r.profile) dispatch({ type: "SET_PROFILE", payload: r.profile as StudentProfile });
        if (r.path) dispatch({ type: "SET_PATH", payload: r.path as LearningPath });
        if (r.resources) dispatch({ type: "SET_RESOURCES", payload: r.resources as LearningResource[] });
        if (r.recommendations) dispatch({ type: "SET_RECOMMENDATIONS", payload: r.recommendations as Recommendation[] });
        if (r.workflow) dispatch({ type: "SET_WORKFLOW", payload: r.workflow as AgentWorkflow });
        if (r.conversation_id) dispatch({ type: "SET_SELECTED_CONVERSATION", payload: String(r.conversation_id) });

        const resCount = Array.isArray(r.resources) ? r.resources.length : 0;
        setMessages((prev) => prev.map((m) => m.id === assistantMsg.id ? {
          ...m, content: `学习流程完成，共生成 ${resCount} 个资源。`, streaming: false, trace: [...trace],
          resources: r.resources as LearningResource[] | undefined,
          recommendations: r.recommendations as Recommendation[] | undefined,
        } : m));
      } else {
        setMessages((prev) => prev.map((m) => m.id === assistantMsg.id ? { ...m, content: "学习流程完成。", streaming: false } : m));
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setMessages((prev) => prev.map((m) => m.id === assistantMsg.id ? { ...m, content: m.content || "已停止", streaming: false } : m));
        return;
      }
      const errMsg = err instanceof Error ? getFriendlyError(err.message) : "请求失败，请重试";
      setMessages((prev) => prev.map((m) => m.id === assistantMsg.id ? { ...m, content: errMsg, streaming: false } : m));
    } finally {
      pipelineBusyRef.current = false;
      setMessages((prev) => prev.map((m) => m.id === assistantMsg.id && m.streaming ? { ...m, streaming: false } : m));
    }
  }, [user, selectedBaseAgentId, dispatch, onAuth]);

  const sendMessage = useCallback(async (images?: string[]) => {
    if (!user) {
      onAuth();
      return;
    }
    const content = input.trim();
    if ((!content && !images?.length) || loading) return;

    setInput("");
    if (mode === "intent") {
      await sendIntentMessage(content);
    } else {
      await sendPipelineMessage(content, images);
    }
  }, [user, input, loading, mode, onAuth, sendIntentMessage, sendPipelineMessage]);

  const handlePlusMenuSelect = useCallback((key: string) => {
    if (key === "custom-agent") return onCreateAgent();
    if (key === "select-agent") return onSelectAgent();
    if (key === "model-config") return onModelConfig?.();
    if (key === "upload-image") {
      (window as any).__chatInputRefs?.openImageUpload?.();
      return;
    }
    if (key === "upload-video") {
      (window as any).__chatInputRefs?.openVideoUpload?.();
      return;
    }
  }, [onCreateAgent, onSelectAgent, onModelConfig]);

  const RESOURCE_HINTS = [
    { label: "文档资源", type: "document" as ResourceType },
    { label: "阅读材料", type: "reading" as ResourceType },
    { label: "题目资源", type: "quiz" as ResourceType },
    { label: "代码实操", type: "code_case" as ResourceType },
    { label: "思维导图", type: "mindmap" as ResourceType },
    { label: "视频动画", type: "video" as ResourceType },
    { label: "流程图", type: "flowchart" as ResourceType },
  ];

  const handleResourceHint = useCallback((label: string) => {
    if (!user) return onAuth();
    const topic = input.trim() || profileRef.current.learning_goal.current_goal || "通用知识点";
    setInput(`请为「${topic}」生成${label}`);
    setMode("pipeline");
  }, [user, input, onAuth]);

  const TYPE_LABELS: Record<string, string> = {
    document: "文档", mindmap: "思维导图", quiz: "测验", reading: "阅读",
    video: "视频", animation: "动画", code_case: "代码实操", flowchart: "流程图",
  };

  const handleAction = useCallback((action: string, payload?: string) => {
    if (action === "generate_resource" && payload) {
      const [kp, resType] = payload.split("|");
      const label = TYPE_LABELS[resType] || resType;
      setInput(`请为「${kp}」生成${label}`);
      setMode("pipeline");
    } else if (action === "post_test" && payload) {
      const msgId = `post-test-${Date.now()}`;
      const streamMsg: ChatMsg = { id: msgId, role: "assistant", content: "", streaming: true };
      setMessages((prev) => [...prev, streamMsg]);

      apiPost<{
        quiz_pending?: boolean;
        question?: Record<string, unknown>;
        quiz_session?: Record<string, unknown>;
        knowledge_point?: string;
        error?: string;
      }>("/learning/chat/post-quiz-start", {
        knowledge_point: payload,
        conversation_id: convIdRef.current,
        base_agent_id: selectedBaseAgentId,
      }).then((res) => {
        if (res.quiz_pending && res.question && res.quiz_session) {
          const kp = res.knowledge_point || payload;
          const quizMsg: ChatMsg = {
            id: msgId,
            role: "assistant",
            content: "",
            streaming: false,
            postQuiz: {
              question: res.question as any,
              quizSession: res.quiz_session as any,
              knowledgePoint: kp,
              conversationId: convIdRef.current,
              onComplete: () => {
                apiGet<StudentProfile>("/profiles/me")
                  .then((p) => dispatch({ type: "SET_PROFILE", payload: p }))
                  .catch(() => {});
                apiGet<Recommendation[]>("/recommendations/")
                  .then((recs) => dispatch({ type: "SET_RECOMMENDATIONS", payload: recs }))
                  .catch(() => {});
              },
            },
          };
          setMessages((prev) => prev.map((m) => (m.id === msgId ? quizMsg : m)));
        } else {
          setMessages((prev) => prev.map((m) =>
            m.id === msgId ? { ...m, content: res.error || "生成练习失败", streaming: false } : m
          ));
        }
      }).catch((err) => {
        const errMsg = err instanceof Error ? getFriendlyError(err.message) : "生成练习失败，请重试";
        setMessages((prev) => prev.map((m) =>
          m.id === msgId ? { ...m, content: errMsg, streaming: false } : m
        ));
      });
    }
  }, [dispatch]);

  // Extract pipeline trace from the latest streaming/completed assistant message
  const pipelineTrace = messages.reduce<TraceEntry[]>((acc, m) => {
    if (m.trace && m.trace.length > acc.length) return m.trace;
    return acc;
  }, []);
  const pipelineStreaming = messages.some((m) => m.streaming);
  const pipelineAgent = messages.find((m) => m.streaming)?.currentAgent ?? "";

  return (
    <div className="chat-panel">
      {pipelineTrace.length > 0 && (
        <PipelineBar trace={pipelineTrace} streaming={pipelineStreaming} currentAgent={pipelineAgent} />
      )}
      <div className="chat-mode-toggle">
        <button
          className={`chat-mode-btn ${mode === "intent" ? "active" : ""}`}
          onClick={() => setMode("intent")}
          type="button"
        >
          智能对话
        </button>
        <button
          className={`chat-mode-btn ${mode === "pipeline" ? "active" : ""}`}
          onClick={() => setMode("pipeline")}
          type="button"
        >
          学习流程
        </button>
      </div>

      <div className="chat-workspace-hero">
        <div className="chat-workspace-copy">
          <span className="chat-workspace-kicker">{mode === "intent" ? "智能对话模式" : "学习流程模式"}</span>
          <h2>{state.profile.learning_goal.current_goal || "开始一轮新的学习协作"}</h2>
          <p>
            {mode === "intent"
              ? "适合提问、追问、解释概念或针对图片内容继续辅导。"
              : "适合直接输入学习目标，系统会自动组织画像、路径、资源与推荐结果。"}
          </p>
          <div className="chat-workspace-tags">
            <span>{state.profile.learning_behavior.last_knowledge_point || "等待识别知识点"}</span>
            <span>{user ? `会话 ${state.selectedConversationId ? "继续中" : "未开始"}` : "未登录"}</span>
          </div>
        </div>

        <div className="chat-workspace-stats">
          {workspaceStats.map((item) => (
            <article className="chat-workspace-stat" key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </article>
          ))}
        </div>
      </div>

      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <div className="chat-empty-card">
              <h3>{mode === "intent" ? "开始智能对话" : "启动学习流程"}</h3>
              {mode === "intent" ? (
                <p>输入问题，AI 将自动识别意图并路由到合适的模块。</p>
              ) : (
                <p>输入学习目标，AI 将构建画像、规划路径并生成资源。</p>
              )}
              <div className="chat-empty-suggestions">
                <button type="button" onClick={() => setInput("帮我出几道快速排序的练习题")}>练习刷题</button>
                <button type="button" onClick={() => setInput("帮我生成一个思维导图")}>生成资源</button>
                <button type="button" onClick={() => setInput("展示学习地图")}>学习地图</button>
                <button type="button" onClick={() => setInput("看看我的学习情况")}>学习看板</button>
                <button type="button" onClick={() => setInput("帮我规划一个数据结构的学习路径")}>规划路径</button>
                <button type="button" onClick={() => setInput("评估一下我的学习掌握程度")}>学习评估</button>
              </div>
            </div>
          </div>
        ) : (
          <Virtuoso
            data={messages}
            followOutput="smooth"
            itemContent={(index, msg) => (
              <ErrorBoundary fallback={<div style={{ padding: 12, color: "#ef4444", fontSize: 13 }}>消息渲染出错，请刷新重试。</div>}>
                <ChatMessage message={{ ...msg, onAction: handleAction }} />
              </ErrorBoundary>
            )}
            style={{ flex: 1 }}
          />
        )}
      </div>

      <div className="floating-learning-input-wrapper">
        <div className="resource-hint-bar">
          {RESOURCE_HINTS.map((h) => (
            <button
              key={h.type}
              className="resource-hint-chip"
              type="button"
              onClick={() => handleResourceHint(h.label)}
            >
              {h.label}
            </button>
          ))}
        </div>
        {ragContext.length > 0 && (
          <div className="tutor-context-bar">
            <span className="tutor-context-label">引用知识：</span>
            {ragContext.map((ctx) => (
              <span key={ctx.chunk_id} className="tutor-context-tag">
                {ctx.title}
                <button type="button" onClick={() => setRagContext((prev) => prev.filter((p) => p.chunk_id !== ctx.chunk_id))}>
                  <X size={12} />
                </button>
              </span>
            ))}
          </div>
        )}

        {ragPanelOpen && (
          <div className="chat-rag-panel">
            <div className="chat-rag-search">
              <Search size={14} />
              <input
                className="chat-rag-input"
                placeholder="检索知识库..."
                value={ragQuery}
                onChange={(e) => setRagQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && ragQuery.trim()) {
                    setRagLoading(true);
                    apiPost<{ results: Array<{ chunk_id: string; title: string; content: string; subject: string; score: number }> }>("/knowledge/search", { query: ragQuery.trim(), top_k: 5 })
                      .then((data) => setRagResults(data.results ?? []))
                      .catch(() => setRagResults([]))
                      .finally(() => setRagLoading(false));
                  }
                }}
              />
              <button type="button" className="chat-rag-close" onClick={() => { setRagPanelOpen(false); setRagResults(null); }}>
                <X size={14} />
              </button>
            </div>
            {ragLoading && <div className="chat-rag-loading">搜索中...</div>}
            {ragResults && (
              <div className="chat-rag-results">
                {ragResults.length === 0 ? (
                  <div className="chat-rag-empty">未找到相关知识</div>
                ) : (
                  ragResults.map((r) => (
                    <div key={r.chunk_id} className="chat-rag-item" onClick={() => {
                      setRagContext((prev) => prev.some((p) => p.chunk_id === r.chunk_id) ? prev : [...prev, { chunk_id: r.chunk_id, title: r.title, content: r.content, subject: r.subject }]);
                    }}>
                      <div className="chat-rag-item-title">{r.title}</div>
                      <div className="chat-rag-item-content">{r.content.length > 100 ? r.content.slice(0, 100) + "..." : r.content}</div>
                      <div className="chat-rag-item-meta">{r.subject} · 相关度 {Math.round(r.score * 100)}%</div>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        )}

        <div className="floating-learning-input">
          <div className="input-left-tools">
            <PlusMenu onSelect={handlePlusMenuSelect} />
            <button
              type="button"
              className={`rag-toggle-btn ${ragPanelOpen ? "active" : ""}`}
              onClick={() => setRagPanelOpen(!ragPanelOpen)}
              title="知识检索"
            >
              <Search size={16} />
            </button>
          </div>
          <ChatInput
            value={input}
            onChange={setInput}
            onSend={sendMessage}
            loading={loading}
            onStop={() => abortRef.current?.abort()}
            disabled={!user}
          />
        </div>
      </div>
    </div>
  );
}
