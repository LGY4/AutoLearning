interface LearningActionNode {
  knowledge_point: string;
  status?: string;
  order?: number;
  estimated_minutes?: number;
}

interface LearningActionProfile {
  knowledge_profile: {
    weak_topics?: string[];
  };
  learning_goal: {
    current_goal?: string;
  };
}

interface LearningActionRecommendation {
  title: string;
  score: number;
}

interface LearningActionPath {
  nodes: LearningActionNode[];
}

export interface LearningPathProgress {
  total: number;
  completed: number;
  percent: number;
  nextNode: LearningActionNode | null;
  summary: string;
  nextLabel: string;
}

export interface NextLearningAction {
  kind: "path" | "practice" | "resource" | "plan" | "chat";
  label: string;
  title: string;
  description: string;
  cta: string;
  to: string;
}

function byOrder(a: LearningActionNode, b: LearningActionNode) {
  return (a.order ?? 0) - (b.order ?? 0);
}

function topicPath(path: string, param: string, topic: string) {
  return `${path}?${param}=${encodeURIComponent(topic)}`;
}

export function getLearningPathProgress(path: LearningActionPath): LearningPathProgress {
  const nodes = [...(path.nodes ?? [])].sort(byOrder);
  const total = nodes.length;
  const completed = nodes.filter((node) => node.status === "completed").length;
  const nextNode =
    nodes.find((node) => node.status === "learning") ??
    nodes.find((node) => node.status === "available") ??
    nodes.find((node) => !["completed", "skipped", "locked"].includes(node.status ?? "")) ??
    null;
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0;

  return {
    total,
    completed,
    percent,
    nextNode,
    summary: total > 0 ? `${completed}/${total} 已完成` : "暂无路径",
    nextLabel: nextNode ? `下一节点：${nextNode.knowledge_point}` : total > 0 ? "路径暂无可学习节点" : "先生成学习路径",
  };
}

export function buildNextLearningActions(input: {
  profile: LearningActionProfile;
  learningPath: LearningActionPath;
  recommendations: LearningActionRecommendation[];
}): NextLearningAction[] {
  const actions: NextLearningAction[] = [];
  const progress = getLearningPathProgress(input.learningPath);

  if (progress.nextNode) {
    const step = progress.nextNode.order != null ? `第 ${progress.nextNode.order + 1} 步` : "学习路径";
    const minutes = progress.nextNode.estimated_minutes ? ` · 预计 ${progress.nextNode.estimated_minutes} 分钟` : "";
    actions.push({
      kind: "path",
      label: progress.nextNode.status === "learning" ? "继续学习" : "下一步",
      title: progress.nextNode.knowledge_point,
      description: `${step}${minutes}`,
      cta: "进入学习",
      to: topicPath("/chat", "topic", progress.nextNode.knowledge_point),
    });
  }

  const weakTopic = input.profile.knowledge_profile.weak_topics?.find(Boolean);
  if (weakTopic) {
    actions.push({
      kind: "practice",
      label: "薄弱点强化",
      title: weakTopic,
      description: "用自适应练习巩固薄弱知识点。",
      cta: "开始练习",
      to: topicPath("/practice", "knowledge_point", weakTopic),
    });
  }

  const recommendation = input.recommendations[0];
  if (recommendation) {
    actions.push({
      kind: "resource",
      label: "推荐资源",
      title: recommendation.title,
      description: `匹配度 ${Math.round(recommendation.score * 100)}%，可先阅读再继续追问。`,
      cta: "查看推荐",
      to: topicPath("/chat", "topic", recommendation.title),
    });
  }

  if (actions.length === 0) {
    const goal = input.profile.learning_goal.current_goal?.trim();
    if (goal) {
      actions.push({
        kind: "plan",
        label: "路径规划",
        title: goal,
        description: "先把目标拆成可执行的学习路径和练习节奏。",
        cta: "生成路径",
        to: topicPath("/chat", "topic", `请为「${goal}」规划学习路径，并推荐下一步练习`),
      });
    } else {
      actions.push({
        kind: "chat",
        label: "开始学习",
        title: "创建新的学习目标",
        description: "输入目标后，系统会生成画像、路径、资源和练习。",
        cta: "进入工作区",
        to: "/chat",
      });
    }
  }

  return actions.slice(0, 3);
}
