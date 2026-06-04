import { useCallback, useRef, useState } from "react";
import { Button, Input, Modal } from "antd";
import type { InputRef } from "antd";

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

  const refs = {
    username: useRef<InputRef>(null),
    password: useRef<InputRef>(null),
    realName: useRef<InputRef>(null),
    major: useRef<InputRef>(null),
    grade: useRef<InputRef>(null),
    school: useRef<InputRef>(null),
  };

  const handleOk = useCallback(() => {
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
  }, [username, password, realName, major, grade, school, mode, onSubmit]);

  const handleKeyDown = useCallback(
    (current: keyof typeof refs, e: React.KeyboardEvent) => {
      if (e.key !== "Enter") return;
      e.preventDefault();

      const order: (keyof typeof refs)[] =
        mode === "login"
          ? ["username", "password"]
          : ["username", "password", "realName", "major", "grade", "school"];

      const idx = order.indexOf(current);
      const val = current === "password" ? password : current === "username" ? username : current === "realName" ? realName : current === "major" ? major : current === "grade" ? grade : school;

      // If current field is empty, do nothing
      if (!val.trim()) return;

      // Find next empty field
      for (let i = idx + 1; i < order.length; i++) {
        const key = order[i];
        const nextVal = key === "password" ? password : key === "username" ? username : key === "realName" ? realName : key === "major" ? major : key === "grade" ? grade : school;
        if (!nextVal.trim()) {
          refs[key].current?.focus();
          return;
        }
      }

      // All fields filled → submit
      handleOk();
    },
    [mode, username, password, realName, major, grade, school, handleOk],
  );

  return (
    <Modal title={mode === "login" ? "用户登录" : "用户注册"} open={open} onCancel={onClose} onOk={handleOk} okButtonProps={{ htmlType: "button" }} keyboard={false} destroyOnClose>
      <div className="agent-form">
        {(error || localError) && <div className="auth-error">{error || localError}</div>}
        <Input ref={refs.username} value={username} onChange={(e) => setUsername(e.target.value)} onKeyDown={(e) => handleKeyDown("username", e)} placeholder="用户名" autoComplete="username" />
        <Input.Password ref={refs.password} value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => handleKeyDown("password", e)} placeholder="密码" autoComplete={mode === "login" ? "current-password" : "new-password"} />
        {mode === "register" && (
          <>
            <Input ref={refs.realName} value={realName} onChange={(e) => setRealName(e.target.value)} onKeyDown={(e) => handleKeyDown("realName", e)} placeholder="姓名" />
            <Input ref={refs.major} value={major} onChange={(e) => setMajor(e.target.value)} onKeyDown={(e) => handleKeyDown("major", e)} placeholder="专业" />
            <Input ref={refs.grade} value={grade} onChange={(e) => setGrade(e.target.value)} onKeyDown={(e) => handleKeyDown("grade", e)} placeholder="年级" />
            <Input ref={refs.school} value={school} onChange={(e) => setSchool(e.target.value)} onKeyDown={(e) => handleKeyDown("school", e)} placeholder="学校" />
          </>
        )}
        <Button type="link" onClick={() => { setMode((c) => (c === "login" ? "register" : "login")); setLocalError(null); }}>
          {mode === "login" ? "没有账号，去注册" : "已有账号，去登录"}
        </Button>
      </div>
    </Modal>
  );
}
