import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PracticePanel, LearningMapPanel, DashboardPanel, ResourceBrowsePanel } from "./InlinePanels";

// Mock API
vi.mock("../../../api/client", () => ({
  apiGet: vi.fn().mockResolvedValue({}),
  apiPost: vi.fn().mockResolvedValue({}),
}));

vi.mock("../../../hooks/useTaskPolling", () => ({
  useTaskPolling: () => ({ taskStatus: null, polling: false, startPolling: vi.fn(), stopPolling: vi.fn() }),
}));

describe("PracticePanel", () => {
  it("shows error when result has error", () => {
    render(<PracticePanel result={{ error: "生成失败" }} />);
    expect(screen.getByText("生成失败")).toBeInTheDocument();
  });

  it("shows empty state when no questions", () => {
    render(<PracticePanel result={{ questions: [], knowledge_point: "排序" }} />);
    expect(screen.getByText(/暂无题目/)).toBeInTheDocument();
  });

  it("renders questions when provided", () => {
    const questions = [
      { question: "什么是快速排序?", options: ["A. 排序算法", "B. 搜索算法", "C. 图算法", "D. 动态规划"], answer: "A. 排序算法" },
    ];
    render(<PracticePanel result={{ questions, knowledge_point: "快速排序" }} />);
    expect(screen.getByText(/1\. 什么是快速排序/)).toBeInTheDocument();
    expect(screen.getByText("提交答案")).toBeInTheDocument();
  });

  it("shows progress counter", () => {
    const questions = [
      { question: "Q1?", options: ["A", "B"], answer: "A" },
      { question: "Q2?", options: ["A", "B"], answer: "B" },
    ];
    render(<PracticePanel result={{ questions, knowledge_point: "test" }} />);
    expect(screen.getByText(/进度: 0\/2/)).toBeInTheDocument();
  });
});

describe("LearningMapPanel", () => {
  it("shows error when result has error", () => {
    render(<LearningMapPanel result={{ error: "加载失败" }} />);
    expect(screen.getByText("加载失败")).toBeInTheDocument();
  });

  it("shows empty state when no nodes", () => {
    render(<LearningMapPanel result={{ nodes: [], edges: [] }} />);
    expect(screen.getByText(/知识图谱为空/)).toBeInTheDocument();
  });

  it("renders nodes grouped by level", () => {
    const nodes = [
      { id: "1", name: "链表", level: 0, status: "completed" },
      { id: "2", name: "树", level: 1, status: "available" },
    ];
    render(<LearningMapPanel result={{ nodes, edges: [] }} />);
    expect(screen.getByText(/链表/)).toBeInTheDocument();
    expect(screen.getByText(/树/)).toBeInTheDocument();
    expect(screen.getByText(/2 节点/)).toBeInTheDocument();
  });
});

describe("DashboardPanel", () => {
  it("shows empty state when no profile", () => {
    render(<DashboardPanel result={{}} />);
    expect(screen.getByText(/暂无学习数据/)).toBeInTheDocument();
  });

  it("renders profile with goal", () => {
    const profile = {
      learning_goal: { current_goal: "掌握数据结构", target_course: "数据结构" },
      knowledge_profile: { overall_level: "intermediate", topic_dimensions: {}, weak_topics: [] },
    };
    render(<DashboardPanel result={{ profile, recommendations: [] }} />);
    expect(screen.getByText("掌握数据结构")).toBeInTheDocument();
    expect(screen.getByText("中级")).toBeInTheDocument();
  });

  it("renders weak topics", () => {
    const profile = {
      learning_goal: { current_goal: "" },
      knowledge_profile: { overall_level: "beginner", topic_dimensions: {}, weak_topics: ["图", "堆"] },
    };
    render(<DashboardPanel result={{ profile, recommendations: [] }} />);
    expect(screen.getByText("薄弱知识点")).toBeInTheDocument();
    expect(screen.getByText("图")).toBeInTheDocument();
    expect(screen.getByText("堆")).toBeInTheDocument();
  });
});

describe("ResourceBrowsePanel", () => {
  it("shows empty state when no resources", () => {
    render(<ResourceBrowsePanel result={{ resources: [], total: 0 }} />);
    expect(screen.getByText(/暂无资源/)).toBeInTheDocument();
  });

  it("renders resource cards", () => {
    const resources = [
      { resource_id: "1", title: "快速排序文档", resource_type: "document", knowledge_point: "排序" },
      { resource_id: "2", title: "排序练习", resource_type: "quiz", knowledge_point: "排序" },
    ];
    render(<ResourceBrowsePanel result={{ resources, total: 2 }} />);
    expect(screen.getByText("快速排序文档")).toBeInTheDocument();
    expect(screen.getByText("排序练习")).toBeInTheDocument();
    expect(screen.getByText(/2 份/)).toBeInTheDocument();
  });
});
