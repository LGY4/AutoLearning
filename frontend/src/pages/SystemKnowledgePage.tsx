import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle, Database, ExternalLink, RefreshCw, Search, ShieldCheck } from "lucide-react";
import { apiGet, apiPost } from "../api/client";
import { Spinner } from "../components/common/Spinner";

interface GovernanceMetrics {
  chunk_count: number;
  subject_count: number;
  source_count: number;
  hash_coverage: number;
}

interface GovernanceReport {
  passed: boolean;
  failures: string[];
  manifest_version: string;
  schema_version: string;
  policy: Record<string, string>;
  allowed_sources: SourcePolicy[];
  metrics: GovernanceMetrics;
  breakdown: Record<string, Record<string, number>>;
  sample_chunks: KnowledgeChunkSummary[];
}

interface SourcePolicy {
  source_name: string;
  source_type: string;
  url_prefixes: string[];
  license: string;
  authority_level: string;
  update_frequency: string;
}

interface KnowledgeChunkSummary {
  chunk_id: string;
  title: string;
  subject: string;
  content_preview: string;
  tags: string[];
  source_name: string;
  source_url: string;
  source_type: string;
  license: string;
  authority_level: string;
  review_status: string;
  content_hash: string;
}

interface KnowledgeSearchResult extends KnowledgeChunkSummary {
  content: string;
  score: number;
  retrieval_engine: string;
  source: string;
}

interface SearchResponse {
  query: string;
  subject: string | null;
  results: KnowledgeSearchResult[];
}

interface ValidateResponse {
  passed: boolean;
  failures: string[];
}

const SOURCE_LABELS: Record<string, string> = {
  official_documentation: "官方文档",
  official_repository: "官方仓库",
  open_textbook: "开放教材",
  curated_seed: "种子知识",
};

const AUTHORITY_LABELS: Record<string, string> = {
  official: "官方",
  open_textbook: "开放教材",
  curated_seed: "维护种子",
};

function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function label(value: string, labels: Record<string, string>): string {
  return labels[value] || value || "未标记";
}

function topBreakdown(items: Record<string, number> | undefined): Array<[string, number]> {
  return Object.entries(items || {}).sort((a, b) => b[1] - a[1]).slice(0, 6);
}

function SourceLink({ url, children }: { url: string; children: string }) {
  if (!url) return <span>{children}</span>;
  return (
    <a href={url} target="_blank" rel="noreferrer" className="kb-link">
      <span>{children}</span>
      <ExternalLink size={13} />
    </a>
  );
}

function ChunkCard({ chunk }: { chunk: KnowledgeChunkSummary }) {
  return (
    <article className="kb-chunk">
      <div className="kb-chunk-head">
        <div>
          <strong>{chunk.title}</strong>
          <span>{chunk.chunk_id} · {chunk.subject}</span>
        </div>
        <span className={`kb-badge ${chunk.review_status === "approved" ? "ok" : ""}`}>
          {chunk.review_status || "unknown"}
        </span>
      </div>
      <p>{chunk.content_preview}</p>
      <div className="kb-tags">
        {chunk.tags.slice(0, 6).map((tag) => <span key={tag}>{tag}</span>)}
      </div>
      <div className="kb-source-line">
        <SourceLink url={chunk.source_url}>{chunk.source_name}</SourceLink>
        <span>{label(chunk.source_type, SOURCE_LABELS)}</span>
        <span>{label(chunk.authority_level, AUTHORITY_LABELS)}</span>
        <span>{chunk.license}</span>
      </div>
    </article>
  );
}

