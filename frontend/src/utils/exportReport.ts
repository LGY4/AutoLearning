import type { StudentProfile, LearningPath, LearningResource } from "../types/baseline";

export function exportLearningReport(
  profile: StudentProfile | null,
  path: LearningPath | null,
  resources: LearningResource[]
): void {
  const kp = profile?.knowledge_profile;
  const pref = profile?.learning_preference;
  const goal = profile?.learning_goal;

  const lines = [
    `# AutoLearning 学习报告`,
    `> 导出时间: ${new Date().toLocaleString("zh-CN")}`,
    ``,
    `## 📊 学习画像`,
    ``,
    `- **整体水平**: ${kp?.overall_level || "未评估"}`,
    `- **学习风格**: ${pref?.learning_style || "—"}`,
    `- **完整度**: ${profile?.completeness_score ? `${Math.round(profile.completeness_score)}%` : "—"}`,
    `- **当前目标**: ${goal?.current_goal || "—"}`,
    ``,
    `### 四维度评估`,
    ``,
  ];

  if (kp?.topic_dimensions) {
    Object.entries(kp.topic_dimensions).forEach(([topic, dims]) => {
      lines.push(`#### ${topic}`);
      lines.push(`| 掌握 | 应用 | 记忆 | 理解 |`);
      lines.push(`|------|------|------|------|`);
      lines.push(`| ${(dims as Record<string,string>).mastery} | ${(dims as Record<string,string>).application} | ${(dims as Record<string,string>).memory} | ${(dims as Record<string,string>).understanding} |`);
      lines.push(``);
    });
  }

  if (kp?.weak_topics?.length) {
    lines.push(`### 薄弱知识点`);
    kp.weak_topics.forEach((t: string) => lines.push(`- ⚠️ ${t}`));
    lines.push(``);
  }

  lines.push(`## 🗺️ 学习路径`);
  lines.push(``);
  if (path?.nodes?.length) {
    path.nodes.forEach((n) => {
      const icon = n.status === "completed" ? "✅" : n.status === "learning" ? "🔄" : "⬜";
      lines.push(`${icon} **${n.knowledge_point}** (${n.estimated_minutes}分钟)`);
    });
  } else {
    lines.push(`暂无学习路径数据`);
  }
  lines.push(``);

  lines.push(`## 📚 学习资源 (${resources.length})`);
  lines.push(``);
  resources.slice(0, 20).forEach((r) => {
    const typeIcons: Record<string, string> = {
      document: "📄", mindmap: "🧠", quiz: "📝", code_case: "💻",
      video: "🎬", reading: "📖", flowchart: "🔷", animation: "🎞️",
    };
    lines.push(`- ${typeIcons[r.resource_type] || "📌"} **${r.title}** [${r.resource_type}] ${r.knowledge_point ? `· ${r.knowledge_point}` : ""}`);
  });
  lines.push(``);

  lines.push(`---`);
  lines.push(`*由 AutoLearning 自动生成*`);

  const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `autolearning-report-${new Date().toISOString().slice(0, 10)}.md`;
  a.click();
  URL.revokeObjectURL(url);
}
