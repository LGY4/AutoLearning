import { useState, useEffect, useCallback } from "react";
import { apiGet, apiDelete, apiPostForm } from "../api/client";
import { useAppContext } from "../context/AppContext";
import { useTaskPolling } from "../hooks/useTaskPolling";
import { Spinner } from "../components/common/Spinner";
import { ResourceRenderer } from "../components/resource/ResourceRenderer";
import type { LearningResource } from "../types/baseline";

interface ResourceItem {
  resource_id: string;
  title: string;
  resource_type: string;
  knowledge_point: string;
  difficulty: string;
  quality_score: number;
  status: string;
  created_at: string | null;
}

interface QuestionItem {
  id: string;
  knowledge_point: string;
  question_type: string;
  stem: string;
  difficulty_level: string;
  subject: string;
  tags: string[];
}

interface LibraryData {
  total: number;
  page: number;
  resources: ResourceItem[];
}

interface QuestionBankData {
  total: number;
  page: number;
  questions: QuestionItem[];
}

const TYPE_LABELS: Record<string, string> = {
  document: "文档",
  quiz: "题目",
  mindmap: "思维导图",
  video: "视频",
  animation: "动画",
  code_case: "代码",
  reading: "阅读",
};

const QTYPE_LABELS: Record<string, string> = {
  choice: "选择题",
  blank: "填空题",
  short_answer: "简答题",
  programming: "编程题",
  case_analysis: "案例分析",
};

type Tab = "resources" | "questions" | "answers" | "bilibili" | "knowledge";

