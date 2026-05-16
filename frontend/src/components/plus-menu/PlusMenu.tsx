import { Dropdown } from "antd";
import {
  BookOpen,
  Bot,
  Cpu,
  FileText,
  GitBranch,
  LayoutDashboard,
  MessageSquare,
  Plus,
  Settings,
  SquareCode,
  Users,
  Video,
} from "lucide-react";

interface Props {
  onSelect: (key: string) => void;
}

const MENU_ITEMS = [
  { key: "add-document", label: "文档资源", icon: <FileText size={14} /> },
  { key: "add-reading", label: "阅读材料", icon: <BookOpen size={14} /> },
  { key: "add-quiz", label: "题目资源", icon: <MessageSquare size={14} /> },
  { key: "add-code", label: "代码实操", icon: <SquareCode size={14} /> },
  { key: "add-mindmap", label: "思维导图", icon: <LayoutDashboard size={14} /> },
  { key: "add-video", label: "视频动画", icon: <Video size={14} /> },
  { key: "add-flowchart", label: "流程图", icon: <GitBranch size={14} /> },
  { type: "divider" as const },
  { key: "custom-agent", label: "自定义智能体", icon: <Bot size={14} /> },
  { key: "select-agent", label: "选择智能体", icon: <Users size={14} /> },
  { type: "divider" as const },
  { key: "model-config", label: "模型配置", icon: <Settings size={14} /> },
];

export function PlusMenu({ onSelect }: Props) {
  return (
    <Dropdown
      trigger={["click"]}
      menu={{
        items: MENU_ITEMS.map((item) =>
          item.type === "divider"
            ? { type: "divider" as const }
            : { key: item.key, label: <span style={{ display: "flex", alignItems: "center", gap: 8 }}>{item.icon}{item.label}</span> }
        ),
        onClick: ({ key }) => onSelect(key),
      }}
    >
      <button className="floating-plus" type="button" title="更多">
        <Plus size={22} />
      </button>
    </Dropdown>
  );
}