export function SystemKnowledgePage() {
  const [report, setReport] = useState<GovernanceReport | null>(null);
  const [chunks, setChunks] = useState<KnowledgeChunkSummary[]>([]);
  const [searchResults, setSearchResults] = useState<KnowledgeSearchResult[]>([]);
  const [query, setQuery] = useState("栈");
  const [chunkQuery, setChunkQuery] = useState("");
  const [subject, setSubject] = useState("");
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validation, setValidation] = useState<ValidateResponse | null>(null);

  const subjects = useMemo(() => topBreakdown(report?.breakdown.subjects).map(([name]) => name).filter(Boolean), [report]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "30" });
      if (chunkQuery.trim()) params.set("q", chunkQuery.trim());
      if (subject.trim()) params.set("subject", subject.trim());
      const [governance, chunkList] = await Promise.all([
        apiGet<GovernanceReport>("/knowledge/governance"),
        apiGet<KnowledgeChunkSummary[]>(`/knowledge/chunks?${params}`),
      ]);
      setReport(governance);
      setChunks(chunkList);
      setValidation({ passed: governance.passed, failures: governance.failures });
    } catch (err) {
      setError(err instanceof Error ? err.message : "知识库加载失败");
    } finally {
      setLoading(false);
    }
  }, [chunkQuery, subject]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const runValidation = async () => {
    setValidating(true);
    setError(null);
    try {
      const result = await apiGet<ValidateResponse>("/knowledge/validate");
      setValidation(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "知识库校验失败");
    } finally {
      setValidating(false);
    }
  };

  const runSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    try {
      const result = await apiPost<SearchResponse>("/knowledge/search", {
        query: query.trim(),
        subject: subject.trim() || null,
        top_k: 5,
      });
      setSearchResults(result.results || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "RAG 检索失败");
    } finally {
      setSearching(false);
    }
  };

  if (loading && !report) {
    return <div className="kb-page kb-loading"><Spinner /></div>;
  }

  return (
    <div className="kb-page">
      <header className="kb-header">
        <div>
          <h1><ShieldCheck size={24} /> 系统知识库</h1>
          <p>治理状态、可信来源、知识片段和 RAG 检索验证集中在这里。</p>
        </div>
        <button className="kb-icon-btn" onClick={() => void loadData()} type="button" title="刷新">
          <RefreshCw size={17} />
          <span>刷新</span>
        </button>
      </header>

      {error && <div className="kb-error">{error}</div>}

      <section className="kb-status">
        <div className={`kb-health ${validation?.passed ? "ok" : "bad"}`}>
          {validation?.passed ? <CheckCircle size={22} /> : <AlertTriangle size={22} />}
          <div>
            <strong>{validation?.passed ? "治理校验通过" : "治理校验失败"}</strong>
            <span>Manifest {report?.manifest_version || "-"} · Schema {report?.schema_version || "-"}</span>
          </div>
          <button className="kb-secondary-btn" onClick={runValidation} disabled={validating} type="button">
            {validating ? "校验中..." : "重新校验"}
          </button>
        </div>

        <div className="kb-metrics">
          <div><strong>{report?.metrics.chunk_count ?? 0}</strong><span>知识片段</span></div>
          <div><strong>{report?.metrics.subject_count ?? 0}</strong><span>学科主题</span></div>
          <div><strong>{report?.metrics.source_count ?? 0}</strong><span>可信来源</span></div>
          <div><strong>{pct(report?.metrics.hash_coverage ?? 0)}</strong><span>哈希覆盖</span></div>
        </div>
      </section>

      {validation && validation.failures.length > 0 && (
        <section className="kb-section">
          <h2>治理问题</h2>
          <div className="kb-failures">
            {validation.failures.map((failure) => <span key={failure}>{failure}</span>)}
          </div>
        </section>
      )}

      <section className="kb-section">
        <h2>治理策略</h2>
        <div className="kb-policy-grid">
          {Object.entries(report?.policy || {}).map(([key, value]) => (
            <div key={key} className="kb-policy-item">
              <span>{key}</span>
              <p>{value}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="kb-section">
        <h2>来源白名单</h2>
        <div className="kb-source-list">
          {(report?.allowed_sources || []).map((source) => (
            <article key={source.source_name} className="kb-source">
              <div>
                <strong>{source.source_name}</strong>
                <span>{label(source.source_type, SOURCE_LABELS)} · {label(source.authority_level, AUTHORITY_LABELS)}</span>
              </div>
              <div className="kb-source-meta">
                <span>{source.license}</span>
                <span>{source.update_frequency}</span>
                {source.url_prefixes.slice(0, 2).map((url) => (
                  <SourceLink key={url} url={url}>{url}</SourceLink>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="kb-section">
        <h2>RAG 检索验证</h2>
        <div className="kb-search-row">
          <div className="kb-field">
            <label>查询</label>
            <input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && void runSearch()} />
          </div>
          <div className="kb-field compact">
            <label>主题</label>
            <select value={subject} onChange={(e) => setSubject(e.target.value)}>
              <option value="">全部</option>
              {subjects.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </div>
          <button className="kb-primary-btn" onClick={runSearch} disabled={searching || !query.trim()} type="button">
            <Search size={16} />
            <span>{searching ? "检索中..." : "检索"}</span>
          </button>
        </div>
        <div className="kb-results">
          {searchResults.length === 0 ? (
            <p className="kb-empty">输入查询后可查看 RAG 返回来源、分数和治理字段。</p>
          ) : (
            searchResults.map((item) => (
              <article key={`${item.chunk_id}-${item.retrieval_engine}`} className="kb-result">
                <div className="kb-result-top">
                  <strong>{item.title}</strong>
                  <span>{item.retrieval_engine} · {Math.round((item.score || 0) * 100)}%</span>
                </div>
                <p>{item.content || item.content_preview}</p>
                <div className="kb-source-line">
                  <SourceLink url={item.source_url}>{item.source_name}</SourceLink>
                  <span>{item.review_status}</span>
                  <span>{label(item.authority_level, AUTHORITY_LABELS)}</span>
                </div>
              </article>
            ))
          )}
        </div>
      </section>

      <section className="kb-section">
        <h2><Database size={17} /> 知识片段</h2>
        <div className="kb-search-row">
          <div className="kb-field">
            <label>过滤</label>
            <input value={chunkQuery} onChange={(e) => setChunkQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && void loadData()} />
          </div>
          <button className="kb-secondary-btn" onClick={() => void loadData()} type="button">筛选</button>
        </div>
        <div className="kb-chunk-list">
          {chunks.length === 0 ? <p className="kb-empty">暂无匹配知识片段。</p> : chunks.map((chunk) => <ChunkCard key={chunk.chunk_id} chunk={chunk} />)}
        </div>
      </section>
    </div>
  );
}