export function ResourceLibraryPage() {
  const { state } = useAppContext();
  const userId = state.user?.id;

  const [tab, setTab] = useState<Tab>("resources");
  const [resources, setResources] = useState<LibraryData>({ total: 0, page: 1, resources: [] });
  const [questions, setQuestions] = useState<QuestionBankData>({ total: 0, page: 1, questions: [] });
  const [answers, setAnswers] = useState<Array<{ id: string; question_id: string; user_answer: unknown; is_correct: boolean; score: number | null; grading_method: string; time_spent_seconds: number | null; submitted_at: string | null }>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterType, setFilterType] = useState("");
  const [keyword, setKeyword] = useState("");

  // Bilibili search
  const [biliKeyword, setBiliKeyword] = useState("");
  const [biliResults, setBiliResults] = useState<{ total: number; results: Array<{ bvid: string; title: string; author: string; play: number; duration: string; url: string; pic: string }> } | null>(null);

  // Resource detail
  const [selectedResource, setSelectedResource] = useState<LearningResource | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Upload
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploading, setUploading] = useState(false);

  // Task status polling
  const [taskId, setTaskId] = useState("");
  const { taskStatus, polling, startPolling } = useTaskPolling({
    intervalMs: 3000,
    onDone: () => { if (tab === "resources") loadResources(); },
  });

  const handleResourceClick = async (resourceId: string) => {
    setDetailLoading(true);
    try {
      const data = await apiGet<LearningResource>(`/resources/${resourceId}`);
      setSelectedResource(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载资源详情失败");
    } finally {
      setDetailLoading(false);
    }
  };

  const handleUpload = async () => {
    if (!uploadFile || !uploadTitle.trim() || !userId) return;
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("user_id", userId);
      formData.append("title", uploadTitle.trim());
      formData.append("resource_type", "document");
      formData.append("file", uploadFile);
      await apiPostForm("/resources/upload", formData);
      setUploadFile(null);
      setUploadTitle("");
      loadResources();
    } catch (e) {
      setError(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploading(false);
    }
  };

  const loadResources = useCallback(async (page = 1) => {
    if (!userId) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "15" });
      if (filterType) params.set("resource_type", filterType);
      if (keyword) params.set("keyword", keyword);
      const data = await apiGet<LibraryData>(`/resources/library?${params}`);
      setResources(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载资源失败");
    } finally { setLoading(false); }
  }, [userId, filterType, keyword]);

  const loadQuestions = useCallback(async (page = 1) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "15" });
      if (filterType) params.set("question_type", filterType);
      if (keyword) params.set("knowledge_point", keyword);
      const data = await apiGet<QuestionBankData>(`/resources/questions/list?${params}`);
      setQuestions(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载题库失败");
    } finally { setLoading(false); }
  }, [filterType, keyword]);

  const loadAnswers = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiGet<Array<{ id: string; question_id: string; user_answer: unknown; is_correct: boolean; score: number | null; grading_method: string; time_spent_seconds: number | null; submitted_at: string | null }>>("/resources/answers");
      setAnswers(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载答题记录失败");
    } finally { setLoading(false); }
  }, [userId]);

  useEffect(() => {
    setFilterType("");
    setKeyword("");
    if (tab === "resources") loadResources();
    else if (tab === "questions") loadQuestions();
    else if (tab === "answers") loadAnswers();
  }, [tab]);

  const handleDeleteResource = async (id: string) => {
    if (!userId) return;
    try {
      await apiDelete(`/resources/library/${id}`);
      loadResources(resources.page);
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  };

  const handleDeleteQuestion = async (id: string) => {
    try {
      await apiDelete(`/resources/questions/${id}`);
      setQuestions((prev) => ({ ...prev, questions: prev.questions.filter((q) => q.id !== id), total: prev.total - 1 }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  };

  const [videoPlayerUrl, setVideoPlayerUrl] = useState<string | null>(null);

  const handlePlayVideo = (videoId: string) => {
    setVideoPlayerUrl(`/api/v1/video/file/${videoId}`);
  };

  const handleBiliSearch = async () => {
    if (!biliKeyword.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiGet<{ total: number; results: Array<{ bvid: string; title: string; author: string; play: number; duration: string; url: string; pic: string }> }>(`/bilibili/search/${encodeURIComponent(biliKeyword)}?page_size=10`);
      setBiliResults(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "B站搜索失败");
    } finally { setLoading(false); }
  };

  return (
    <div className="res-lib">
      <h2>资源库</h2>

      <div className="res-lib-tabs">
        <button className={`res-lib-tab ${tab === "resources" ? "active" : ""}`} onClick={() => setTab("resources")} type="button">我的资源</button>
        <button className={`res-lib-tab ${tab === "questions" ? "active" : ""}`} onClick={() => setTab("questions")} type="button">题库</button>
        <button className={`res-lib-tab ${tab === "answers" ? "active" : ""}`} onClick={() => setTab("answers")} type="button">答题记录</button>
        <button className={`res-lib-tab ${tab === "bilibili" ? "active" : ""}`} onClick={() => setTab("bilibili")} type="button">B站视频</button>
        <button className={`res-lib-tab ${tab === "knowledge" ? "active" : ""}`} onClick={() => setTab("knowledge")} type="button">知识库</button>
      </div>

      {/* Filters */}
      {tab !== "bilibili" && (
        <div className="res-lib-filters">
          <input
            className="res-lib-search"
            placeholder={tab === "resources" ? "搜索资源..." : "搜索知识点..."}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (tab === "resources" ? loadResources() : loadQuestions())}
          />
          <select className="res-lib-select" value={filterType} onChange={(e) => setFilterType(e.target.value)}>
            <option value="">全部类型</option>
            {tab === "resources"
              ? Object.entries(TYPE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)
              : Object.entries(QTYPE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)
            }
          </select>
        </div>
      )}

      {error && <div className="res-lib-error">{error}</div>}
      {loading && <div className="res-lib-loading"><Spinner /></div>}

      {/* Upload section */}
      {tab === "resources" && (
        <div className="res-lib-upload">
          <input
            className="res-lib-upload-title"
            placeholder="资源标题"
            value={uploadTitle}
            onChange={(e) => setUploadTitle(e.target.value)}
          />
          <label className="res-lib-upload-btn">
            {uploadFile ? uploadFile.name : "选择文件"}
            <input
              type="file"
              accept=".md,.txt,.json,.py,.js,.ts,.java,.c,.cpp,.html,.css,.csv,.pdf"
              onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
              hidden
            />
          </label>
          <button
            className="res-lib-upload-submit"
            onClick={handleUpload}
            disabled={!uploadFile || !uploadTitle.trim() || uploading}
            type="button"
          >
            {uploading ? "上传中..." : "上传"}
          </button>
        </div>
      )}

      {/* Task status - hidden for regular users, shown only when there's an active task */}
      {taskStatus && (
        <div className="res-lib-card" style={{ marginBottom: 12 }}>
          <div className="res-lib-card-top">
            <span className={`res-lib-type ${taskStatus.status === "done" ? "res-lib-correct" : taskStatus.status === "failed" ? "res-lib-wrong" : ""}`}>
              {taskStatus.status}
            </span>
            <span className="res-lib-kp">任务 {taskStatus.task_id}</span>
          </div>
          {taskStatus.status === "running" && <Spinner />}
          {taskStatus.error && <div className="res-lib-error">{taskStatus.error}</div>}
          {taskStatus.result && (
            <div className="res-lib-card-meta">
              生成完成 · {((taskStatus.result as Record<string, unknown>).resources as unknown[])?.length ?? 0} 个资源
            </div>
          )}
        </div>
      )}

      {/* Resource list */}
      {tab === "resources" && !loading && (
        <div className="res-lib-list">
          {resources.resources.length === 0 ? (
            <p className="res-lib-empty">暂无资源</p>
          ) : (
            resources.resources.map((r) => (
              <div key={r.resource_id} className="res-lib-card res-lib-card-clickable" onClick={() => handleResourceClick(r.resource_id)} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && handleResourceClick(r.resource_id)}>
                <div className="res-lib-card-top">
                  <span className="res-lib-type">{TYPE_LABELS[r.resource_type] || r.resource_type}</span>
                  <span className="res-lib-kp">{r.knowledge_point}</span>
                </div>
                <div className="res-lib-card-title">{r.title}</div>
                <div className="res-lib-card-meta">
                  {r.difficulty} · 质量 {Math.round(r.quality_score * 100)}%
                  {r.created_at && ` · ${new Date(r.created_at).toLocaleDateString()}`}
                </div>
                <button className="res-lib-delete" onClick={(e) => { e.stopPropagation(); handleDeleteResource(r.resource_id); }} type="button">删除</button>
              </div>
            ))
          )}
          {resources.total > 15 && (
            <div className="res-lib-pagination">
              <button disabled={resources.page <= 1} onClick={() => loadResources(resources.page - 1)}>上一页</button>
              <span>{resources.page} / {Math.ceil(resources.total / 15)}</span>
              <button disabled={resources.page * 15 >= resources.total} onClick={() => loadResources(resources.page + 1)}>下一页</button>
            </div>
          )}
        </div>
      )}

      {/* Question bank */}
      {tab === "questions" && !loading && (
        <div className="res-lib-list">
          {questions.questions.length === 0 ? (
            <p className="res-lib-empty">暂无题目</p>
          ) : (
            questions.questions.map((q) => (
              <div key={q.id} className="res-lib-card">
                <div className="res-lib-card-top">
                  <span className="res-lib-type">{QTYPE_LABELS[q.question_type] || q.question_type}</span>
                  <span className="res-lib-kp">{q.knowledge_point}</span>
                </div>
                <div className="res-lib-card-title">{q.stem.length > 100 ? q.stem.slice(0, 100) + "..." : q.stem}</div>
                <div className="res-lib-card-meta">
                  {q.difficulty_level} · {q.subject}
                  {q.tags.length > 0 && ` · ${q.tags.join(", ")}`}
                </div>
                <button className="res-lib-delete" onClick={() => handleDeleteQuestion(q.id)} type="button">删除</button>
              </div>
            ))
          )}
        </div>
      )}

      {/* Answer history */}
      {tab === "answers" && !loading && (
        <div className="res-lib-list">
          {answers.length === 0 ? (
            <p className="res-lib-empty">暂无答题记录</p>
          ) : (
            answers.map((a) => (
              <div key={a.id} className="res-lib-card">
                <div className="res-lib-card-top">
                  <span className={`res-lib-type ${a.is_correct ? "res-lib-correct" : "res-lib-wrong"}`}>
                    {a.is_correct ? "✓ 正确" : "✗ 错误"}
                  </span>
                  {a.score != null && <span className="res-lib-kp">{a.score}分</span>}
                </div>
                <div className="res-lib-card-title">
                  答案：{typeof a.user_answer === "string" ? a.user_answer : JSON.stringify(a.user_answer)}
                </div>
                <div className="res-lib-card-meta">
                  题目 ID: {a.question_id?.slice(0, 8)}...
                  {a.grading_method === "llm" ? " · AI 评分" : ""}
                  {a.time_spent_seconds ? ` · 用时 ${a.time_spent_seconds}秒` : ""}
                  {a.submitted_at && ` · ${new Date(a.submitted_at).toLocaleString()}`}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Bilibili search */}
      {tab === "bilibili" && (
        <div className="res-lib-bili">
          <div className="res-lib-bili-search">
            <input
              className="res-lib-search"
              placeholder="搜索B站教学视频..."
              value={biliKeyword}
              onChange={(e) => setBiliKeyword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleBiliSearch()}
            />
            <button className="res-lib-bili-btn" onClick={handleBiliSearch} disabled={loading}>搜索</button>
          </div>
          {biliResults && (
            <div className="res-lib-list">
              {biliResults.results.length === 0 ? (
                <p className="res-lib-empty">未找到结果</p>
              ) : (
                biliResults.results.map((v) => (
                  <a key={v.bvid} className="res-lib-card res-lib-bili-card" href={v.url} target="_blank" rel="noopener noreferrer">
                    {v.pic && <img className="res-lib-bili-pic" src={v.pic} alt="" loading="lazy" />}
                    <div>
                      <div className="res-lib-card-title">{v.title}</div>
                      <div className="res-lib-card-meta">{v.author} · {v.duration} · {v.play.toLocaleString()} 播放</div>
                    </div>
                  </a>
                ))
              )}
            </div>
          )}
        </div>
      )}

      {/* Resource detail overlay */}
      {selectedResource && (
        <div className="res-lib-detail-overlay" onClick={() => setSelectedResource(null)} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Escape" && setSelectedResource(null)}>
          <div className="res-lib-detail" onClick={(e) => e.stopPropagation()}>
            <div className="res-lib-detail-header">
              <div>
                <span className="res-lib-type">{TYPE_LABELS[selectedResource.resource_type] || selectedResource.resource_type}</span>
                <strong>{selectedResource.title}</strong>
              </div>
              <button className="res-lib-detail-close" onClick={() => setSelectedResource(null)} type="button">✕</button>
            </div>
            <div className="res-lib-detail-body">
              <ResourceRenderer resource={selectedResource} />
            </div>
          </div>
        </div>
      )}
      {detailLoading && <div className="res-lib-loading"><Spinner /></div>}

      {/* Video player overlay */}
      {videoPlayerUrl && (
        <div className="res-lib-detail-overlay" onClick={() => setVideoPlayerUrl(null)} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Escape" && setVideoPlayerUrl(null)}>
          <div className="res-lib-detail" onClick={(e) => e.stopPropagation()}>
            <div className="res-lib-detail-header">
              <strong>视频播放</strong>
              <button className="res-lib-detail-close" onClick={() => setVideoPlayerUrl(null)} type="button">✕</button>
            </div>
            <div className="res-lib-detail-body">
              <video controls autoPlay style={{ width: "100%", maxHeight: 500 }} src={videoPlayerUrl} />
            </div>
          </div>
        </div>
      )}

      {/* Personal Knowledge Base tab */}
      {tab === "knowledge" && (
        <KnowledgeBaseSection />
      )}
    </div>
  );
}


function KnowledgeBaseSection() {
  const [docs, setDocs] = useState<Array<{ title: string; subject: string; source: string; chunk_count: number; tags: string[] }>>([]);
  const [stats, setStats] = useState<{ total_chunks: number; documents: number }>({ total_chunks: 0, documents: 0 });
  const [uploading, setUploading] = useState(false);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadSubject, setUploadSubject] = useState("通用");
  const [loading, setLoading] = useState(true);
  const fileRef = { current: null as HTMLInputElement | null };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [docsData, statsData] = await Promise.all([
        apiGet<Array<{ title: string; subject: string; source: string; chunk_count: number; tags: string[] }>>("/knowledge/my-documents"),
        apiGet<{ total_chunks: number; documents: number }>("/knowledge/my-stats"),
      ]);
      setDocs(docsData);
      setStats(statsData);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file || !uploadTitle.trim()) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const params = new URLSearchParams({ title: uploadTitle.trim(), subject: uploadSubject });
      await fetch(`/api/v1/knowledge/upload?${params}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("autolearning_access_token") || ""}` },
        body: formData,
      });
      setUploadTitle("");
      if (fileRef.current) fileRef.current.value = "";
      await loadData();
    } catch { /* ignore */ }
    setUploading(false);
  };

  const handleDelete = async (title: string) => {
    if (!confirm(`确定删除「${title}」？`)) return;
    try {
      await apiDelete(`/knowledge/my-documents/${encodeURIComponent(title)}`);
      await loadData();
    } catch { /* ignore */ }
  };

  return (
    <div style={{ padding: 16 }}>
      <h3 style={{ margin: "0 0 16px", fontSize: 16 }}>个人知识库</h3>
      <p style={{ fontSize: 13, color: "#9ca3af", marginBottom: 16 }}>
        上传文档到个人知识库，AI 辅导时会优先引用你上传的内容。支持 PDF、DOCX、PPTX、TXT、MD 格式。
      </p>

      {/* Stats */}
      <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
        <div style={{ padding: 12, background: "var(--bg-card)", borderRadius: 8, flex: 1 }}>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{stats.documents}</div>
          <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>文档数</div>
        </div>
        <div style={{ padding: 12, background: "var(--bg-card)", borderRadius: 8, flex: 1 }}>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{stats.total_chunks}</div>
          <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>知识片段</div>
        </div>
      </div>

      {/* Upload form */}
      <div style={{ padding: 16, border: "1px solid var(--border-primary)", borderRadius: 8, marginBottom: 16 }}>
        <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 14 }}>上传文档</div>
        <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
          <input
            type="text"
            placeholder="文档标题"
            value={uploadTitle}
            onChange={(e) => setUploadTitle(e.target.value)}
            style={{ flex: 1, padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border-primary)", background: "var(--bg-input)", color: "var(--text-primary)", fontSize: 13 }}
          />
          <input
            type="text"
            placeholder="学科（可选）"
            value={uploadSubject}
            onChange={(e) => setUploadSubject(e.target.value)}
            style={{ width: 120, padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border-primary)", background: "var(--bg-input)", color: "var(--text-primary)", fontSize: 13 }}
          />
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            ref={(el) => { fileRef.current = el; }}
            type="file"
            accept=".pdf,.docx,.pptx,.txt,.md,.json,.py,.js,.ts"
            style={{ fontSize: 13 }}
          />
          <button
            onClick={handleUpload}
            disabled={uploading || !uploadTitle.trim()}
            style={{ padding: "6px 16px", borderRadius: 6, border: "none", background: uploadTitle.trim() ? "var(--accent-primary)" : "var(--bg-card)", color: "white", cursor: "pointer", fontSize: 13, whiteSpace: "nowrap" }}
          >
            {uploading ? "上传中..." : "上传"}
          </button>
        </div>
      </div>

      {/* Document list */}
      {loading ? (
        <div style={{ textAlign: "center", padding: 32 }}><Spinner /></div>
      ) : docs.length === 0 ? (
        <div style={{ textAlign: "center", padding: 32, color: "var(--text-tertiary)" }}>
          暂无文档，上传你的学习资料开始使用。
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {docs.map((doc, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px", border: "1px solid var(--border-primary)", borderRadius: 8 }}>
              <div>
                <div style={{ fontWeight: 500, fontSize: 14 }}>{doc.title}</div>
                <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
                  {doc.subject} · {doc.chunk_count} 个片段
                  {doc.tags?.length > 0 && ` · ${doc.tags.slice(0, 3).join(", ")}`}
                </div>
              </div>
              <button
                onClick={() => handleDelete(doc.title)}
                style={{ padding: "4px 10px", borderRadius: 6, border: "1px solid var(--status-error)", background: "transparent", color: "var(--status-error)", cursor: "pointer", fontSize: 12 }}
              >
                删除
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
