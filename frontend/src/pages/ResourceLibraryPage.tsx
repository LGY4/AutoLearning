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

type Tab = "resources" | "questions" | "answers" | "bilibili";

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
    if (tab === "resources") loadResources();
    else if (tab === "questions") loadQuestions();
    else if (tab === "answers") loadAnswers();
  }, [tab, loadResources, loadQuestions, loadAnswers]);

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
              accept=".md,.txt,.json,.py,.js,.ts,.java,.c,.cpp,.html,.css,.csv"
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

      {/* Task status */}
      {tab === "resources" && (
        <div className="res-lib-upload" style={{ marginBottom: 12 }}>
          <input
            className="res-lib-upload-title"
            placeholder="输入任务 ID 查看状态"
            value={taskId}
            onChange={(e) => setTaskId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && taskId.trim() && startPolling(taskId.trim())}
          />
          <button
            className="res-lib-upload-submit"
            onClick={() => taskId.trim() && startPolling(taskId.trim())}
            disabled={!taskId.trim() || polling}
            type="button"
          >
            {polling ? "查询中..." : "查询状态"}
          </button>
        </div>
      )}
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
                {r.resource_type === "video" && (
                  <img className="res-lib-bili-pic" src={`/api/v1/video/thumbnail/${r.resource_id}`} alt="" loading="lazy" onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
                )}
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
                    {a.is_correct ? "正确" : "错误"}
                  </span>
                  {a.score != null && <span className="res-lib-kp">{a.score}分</span>}
                </div>
                <div className="res-lib-card-title">
                  {typeof a.user_answer === "string" ? a.user_answer : JSON.stringify(a.user_answer)}
                </div>
                <div className="res-lib-card-meta">
                  {a.grading_method} · {a.time_spent_seconds ? `${a.time_spent_seconds}秒` : ""}
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
              {selectedResource.resource_type === "video" && selectedResource.resource_id ? (
                <video controls style={{ width: "100%", maxHeight: 400 }} src={`/api/v1/video/file/${selectedResource.resource_id}`} />
              ) : (
                <ResourceRenderer resource={selectedResource} />
              )}
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
    </div>
  );
}
