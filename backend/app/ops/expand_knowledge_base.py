"""Expand knowledge base with additional subjects.

Adds chunks for: database, networking, OS, software engineering, ML,
distributed systems, system design, frontend, security.
Run: python -m app.ops.expand_knowledge_base
"""

import json
from pathlib import Path

KB_PATH = Path(__file__).resolve().parents[1] / "data" / "knowledge_base.json"

NEW_CHUNKS = [
    # ── Database (扩展) ──
    {"chunk_id": "db_sql_001", "title": "SQL 查询优化", "subject": "数据库", "content": "SQL 优化核心：使用 EXPLAIN 分析执行计划，关注全表扫描、索引失效、排序操作。优化策略：合理建索引、避免 SELECT *、减少子查询改用 JOIN、分页优化用游标替代 OFFSET。慢查询日志定位瓶颈。", "tags": ["SQL", "查询优化", "EXPLAIN", "慢查询"]},
    {"chunk_id": "db_sql_002", "title": "数据库连接池", "subject": "数据库", "content": "连接池复用数据库连接，避免频繁创建销毁的开销。核心参数：最小连接数、最大连接数、连接超时、空闲超时。常见实现：HikariCP(Java)、SQLAlchemy pool(Python)、pgbouncer(PostgreSQL)。连接泄漏检测：定期检查空闲连接有效性。", "tags": ["连接池", "HikariCP", "数据库连接", "性能优化"]},
    {"chunk_id": "db_nosql_001", "title": "NoSQL 数据库分类", "subject": "数据库", "content": "键值型(Redis、DynamoDB)：O(1)读写，适合缓存和会话。文档型(MongoDB、CouchDB)：灵活 schema，适合内容管理。列族型(Cassandra、HBase)：高写入吞吐，适合时序数据。图数据库(Neo4j)：关系查询高效，适合社交网络和推荐。CAP 定理：一致性、可用性、分区容错最多满足两个。", "tags": ["NoSQL", "Redis", "MongoDB", "CAP定理"]},
    {"chunk_id": "db_transaction_001", "title": "分布式事务", "subject": "数据库", "content": "分布式事务解决方案：2PC(两阶段提交)强一致但性能差。TCC(补偿事务)灵活但实现复杂。Saga 模式：每个操作有补偿操作，适合长事务。最终一致性：消息队列+重试，适合高并发场景。本地消息表：利用本地事务保证消息可靠发送。", "tags": ["分布式事务", "2PC", "TCC", "Saga", "最终一致性"]},

    # ── Computer Networking (扩展) ──
    {"chunk_id": "net_http_002", "title": "HTTP/2 与 HTTP/3", "subject": "计算机网络", "content": "HTTP/2：多路复用(一个连接并行多个请求)、头部压缩(HPACK)、服务器推送、二进制分帧。HTTP/3：基于 QUIC(UDP)，0-RTT 握手，连接迁移(网络切换不断连)，改进的丢包恢复。性能对比：HTTP/3 在高延迟和丢包环境优势明显。", "tags": ["HTTP/2", "HTTP/3", "QUIC", "多路复用"]},
    {"chunk_id": "net_rest_001", "title": "RESTful API 设计", "subject": "计算机网络", "content": "REST 核心原则：资源导向(URI 表示资源)、统一接口(GET/POST/PUT/DELETE)、无状态、可缓存。设计规范：名词复数表示集合(/users)、嵌套表示关系(/users/123/posts)、状态码语义(200成功/201创建/400客户端错误/500服务器错误)。版本控制：URL 路径(/v1/)或请求头。", "tags": ["REST", "API设计", "HTTP方法", "状态码"]},
    {"chunk_id": "net_websocket_001", "title": "WebSocket 与实时通信", "subject": "计算机网络", "content": "WebSocket 全双工通信协议，建立在 TCP 之上。握手阶段使用 HTTP Upgrade 头。持久连接，服务端可主动推送。应用：聊天室、实时通知、在线协作、股票行情。SSE(Server-Sent Events)：单向服务端推送，基于 HTTP，实现更简单。轮询 vs 长轮询 vs SSE vs WebSocket 选型。", "tags": ["WebSocket", "SSE", "实时通信", "全双工"]},
    {"chunk_id": "net_dns_001", "title": "DNS 解析与 CDN", "subject": "计算机网络", "content": "DNS 解析流程：浏览器缓存 → 系统缓存 → 本地 DNS → 根域名 → 顶级域名 → 权威域名。递归查询 vs 迭代查询。CDN 原理：将静态资源分发到边缘节点，用户就近访问。DNS 负载均衡：轮询、加权、地理位置。CNAME 记录用于 CDN 域名映射。", "tags": ["DNS", "CDN", "域名解析", "边缘节点"]},

    # ── Operating Systems (扩展) ──
    {"chunk_id": "os_process_002", "title": "进程间通信(IPC)", "subject": "操作系统", "content": "IPC 方式：管道(匿名管道父子进程、命名管道无亲缘关系)、消息队列、共享内存(最快但需同步)、信号量(计数器同步)、Socket(跨网络)。选择标准：数据量大用共享内存，跨机器用 Socket，简单场景用管道。线程同步：互斥锁、读写锁、条件变量、信号量。", "tags": ["IPC", "管道", "共享内存", "信号量", "线程同步"]},
    {"chunk_id": "os_memory_002", "title": "虚拟内存与页面置换", "subject": "操作系统", "content": "虚拟内存将物理内存抽象为连续地址空间。页表映射虚拟页到物理帧。缺页中断：访问不在内存的页触发页面调入。页面置换算法：FIFO(先进先出)、LRU(最近最少使用)、LFU(最不经常使用)、Clock(近似LRU)。抖动(thrashing)：频繁缺页导致性能崩溃。", "tags": ["虚拟内存", "页面置换", "LRU", "缺页中断", "抖动"]},
    {"chunk_id": "os_file_001", "title": "文件系统与 I/O", "subject": "操作系统", "content": "文件系统管理磁盘块分配：连续分配(快但碎片)、链式(无碎片但随机访问慢)、索引(综合优势)。inode 存储文件元数据。日志文件系统(ext4、NTFS)保证崩溃一致性。I/O 模型：阻塞、非阻塞、多路复用(select/poll/epoll)、异步(AIO)。epoll 边缘触发 vs 水平触发。", "tags": ["文件系统", "inode", "epoll", "I/O模型"]},
    {"chunk_id": "os_concurrent_001", "title": "并发与死锁", "subject": "操作系统", "content": "死锁四个必要条件：互斥、占有且等待、不可抢占、循环等待。预防：破坏任一条件。检测：资源分配图。避免：银行家算法。活锁：线程互相让步但无进展。饥饿：低优先级线程长期得不到资源。并发编程模型：共享内存(锁、原子操作) vs 消息传递(Actor、CSP)。", "tags": ["死锁", "并发", "银行家算法", "活锁", "Actor"]},

    # ── Software Engineering (扩展) ──
    {"chunk_id": "se_testing_001", "title": "软件测试策略", "subject": "软件工程", "content": "测试金字塔：单元测试(多、快、隔离) → 集成测试(中等数量、测试交互) → 端到端测试(少、慢、测试完整流程)。TDD：先写测试再写代码，红-绿-重构循环。Mock 与 Stub：隔离外部依赖。测试覆盖率：行覆盖、分支覆盖、路径覆盖。覆盖率高不等于质量高。", "tags": ["测试", "TDD", "单元测试", "测试金字塔", "Mock"]},
    {"chunk_id": "se_ci_cd_001", "title": "CI/CD 流水线", "subject": "软件工程", "content": "CI(持续集成)：代码提交自动构建+测试，快速发现集成问题。CD(持续交付)：自动部署到预发布环境。CD(持续部署)：自动部署到生产环境。工具链：GitHub Actions、GitLab CI、Jenkins、ArgoCD。流水线阶段：lint → build → test → deploy。制品管理：Docker 镜像、NPM 包。", "tags": ["CI/CD", "持续集成", "持续部署", "GitHub Actions", "Docker"]},
    {"chunk_id": "se_arch_001", "title": "微服务架构", "subject": "软件工程", "content": "微服务将单体应用拆分为独立服务。优势：独立部署、技术栈灵活、故障隔离。挑战：服务发现、负载均衡、分布式事务、链路追踪。通信方式：同步(REST/gRPC) vs 异步(消息队列)。API 网关：统一入口、认证、限流、熔断。服务网格(Istio)：透明代理处理服务间通信。", "tags": ["微服务", "API网关", "服务发现", "gRPC", "Istio"]},
    {"chunk_id": "se_security_001", "title": "Web 安全基础", "subject": "软件工程", "content": "XSS(跨站脚本)：注入恶意脚本到页面，防御：输入过滤+输出编码+CSP。CSRF(跨站请求伪造)：利用用户已登录状态发起请求，防御：CSRF Token+SameSite Cookie。SQL 注入：拼接SQL语句，防御：参数化查询+ORM。HTTPS：TLS 加密传输。JWT：无状态认证 Token，注意过期和刷新机制。", "tags": ["XSS", "CSRF", "SQL注入", "HTTPS", "JWT"]},

    # ── Machine Learning (扩展) ──
    {"chunk_id": "ml_dl_001", "title": "深度学习基础", "subject": "机器学习", "content": "神经网络：输入层→隐藏层→输出层，激活函数引入非线性(ReLU、Sigmoid、Tanh)。反向传播：链式法则计算梯度，梯度下降更新权重。CNN(卷积神经网络)：卷积层提取局部特征，池化层降维，适合图像。RNN/LSTM：处理序列数据，LSTM 用门控机制解决长程依赖。Transformer：自注意力机制，并行化训练。", "tags": ["深度学习", "神经网络", "CNN", "RNN", "Transformer"]},
    {"chunk_id": "ml_nlp_001", "title": "自然语言处理", "subject": "机器学习", "content": "文本表示：词袋模型、TF-IDF、词嵌入(Word2Vec、GloVe)、上下文嵌入(BERT、GPT)。预训练模型：BERT(双向编码，适合理解任务)、GPT(自回归，适合生成任务)。微调：在预训练模型上用任务数据微调。RAG：检索增强生成，结合知识库提升回答准确性。", "tags": ["NLP", "BERT", "GPT", "词嵌入", "RAG"]},
    {"chunk_id": "ml_llm_001", "title": "大语言模型(LLM)技术", "subject": "机器学习", "content": "LLM 核心技术：Transformer 架构、大规模预训练、指令微调、RLHF(人类反馈强化学习)。推理优化：KV Cache、量化(INT8/INT4)、投机解码、连续批处理。RAG 架构：文档分块→向量嵌入→检索→重排序→生成。Agent 框架：LLM+工具调用+规划+记忆。评估：MMLU、HumanEval、MT-Bench。", "tags": ["LLM", "RLHF", "KV Cache", "量化", "Agent"]},
    {"chunk_id": "ml_eval_002", "title": "模型评估与调优", "subject": "机器学习", "content": "分类指标：准确率、精确率、召回率、F1-Score、AUC-ROC。回归指标：MSE、RMSE、MAE、R²。过拟合解决：正则化(L1/L2)、Dropout、早停、数据增强。超参调优：网格搜索、随机搜索、贝叶斯优化。交叉验证：K折交叉验证、分层采样。偏差-方差权衡：高偏差欠拟合，高方差过拟合。", "tags": ["评估指标", "过拟合", "正则化", "交叉验证", "偏差方差"]},

    # ── Distributed Systems ──
    {"chunk_id": "dist_consensus_001", "title": "分布式一致性", "subject": "分布式系统", "content": "一致性模型：强一致(线性化)、顺序一致、最终一致。共识算法：Paxos(难实现)、Raft(可理解的日志复制)、ZAB(ZooKeeper)。CAP 定理：网络分区下 CP(一致性优先，如 HBase)或 AP(可用性优先，如 Cassandra)。BASE 理论：基本可用、软状态、最终一致性。", "tags": ["分布式一致性", "Raft", "Paxos", "CAP", "BASE"]},
    {"chunk_id": "dist_cache_001", "title": "分布式缓存", "subject": "分布式系统", "content": "Redis Cluster：数据分片(16384 槽)、主从复制、故障转移。缓存策略：Cache-Aside(先查缓存再查DB)、Read-Through/Write-Through(缓存层代理)、Write-Behind(异步写回)。缓存问题：缓存穿透(查不存在的key)→布隆过滤器、缓存雪崩(大量key同时过期)→随机过期时间、缓存击穿(热点key过期)→互斥锁。", "tags": ["Redis", "缓存策略", "缓存穿透", "缓存雪崩", "分布式缓存"]},
    {"chunk_id": "dist_mq_001", "title": "消息队列", "subject": "分布式系统", "content": "消息队列解耦、削峰、异步。Kafka：高吞吐，分区有序，适合日志和事件流。RabbitMQ：功能丰富，支持多种协议，适合任务队列。RocketMQ：事务消息，适合金融场景。保证消息可靠：生产者确认、持久化存储、消费者手动ACK、死信队列。消息顺序：分区有序(全局有序性能差)。", "tags": ["消息队列", "Kafka", "RabbitMQ", "消息可靠", "削峰"]},

    # ── System Design ──
    {"chunk_id": "sd_rate_001", "title": "限流与熔断", "subject": "系统设计", "content": "限流算法：固定窗口(简单但有边界突发)、滑动窗口(更平滑)、漏桶(恒定速率)、令牌桶(允许突发)。熔断器：关闭→开启(连续失败达阈值)→半开(试探恢复)。实现：Sentinel、Hystrix、Resilience4j。降级策略：返回缓存数据、默认值、简化功能。", "tags": ["限流", "熔断", "令牌桶", "Sentinel", "降级"]},
    {"chunk_id": "sd_design_001", "title": "高可用架构设计", "subject": "系统设计", "content": "高可用手段：冗余(多副本)、负载均衡(Nginx/HAProxy)、故障转移(主从切换)、健康检查(心跳检测)。数据库高可用：主从复制、读写分离、分库分表。服务高可用：无状态设计、水平扩容、优雅降级。监控告警：Prometheus+Grafana 指标监控、ELK 日志分析、链路追踪(Jaeger/Zipkin)。", "tags": ["高可用", "负载均衡", "主从复制", "监控", "Prometheus"]},

    # ── Frontend ──
    {"chunk_id": "fe_react_001", "title": "React 核心概念", "subject": "前端", "content": "React 核心：JSX 语法糖、组件化(函数组件+Hooks)、虚拟 DOM+Diff 算法、单向数据流。Hooks：useState(状态)、useEffect(副作用)、useMemo(缓存计算)、useCallback(缓存函数)、useRef(DOM引用)。状态管理：Context API(轻量)、Redux(复杂应用)、Zustand(简洁)。性能优化：React.memo、懒加载、虚拟列表。", "tags": ["React", "Hooks", "虚拟DOM", "状态管理", "性能优化"]},
    {"chunk_id": "fe_ts_001", "title": "TypeScript 类型系统", "subject": "前端", "content": "TypeScript 核心：基础类型(string/number/boolean)、接口(interface)、泛型(<T>)、联合类型(|)、交叉类型(&)、类型守卫(is/in)。高级类型：Partial(所有属性可选)、Pick/Omit(选择/排除属性)、Record(键值映射)、映射类型、条件类型。最佳实践：避免 any、用 unknown 替代、类型窄化、const assertions。", "tags": ["TypeScript", "泛型", "类型系统", "接口"]},
    {"chunk_id": "fe_perf_001", "title": "Web 性能优化", "subject": "前端", "content": "加载优化：代码分割(动态import)、Tree Shaking、资源压缩(gzip/brotli)、CDN 分发、预加载(preload/prefetch)。渲染优化：减少重排(reflow)、虚拟列表、图片懒加载、Web Worker 处理计算。网络优化：HTTP/2 多路复用、DNS 预解析、连接预建立。监控：Lighthouse、Core Web Vitals(LCP/FID/CLS)。", "tags": ["性能优化", "代码分割", "虚拟列表", "Core Web Vitals"]},
]


def expand_knowledge_base():
    """Add new chunks to knowledge_base.json."""
    with open(KB_PATH, "r", encoding="utf-8") as f:
        existing = json.load(f)

    existing_ids = {c["chunk_id"] for c in existing}
    new_chunks = [c for c in NEW_CHUNKS if c["chunk_id"] not in existing_ids]

    if not new_chunks:
        print("No new chunks to add.")
        return

    existing.extend(new_chunks)
    with open(KB_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"Added {len(new_chunks)} chunks. Total: {len(existing)}")

    # Count by subject
    subjects: dict[str, int] = {}
    for c in existing:
        s = c.get("subject", "未知")
        subjects[s] = subjects.get(s, 0) + 1
    for s, n in sorted(subjects.items(), key=lambda x: -x[1]):
        print(f"  {s}: {n}")


if __name__ == "__main__":
    expand_knowledge_base()
