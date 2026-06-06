import { Dropdown } from "antd";
import {
  Bot,
  FileVideo,
  Image,
  Settings,
  Users,
} from "lucide-react";
import { Plus } from "lucide-react";

interface Props {
  onSelect: (key: string) => void;
}

const MENU_ITEMS = [
  { key: "upload-image", label: "上传图片", icon: <Image size={14} /> },
  { key: "media-studio", label: "多媒体工作室", icon: <FileVideo size={14} /> },
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
