CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS app_user (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    real_name VARCHAR(64),
    role VARCHAR(32) NOT NULL CHECK (role IN ('student', 'teacher', 'admin')),
    email VARCHAR(128),
    phone VARCHAR(32),
    status VARCHAR(32) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS base_agent (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES app_user(id),
    name VARCHAR(128) NOT NULL,
    description TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    applies_to JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_provider VARCHAR(64) NOT NULL DEFAULT 'spark',
    output_style VARCHAR(64) NOT NULL DEFAULT 'structured',
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS student_profile (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES app_user(id),
    profile_json JSONB NOT NULL,
    profile_version INT DEFAULT 1,
    completeness_score NUMERIC(5, 2),
    confidence_score NUMERIC(5, 2),
    updated_by VARCHAR(64),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS student_profile_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES student_profile(id),
    feature_name VARCHAR(128) NOT NULL,
    old_value JSONB,
    new_value JSONB,
    change_reason TEXT,
    source_type VARCHAR(64) CHECK (source_type IN ('dialogue', 'answer', 'click', 'progress', 'agent')),
    source_id UUID,
    confidence_score NUMERIC(5, 2),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS learning_goal (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES app_user(id),
    goal_title VARCHAR(255) NOT NULL,
    goal_description TEXT,
    target_course_id UUID,
    target_level VARCHAR(64),
    deadline DATE,
    status VARCHAR(32) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS course (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_name VARCHAR(128) NOT NULL,
    subject VARCHAR(128),
    description TEXT,
    difficulty_level VARCHAR(32),
    created_by UUID REFERENCES app_user(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chapter (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES course(id),
    chapter_name VARCHAR(128) NOT NULL,
    chapter_order INT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS knowledge_point (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID REFERENCES chapter(id),
    name VARCHAR(128) NOT NULL,
    description TEXT,
    prerequisite_ids JSONB,
    difficulty_level VARCHAR(32),
    tags JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS learning_resource (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES app_user(id),
    knowledge_point_id UUID REFERENCES knowledge_point(id),
    title VARCHAR(255) NOT NULL,
    resource_type VARCHAR(64) NOT NULL CHECK (
        resource_type IN ('document', 'mindmap', 'quiz', 'reading', 'video', 'animation', 'code_case')
    ),
    content_summary TEXT,
    difficulty_level VARCHAR(32),
    target_profile JSONB,
    status VARCHAR(32) DEFAULT 'draft',
    current_version INT DEFAULT 1,
    generated_by_agent_id UUID,
    quality_score NUMERIC(5, 2),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS resource_version (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_id UUID NOT NULL REFERENCES learning_resource(id),
    version_no INT NOT NULL,
    content TEXT,
    content_url TEXT,
    prompt_used TEXT,
    model_name VARCHAR(128),
    generation_params JSONB,
    change_reason TEXT,
    status VARCHAR(32) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(resource_id, version_no)
);

CREATE TABLE IF NOT EXISTS media_asset (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_id UUID REFERENCES learning_resource(id),
    media_type VARCHAR(64) CHECK (
        media_type IN ('image', 'video', 'audio', 'mindmap', 'pdf', 'markdown', 'code_file')
    ),
    file_name VARCHAR(255),
    file_url TEXT NOT NULL,
    storage_provider VARCHAR(64),
    file_size BIGINT,
    mime_type VARCHAR(128),
    checksum VARCHAR(128),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS question (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    knowledge_point VARCHAR(255) NOT NULL DEFAULT '',
    question_type VARCHAR(64) CHECK (
        question_type IN ('choice', 'blank', 'programming', 'case_analysis', 'short_answer')
    ),
    stem TEXT NOT NULL,
    options JSONB,
    answer JSONB,
    explanation TEXT,
    difficulty_level VARCHAR(32) DEFAULT 'medium',
    subject VARCHAR(128) DEFAULT '',
    tags JSONB DEFAULT '[]',
    status VARCHAR(32) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS answer_record (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES app_user(id),
    question_id UUID NOT NULL REFERENCES question(id),
    user_answer JSONB NOT NULL,
    is_correct BOOLEAN,
    score NUMERIC(5, 2),
    grading_method VARCHAR(32) DEFAULT 'exact',
    grading_detail JSONB,
    time_spent_seconds INT,
    submitted_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_graph (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    graph_id VARCHAR(128) UNIQUE NOT NULL,
    course_id VARCHAR(128) NOT NULL,
    course_name VARCHAR(255) NOT NULL,
    version INT NOT NULL DEFAULT 1,
    review_status VARCHAR(32) NOT NULL DEFAULT 'draft',
    graph_json JSONB NOT NULL,
    node_count INT DEFAULT 0,
    edge_count INT DEFAULT 0,
    confidence NUMERIC(5, 2),
    generated_by VARCHAR(64) DEFAULT 'graph_builder_agent',
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_knowledge_graph_course ON knowledge_graph(course_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_graph_status ON knowledge_graph(review_status);
CREATE INDEX IF NOT EXISTS idx_knowledge_graph_graph_id ON knowledge_graph(graph_id);

CREATE TABLE IF NOT EXISTS learning_path (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES app_user(id),
    goal_id UUID REFERENCES learning_goal(id),
    title VARCHAR(255),
    path_version INT DEFAULT 1,
    strategy JSONB,
    status VARCHAR(32) DEFAULT 'active',
    generated_by_agent_id UUID,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS learning_path_node (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    path_id UUID NOT NULL REFERENCES learning_path(id),
    knowledge_point_id UUID REFERENCES knowledge_point(id),
    resource_id UUID REFERENCES learning_resource(id),
    node_order INT NOT NULL,
    expected_duration_minutes INT,
    node_status VARCHAR(32) DEFAULT 'locked',
    unlock_condition JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS learning_record (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES app_user(id),
    path_id UUID REFERENCES learning_path(id),
    resource_id UUID REFERENCES learning_resource(id),
    score INT,
    duration_seconds INT DEFAULT 0,
    wrong_points JSONB,
    feedback TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_workflow (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES app_user(id),
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    current_agent VARCHAR(64),
    input_payload JSONB,
    output_payload JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_task (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID REFERENCES agent_workflow(id),
    task_type VARCHAR(64) NOT NULL,
    agent_name VARCHAR(128) NOT NULL,
    user_id UUID REFERENCES app_user(id),
    input_payload JSONB,
    output_payload JSONB,
    status VARCHAR(32) DEFAULT 'pending' CHECK (
        status IN ('pending', 'running', 'success', 'failed', 'retrying', 'cancelled', 'timeout')
    ),
    progress INT DEFAULT 0,
    error_message TEXT,
    retry_count INT DEFAULT 0,
    parent_task_id UUID,
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    finished_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_event_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES agent_workflow(id),
    task_id UUID REFERENCES agent_task(id),
    from_agent VARCHAR(128),
    to_agent VARCHAR(128),
    action VARCHAR(128),
    input_snapshot JSONB,
    output_snapshot JSONB,
    status VARCHAR(32),
    progress INT DEFAULT 0,
    duration_ms INT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recommendation_record (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES app_user(id),
    resource_id UUID REFERENCES learning_resource(id),
    path_id UUID REFERENCES learning_path(id),
    recommend_reason JSONB,
    profile_snapshot JSONB,
    score NUMERIC(5, 2),
    status VARCHAR(32) DEFAULT 'pushed',
    clicked BOOLEAN DEFAULT FALSE,
    completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS embedding_index (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_type VARCHAR(64) NOT NULL,
    business_id UUID NOT NULL,
    collection_name VARCHAR(128) NOT NULL,
    embedding_id VARCHAR(128) NOT NULL,
    text_hash VARCHAR(128) NOT NULL,
    embedding_model VARCHAR(128),
    vector_status VARCHAR(32) DEFAULT 'active',
    version_no INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(business_type, business_id, version_no)
);

CREATE TABLE IF NOT EXISTS prompt_template (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(128) NOT NULL,
    agent_name VARCHAR(64) NOT NULL,
    version VARCHAR(32) NOT NULL,
    template TEXT NOT NULL,
    variables JSONB,
    status VARCHAR(32) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    actor_type VARCHAR(64) CHECK (actor_type IN ('user', 'agent', 'admin', 'system')),
    action VARCHAR(128),
    target_table VARCHAR(128),
    target_id UUID,
    before_data JSONB,
    after_data JSONB,
    ip_address VARCHAR(64),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversation_session (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES app_user(id),
    title VARCHAR(255) NOT NULL DEFAULT '学习画像会话',
    profile_id UUID REFERENCES student_profile(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversation_message (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES conversation_session(id),
    user_id UUID NOT NULL REFERENCES app_user(id),
    role VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    intent VARCHAR(64) DEFAULT 'learning',
    metadata_json JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversation_session_user ON conversation_session(user_id);
CREATE INDEX IF NOT EXISTS idx_conversation_message_session ON conversation_message(session_id);

CREATE INDEX IF NOT EXISTS idx_student_profile_user_id ON student_profile(user_id);
CREATE INDEX IF NOT EXISTS idx_profile_json_gin ON student_profile USING GIN (profile_json);
CREATE INDEX IF NOT EXISTS idx_resource_type_status ON learning_resource(resource_type, status);
CREATE INDEX IF NOT EXISTS idx_agent_task_status ON agent_task(status);
CREATE INDEX IF NOT EXISTS idx_agent_event_workflow ON agent_event_log(workflow_id, created_at);
CREATE INDEX IF NOT EXISTS idx_recommend_user_created ON recommendation_record(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_embedding_business ON embedding_index(business_type, business_id);
