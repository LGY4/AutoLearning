import { describe, expect, it } from "vitest";
import { buildNextLearningActions, getLearningPathProgress } from "./learningActions";

const profile = {
  knowledge_profile: { weak_topics: [] },
  learning_goal: { current_goal: "掌握数据结构" },
};

describe("getLearningPathProgress", () => {
  it("computes progress and picks the active learning node first", () => {
    const progress = getLearningPathProgress({
      nodes: [
        { knowledge_point: "数组", status: "completed", order: 0 },
        { knowledge_point: "链表", status: "available", order: 1 },
        { knowledge_point: "栈", status: "learning", order: 2 },
      ],
    });

    expect(progress.completed).toBe(1);
    expect(progress.total).toBe(3);
    expect(progress.percent).toBe(33);
    expect(progress.nextNode?.knowledge_point).toBe("栈");
  });

  it("returns an empty progress summary when there is no path", () => {
    const progress = getLearningPathProgress({ nodes: [] });

    expect(progress.summary).toBe("暂无路径");
    expect(progress.nextNode).toBeNull();
  });
});

describe("buildNextLearningActions", () => {
  it("prioritizes path, weak-topic practice, and recommendation actions", () => {
    const actions = buildNextLearningActions({
      profile: {
        ...profile,
        knowledge_profile: { weak_topics: ["递归"] },
      },
      learningPath: {
        nodes: [
          { knowledge_point: "数组", status: "completed", order: 0 },
          { knowledge_point: "链表", status: "available", order: 1, estimated_minutes: 20 },
        ],
      },
      recommendations: [{ title: "链表练习资源", score: 0.82 }],
    });

    expect(actions.map((action) => action.kind)).toEqual(["path", "practice", "resource"]);
    expect(actions[0].to).toBe("/chat?topic=%E9%93%BE%E8%A1%A8");
    expect(actions[1].to).toBe("/practice?knowledge_point=%E9%80%92%E5%BD%92");
  });

  it("falls back to planning from the current goal when no concrete action exists", () => {
    const actions = buildNextLearningActions({
      profile,
      learningPath: { nodes: [] },
      recommendations: [],
    });

    expect(actions).toHaveLength(1);
    expect(actions[0].kind).toBe("plan");
    expect(actions[0].title).toBe("掌握数据结构");
  });
});
