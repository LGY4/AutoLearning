import { Modal, Select } from "antd";
import type { BaseAgentProfile } from "../../types/baseline";

interface Props {
  open: boolean;
  onClose: () => void;
  agents: BaseAgentProfile[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function SelectAgentModal({ open, onClose, agents, selectedId, onSelect }: Props) {
  return (
    <Modal title="选择智能体" open={open} onCancel={onClose} onOk={onClose} okButtonProps={{ htmlType: "button" }} keyboard={false} destroyOnClose>
      <Select
        value={selectedId}
        onChange={onSelect}
        options={agents.map((item) => ({ label: item.is_system ? `${item.name}（系统）` : item.name, value: item.agent_id }))}
        style={{ width: "100%" }}
        placeholder="选择一个基座智能体"
      />
    </Modal>
  );
}
