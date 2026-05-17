import { useState } from "react";
import { Button, Input, Modal } from "antd";

interface Props {
  open: boolean;
  onClose: () => void;
  onSubmit: (payload: {
    username: string;
    password: string;
    real_name?: string;
    major?: string;
    grade?: string;
    school?: string;
    isLogin: boolean;
  }) => void;
  error?: string | null;
}

export function AuthModal({ open, onClose, onSubmit, error }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [realName, setRealName] = useState("");
  const [major, setMajor] = useState("");
  const [grade, setGrade] = useState("");
  const [school, setSchool] = useState("");

  const [localError, setLocalError] = useState<string | null>(null);

  const handleOk = () => {
    setLocalError(null);
    if (!username.trim() || !password.trim()) return;
    if (mode === "register" && password.trim().length < 6) {
      setLocalError("密码至少 6 个字符");
      return;
    }
    onSubmit({
      username: username.trim(),
      password: password.trim(),
      real_name: realName.trim() || undefined,
      major: major.trim() || undefined,
      grade: grade.trim() || undefined,
      school: school.trim() || undefined,
      isLogin: mode === "login",
    });
  };

  return (
    <Modal title={mode === "login" ? "用户登录" : "用户注册"} open={open} onCancel={onClose} onOk={handleOk} okButtonProps={{ htmlType: "button" }} keyboard={false} destroyOnClose>
      <div className="agent-form">
        {(error || localError) && <div className="auth-error">{error || localError}</div>}
        <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="用户名" autoComplete="username" />
        <Input.Password value={password} onChange={(e) => setPassword(e.target.value)} placeholder="密码" autoComplete={mode === "login" ? "current-password" : "new-password"} />
        {mode === "register" && (
          <>
            <Input value={realName} onChange={(e) => setRealName(e.target.value)} placeholder="姓名" />
            <Input value={major} onChange={(e) => setMajor(e.target.value)} placeholder="专业" />
            <Input value={grade} onChange={(e) => setGrade(e.target.value)} placeholder="年级" />
            <Input value={school} onChange={(e) => setSchool(e.target.value)} placeholder="学校" />
          </>
        )}
        <Button type="link" onClick={() => { setMode((c) => (c === "login" ? "register" : "login")); setLocalError(null); }}>
          {mode === "login" ? "没有账号，去注册" : "已有账号，去登录"}
        </Button>
      </div>
    </Modal>
  );
}
