import { useState, useEffect } from "react";
import { ChevronRight, ChevronLeft, Check, MessageSquare, Brain, Target } from "lucide-react";

const STEPS = [
  {
    title: "欢迎来到 AutoLearning",
    description: "AI 驱动的自适应学习系统，为你构建个性化学习路径。",
    icon: Brain,
    hint: "点击下方按钮开始你的学习之旅",
  },
  {
    title: "智能对话学习",
    description: "在左侧「学习工作区」输入任何问题或学习目标，AI 将自动识别你的意图并给出针对性辅导。",
    icon: MessageSquare,
    hint: '试试输入「我是学计算机的」，看看 AI 如何追问',
  },
  {
    title: "六维画像 + 多资源生成",
    description: "每次学习后系统自动更新你的知识画像，并生成文档、导图、题库、代码等 7 种学习资源。",
    icon: Target,
    hint: "所有资源在右侧面板随时可查看",
  },
];

export function OnboardingTour() {
  const [step, setStep] = useState(-1);

  useEffect(() => {
    const seen = localStorage.getItem("onboarding_seen");
    if (!seen) setStep(0);
  }, []);

  const finish = () => {
    localStorage.setItem("onboarding_seen", "true");
    setStep(-1);
  };

  if (step < 0) return null;

  const current = STEPS[step];
  const Icon = current.icon;
  const isLast = step === STEPS.length - 1;

  return (
    <div className="onboarding-overlay" onClick={finish}>
      <div className="onboarding-card" onClick={(e) => e.stopPropagation()}>
        <div className="onboarding-card-icon">
          <Icon size={32} color="#6366f1" />
        </div>
        <h2 className="onboarding-card-title">{current.title}</h2>
        <p className="onboarding-card-desc">{current.description}</p>
        <p className="onboarding-card-hint">{current.hint}</p>
        <div className="onboarding-card-progress">
          {STEPS.map((_, i) => (
            <div key={i} className={`onboarding-dot ${i === step ? "active" : i < step ? "done" : ""}`} />
          ))}
        </div>
        <div className="onboarding-card-actions">
          {step > 0 && (
            <button className="btn-secondary btn-sm" onClick={() => setStep(step - 1)}>
              <ChevronLeft size={16} /> 上一步
            </button>
          )}
          {isLast ? (
            <button className="btn-primary" onClick={finish}>
              <Check size={16} /> 开始学习
            </button>
          ) : (
            <button className="btn-primary" onClick={() => setStep(step + 1)}>
              下一步 <ChevronRight size={16} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
