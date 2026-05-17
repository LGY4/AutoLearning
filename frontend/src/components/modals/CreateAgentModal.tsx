import { useState } from "react";
import { Input, Modal, Select } from "antd";

const AGENT_OPTIONS = [
  { label: "画像构建", value: "profile_agent" },
  { label: "路径规划", value: "path_agent" },
  { label: "文档生成", value: "document_agent" },
  { label: "题库生成", value: "quiz_agent" },
  { label: "多模态资源", value: "mindmap_agent" },
  { label: "视频动画", value: "video_agent" },
  { label: "代码实操", value: "code_agent" },
  { label: "推荐排序", value: "recommendation_agent" },
  { label: "智能辅导", value: "tutor_agent" },
];

interface Props {
  open: boolean;
  onClose: () => void;
  onSubmit: (payload: { name: string; description: string; system_prompt: string; applies_to: string[] }) => void;
}

export function CreateAgentModal({ open, onClose, onSubmit }: Props) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [prompt, setPrompt] = useState("");
  const [appliesTo, setAppliesTo] = useState<string[]>(AGENT_OPTIONS.map((o) => o.value));

  const handleOk = () => {
    if (!name.trim() || !description.trim() || !prompt.trim()) return;
    onSubmit({ name: name.trim(), description: description.trim(), system_prompt: prompt.trim(), applies_to: appliesTo });
    setName("");
    setDescription("");
    setPrompt("");
  };

  return (
    <Modal title="自定义基座智能体" open={open} onCancel={onClose} onOk={handleOk} okButtonProps={{ htmlType: "button" }} keyboard={false} destroyOnClose>
      <div className="agent-form">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="智能体名称" />
        <Input.TextArea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="智能体描述" />
        <Input.TextArea rows={5} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="系统提示词" />
        <Select
          mode="multiple"
          value={appliesTo}
          onChange={setAppliesTo}
          options={AGENT_OPTIONS as unknown as Array<{ label: string; value: string }>}
          placeholder="适用角色"
        />
      </div>
    </Modal>
  );
}

export { AGENT_OPTIONS };
