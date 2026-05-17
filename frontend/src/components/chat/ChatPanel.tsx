import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAppContext } from "../../context/AppContext";
import { apiGet, apiPatch, apiPost, apiPostStream, getFriendlyError } from "../../api/client";
import { useRecordLearning } from "../../hooks/useRecordLearning";
import { ChatMessage, type ChatMsg, type IntentResult, type TraceEntry } from "./ChatMessage";
import { ChatInput } from "./ChatInput";
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
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const titleGeneratedRef = useRef(false);
  const resourcesRef = useRef(state.resources);
  resourcesRef.current = state.resources;
  const conversationsRef = useRef(state.conversations);
  conversationsRef.current = state.conversations;
  const prevConvIdRef = useRef<string | null>(null);

  const selectedAgent = baseAgents.find((a) => a.agent_id === selectedBaseAgentId) ?? null;
  const recordLearning = useRecordLearning();

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (state.activeMessages.length > 0) {
      const converted: ChatMsg[] = state.activeMessages.map((msg) => ({
        id: msg.id,
        role: msg.role as ChatMsg["role"],
        content: msg.content,
        streaming: false,
      }));
      setMessages(converted);
    } else {
      setMessages([]);
    }
  }, [state.activeMessages]);

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

    // Use SSE streaming for tutor answers
    let usedStreaming = false;
    let streamedContent = "";
    try {
      let resultData: Record<string, unknown> | null = null;

      let streamError: string | null = null;
      await apiPostStream("/learning/chat-stream", {
        user_id: user.id,
        message: content,
        conversation_id: state.selectedConversationId,
        base_agent_id: selectedBaseAgentId,
      }, (evt) => {
        if (evt.type === "error") {
          streamError = String((evt.data as Record<string, unknown>).message || "AI 服务暂时不可用，请重试");
        } else if (evt.type === "text_delta" && typeof (evt.data as Record<string, unknown>).content === "string") {
          streamedContent += (evt.data as Record<string, unknown>).content;
          setMessages((prev) => prev.map((m) => m.id === streamMsg.id ? { ...m, content: streamedContent } : m));
        } else if (evt.type === "result") {
          resultData = evt.data as Record<string, unknown>;
        }
      }, controller.signal);

      usedStreaming = true;

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
          }
        };
      }

      setMessages((prev) => prev.map((m) => (m.id === streamMsg.id ? finalMsg : m)));

      // Sync global state for non-tutoring intents
      const r = res.result;
      if (res.intent === "resource_generation" && r.profile) {
        dispatch({ type: "SET_PROFILE", payload: r.profile as StudentProfile });
        if (r.path) dispatch({ type: "SET_PATH", payload: r.path as LearningPath });
        if (r.resources) dispatch({ type: "SET_RESOURCES", payload: r.resources as LearningResource[] });
        if (r.recommendations) dispatch({ type: "SET_RECOMMENDATIONS", payload: r.recommendations as Recommendation[] });
        if (r.conversation_id) dispatch({ type: "SET_SELECTED_CONVERSATION", payload: String(r.conversation_id) });
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
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
      if (!titleGeneratedRef.current && state.selectedConversationId && streamedContent) {
        titleGeneratedRef.current = true;
        const title = generateTitle(streamedContent);
        dispatch({
          type: "SET_CONVERSATIONS",
          payload: conversationsRef.current.map((c) =>
            c.conversation_id === state.selectedConversationId ? { ...c, title } : c
          ),
        });
        apiPatch(`/conversations/${state.selectedConversationId}`, { title }).catch(() => {});
      }
      dispatch({ type: "SET_LOADING", payload: false });
      setMessages((prev) => prev.map((m) => (m.id === streamMsg.id && m.streaming ? { ...m, streaming: false } : m)));
      return;
    }

    // Fallback: sync POST
    try {
      const res = await apiPost<IntentResult>("/learning/chat", {
        user_id: user.id,
        message: content,
        conversation_id: state.selectedConversationId,
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
          }
        };
      }

      setMessages((prev) => prev.map((m) => (m.id === streamMsg.id ? finalMsg : m)));

      // Sync intent results to global state for right panels
      const r = res.result;
      if (res.intent === "resource_generation" && r.profile) {
        dispatch({ type: "SET_PROFILE", payload: r.profile as StudentProfile });
        if (r.path) dispatch({ type: "SET_PATH", payload: r.path as LearningPath });
        if (r.resources) dispatch({ type: "SET_RESOURCES", payload: r.resources as LearningResource[] });
        if (r.recommendations) dispatch({ type: "SET_RECOMMENDATIONS", payload: r.recommendations as Recommendation[] });
        if (r.workflow) dispatch({ type: "SET_WORKFLOW", payload: r.workflow as AgentWorkflow });
        if (r.conversation_id) dispatch({ type: "SET_SELECTED_CONVERSATION", payload: String(r.conversation_id) });
      } else if (res.intent === "learning_path" && r.path_id) {
        dispatch({ type: "SET_PATH", payload: r as unknown as LearningPath });
      } else if (res.intent === "exercise" && r.resource_id) {
        dispatch({ type: "SET_RESOURCES", payload: [...resourcesRef.current, r as unknown as LearningResource] });
      }

      // Record learning activity (only for resource generation, not tutoring/exercise which need real assessment)
      const kp = state.profile?.learning_goal?.current_goal || content.slice(0, 50);
      if (res.intent === "resource_generation") {
        recordLearning({ knowledge_point: kp, resource_type: "document", score: 0.3 });
      }

      // Add new conversation to sidebar in real-time
      const newConvId = res.conversation_id || (typeof r.conversation_id === "string" ? r.conversation_id : null);
      if (newConvId && !conversationsRef.current.some((c) => c.conversation_id === newConvId)) {
        dispatch({ type: "SET_SELECTED_CONVERSATION", payload: newConvId });
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
      if (!titleGeneratedRef.current && state.selectedConversationId) {
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
              c.conversation_id === state.selectedConversationId ? { ...c, title } : c
            ),
          });
          apiPatch(`/conversations/${state.selectedConversationId}`, { title }).catch(() => {});
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
      dispatch({ type: "SET_LOADING", payload: false });
      setMessages((prev) =>
        prev.map((m) => (m.id === streamMsg.id && m.streaming ? { ...m, streaming: false } : m))
      );
    }
  }, [user, state.selectedConversationId, state.conversations, state.resources, selectedBaseAgentId, dispatch, onAuth, recordLearning]);

  const sendPipelineMessage = useCallback(async (content: string, images?: string[]) => {
    if (!user) { onAuth(); return; }
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
        user_id: user.id,
        message: content,
        conversation_id: state.selectedConversationId,
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
      setMessages((prev) => prev.map((m) => m.id === assistantMsg.id && m.streaming ? { ...m, streaming: false } : m));
    }
  }, [user, state.selectedConversationId, dispatch, onAuth]);

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

    const resourceTypeMap: Record<string, { label: string; type: ResourceType }> = {
      "add-document": { label: "文档资源", type: "document" },
      "add-reading": { label: "阅读材料", type: "reading" },
      "add-quiz": { label: "题目资源", type: "quiz" },
      "add-code": { label: "代码实操", type: "code_case" },
      "add-mindmap": { label: "思维导图", type: "mindmap" },
      "add-video": { label: "视频动画", type: "video" },
      "add-flowchart": { label: "流程图", type: "flowchart" },
    };
    const mapped = resourceTypeMap[key];
    if (!mapped) return;
    if (!user) return onAuth();

    const topic = input.trim() || state.profile.learning_goal.current_goal || "通用知识点";
    setInput(`请为「${topic}」生成${mapped.label}`);
    setMode("pipeline");
  }, [user, input, state.profile, onCreateAgent, onSelectAgent, onModelConfig, onAuth]);

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

      apiPost<IntentResult>("/learning/chat/post-test", {
        knowledge_point: payload,
        conversation_id: state.selectedConversationId,
      }).then((res) => {
        const finalMsg: ChatMsg = { id: msgId, role: "assistant", content: "", streaming: false, intentResult: res };
        if (res.result.quiz_pending) {
          finalMsg.onQuizComplete = (answerResult: IntentResult) => {
            setMessages((prev) => prev.map((m) =>
              m.id === msgId ? { ...m, intentResult: answerResult, onQuizComplete: undefined } : m,
            ));
            const ar = answerResult.result;
            if (ar.updated_dimension) {
              apiGet<StudentProfile>("/profiles/me")
                .then((p) => dispatch({ type: "SET_PROFILE", payload: p }))
                .catch(() => {});
            }
          };
        }
        setMessages((prev) => prev.map((m) => (m.id === msgId ? finalMsg : m)));
      }).catch(() => {
        setMessages((prev) => prev.map((m) =>
          m.id === msgId ? { ...m, content: "生成测试失败，请重试", streaming: false } : m
        ));
      });
    }
  }, [state.selectedConversationId, dispatch]);

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

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            {mode === "intent" ? (
              <p>输入问题，AI 将自动识别意图并路由到合适的模块。</p>
            ) : (
              <p>输入学习目标，AI 将构建画像、规划路径并生成资源。</p>
            )}
          </div>
        )}
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={{ ...msg, onAction: handleAction }} />
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="floating-learning-input">
        <PlusMenu onSelect={handlePlusMenuSelect} />
        <ChatInput
          value={input}
          onChange={setInput}
          onSend={sendMessage}
          loading={loading}
          onStop={() => abortRef.current?.abort()}
          agentName={selectedAgent?.name ?? "系统默认基座智能体"}
          isSystemAgent={selectedAgent?.is_system ?? true}
          disabled={!user}
        />
      </div>
    </div>
  );
}
