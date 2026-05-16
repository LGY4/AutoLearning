import { ChatPanel } from "../components/chat/ChatPanel";

interface Props {
  onAuth: () => void;
  onCreateAgent: () => void;
  onSelectAgent: () => void;
  onModelConfig?: () => void;
}

export function LearningPage({ onAuth, onCreateAgent, onSelectAgent, onModelConfig }: Props) {
  return (
    <div className="workspace-layout">
      <ChatPanel onAuth={onAuth} onCreateAgent={onCreateAgent} onSelectAgent={onSelectAgent} onModelConfig={onModelConfig} />
    </div>
  );
}
