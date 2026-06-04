import { useCallback, useEffect, useState } from "react";
import { BookOpen, Pencil, Plus, Save, Target, Trash2, X } from "lucide-react";
import { apiGet, apiPost, apiPatch, apiDelete } from "../api/client";
import { useAppContext } from "../context/AppContext";
import type { StudentProfile } from "../types/baseline";

interface Course {
  id: string;
  course_name: string;
  subject: string | null;
  description: string | null;
  difficulty_level: string | null;
  created_by: string | null;
  created_at: string | null;
}

interface Goal {
  id: string;
  goal_title: string;
  goal_description: string | null;
  target_course_id: string | null;
  target_level: string | null;
  deadline: string | null;
  status: string;
  created_at: string | null;
}

export function CoursePage() {
  const { state, dispatch } = useAppContext();
  const isAdmin = state.user?.role === "admin";

  const refreshProfile = useCallback(async () => {
    try {
      const profile = await apiGet<StudentProfile>("/profiles/me");
      dispatch({ type: "SET_PROFILE", payload: profile });
    } catch {
      // Best effort
    }
  }, [dispatch]);

  const [courses, setCourses] = useState<Course[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create course form
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ course_name: "", subject: "", description: "", difficulty_level: "" });
  // Edit course state
  const [editingCourseId, setEditingCourseId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ course_name: "", subject: "", description: "", difficulty_level: "" });

  // Create goal form
  const [showGoalForm, setShowGoalForm] = useState(false);
  const [goalForm, setGoalForm] = useState({ goal_title: "", goal_description: "", target_level: "", deadline: "" });
  // Edit goal state
  const [editingGoalId, setEditingGoalId] = useState<string | null>(null);
  const [editGoalForm, setEditGoalForm] = useState({ goal_title: "", goal_description: "", target_level: "", deadline: "", status: "" });

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [coursesRes, goalsRes] = await Promise.all([
        apiGet<{ courses: Course[] }>("/courses"),
        apiGet<{ goals: Goal[] }>("/courses/goals").catch(() => ({ goals: [] })),
      ]);
      setCourses(coursesRes.courses ?? []);
      setGoals(goalsRes.goals ?? []);
    } catch {
      setError("加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateCourse() {
    if (!form.course_name.trim()) return;
    try {
      await apiPost("/courses", form);
      setShowForm(false);
      setForm({ course_name: "", subject: "", description: "", difficulty_level: "" });
      loadData();
    } catch {
      setError("创建课程失败");
    }
  }

  async function handleDeleteCourse(id: string) {
    if (!window.confirm("确定删除该课程？")) return;
    try {
      await apiDelete(`/courses/${id}`);
      setCourses(courses.filter((c) => c.id !== id));
    } catch {
      setError("删除失败");
    }
  }

  function startEditCourse(c: Course) {
    setEditingCourseId(c.id);
    setEditForm({ course_name: c.course_name, subject: c.subject ?? "", description: c.description ?? "", difficulty_level: c.difficulty_level ?? "" });
  }

  async function handleSaveCourse() {
    if (!editingCourseId) return;
    try {
      const updated = await apiPatch<Course>(`/courses/${editingCourseId}`, editForm);
      setCourses(courses.map((c) => c.id === editingCourseId ? { ...c, ...updated } : c));
      setEditingCourseId(null);
    } catch {
      setError("保存失败");
    }
  }

  async function handleCreateGoal() {
    if (!goalForm.goal_title.trim()) return;
    try {
      await apiPost("/courses/goals", goalForm);
      setShowGoalForm(false);
      setGoalForm({ goal_title: "", goal_description: "", target_level: "", deadline: "" });
      await refreshProfile();
      loadData();
    } catch {
      setError("创建目标失败");
    }
  }

  async function handleDeleteGoal(id: string) {
    if (!window.confirm("确定删除该学习目标？")) return;
    try {
      await apiDelete(`/courses/goals/${id}`);
      setGoals(goals.filter((g) => g.id !== id));
      await refreshProfile();
    } catch {
      setError("删除失败");
    }
  }

  function startEditGoal(g: Goal) {
    setEditingGoalId(g.id);
    setEditGoalForm({ goal_title: g.goal_title, goal_description: g.goal_description ?? "", target_level: g.target_level ?? "", deadline: g.deadline ?? "", status: g.status });
  }

  async function handleSaveGoal() {
    if (!editingGoalId) return;
    try {
      const updated = await apiPatch<Goal>(`/courses/goals/${editingGoalId}`, editGoalForm);
      setGoals(goals.map((g) => g.id === editingGoalId ? { ...g, ...updated } : g));
      setEditingGoalId(null);
      await refreshProfile();
    } catch {
      setError("保存失败");
    }
  }

  if (loading) return <div className="page-loading">加载中...</div>;

  return (
    <div className="page-container">
      <div className="page-header">
        <h1><BookOpen size={24} /> 课程管理</h1>
        {isAdmin && (
          <button className="btn-primary" onClick={() => setShowForm(true)}>
            <Plus size={16} /> 新建课程
          </button>
        )}
      </div>

      {error && <div className="page-error">{error}</div>}

      {showForm && (
        <div className="form-card">
          <h3>新建课程</h3>
          <input placeholder="课程名称" value={form.course_name} onChange={(e) => setForm({ ...form, course_name: e.target.value })} />
          <input placeholder="学科" value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} />
          <input placeholder="难度 (beginner/intermediate/advanced)" value={form.difficulty_level} onChange={(e) => setForm({ ...form, difficulty_level: e.target.value })} />
          <textarea placeholder="描述" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <div className="form-actions">
            <button className="btn-primary" onClick={handleCreateCourse}>创建</button>
            <button className="btn-secondary" onClick={() => setShowForm(false)}>取消</button>
          </div>
        </div>
      )}

      <div className="card-grid">
        {courses.map((c) => (
          <div className="info-card" key={c.id}>
            {editingCourseId === c.id ? (
              <>
                <div className="info-card-header">
                  <input value={editForm.course_name} onChange={(e) => setEditForm({ ...editForm, course_name: e.target.value })} />
                </div>
                <input placeholder="学科" value={editForm.subject} onChange={(e) => setEditForm({ ...editForm, subject: e.target.value })} />
                <input placeholder="难度" value={editForm.difficulty_level} onChange={(e) => setEditForm({ ...editForm, difficulty_level: e.target.value })} />
                <textarea placeholder="描述" value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} rows={2} />
                <div className="form-actions">
                  <button className="btn-primary" onClick={handleSaveCourse}><Save size={14} /> 保存</button>
                  <button className="btn-secondary" onClick={() => setEditingCourseId(null)}><X size={14} /> 取消</button>
                </div>
              </>
            ) : (
              <>
                <div className="info-card-header">
                  <h3>{c.course_name}</h3>
                  {isAdmin && (
                    <div className="info-card-actions">
                      <button className="btn-icon" onClick={() => startEditCourse(c)} title="编辑">
                        <Pencil size={14} />
                      </button>
                      <button className="btn-icon danger" onClick={() => handleDeleteCourse(c.id)} title="删除">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  )}
                </div>
                {c.subject && <span className="tag">{c.subject}</span>}
                {c.difficulty_level && <span className="tag">{c.difficulty_level}</span>}
                {c.description && <p className="info-card-desc">{c.description}</p>}
              </>
            )}
          </div>
        ))}
        {courses.length === 0 && <div className="empty-state">暂无课程</div>}
      </div>

      <div className="page-header" style={{ marginTop: 32 }}>
        <h1><Target size={24} /> 学习目标</h1>
        <button className="btn-primary" onClick={() => setShowGoalForm(true)}>
          <Plus size={16} /> 新建目标
        </button>
      </div>

      {showGoalForm && (
        <div className="form-card">
          <h3>新建学习目标</h3>
          <input placeholder="目标标题" value={goalForm.goal_title} onChange={(e) => setGoalForm({ ...goalForm, goal_title: e.target.value })} />
          <input placeholder="目标水平" value={goalForm.target_level} onChange={(e) => setGoalForm({ ...goalForm, target_level: e.target.value })} />
          <input type="date" placeholder="截止日期" value={goalForm.deadline} onChange={(e) => setGoalForm({ ...goalForm, deadline: e.target.value })} />
          <textarea placeholder="描述" value={goalForm.goal_description} onChange={(e) => setGoalForm({ ...goalForm, goal_description: e.target.value })} />
          <div className="form-actions">
            <button className="btn-primary" onClick={handleCreateGoal}>创建</button>
            <button className="btn-secondary" onClick={() => setShowGoalForm(false)}>取消</button>
          </div>
        </div>
      )}

      <div className="card-grid">
        {goals.map((g) => (
          <div className="info-card" key={g.id}>
            {editingGoalId === g.id ? (
              <>
                <div className="info-card-header">
                  <input value={editGoalForm.goal_title} onChange={(e) => setEditGoalForm({ ...editGoalForm, goal_title: e.target.value })} />
                </div>
                <input placeholder="目标水平" value={editGoalForm.target_level} onChange={(e) => setEditGoalForm({ ...editGoalForm, target_level: e.target.value })} />
                <input type="date" value={editGoalForm.deadline} onChange={(e) => setEditGoalForm({ ...editGoalForm, deadline: e.target.value })} />
                <select value={editGoalForm.status} onChange={(e) => setEditGoalForm({ ...editGoalForm, status: e.target.value })}>
                  <option value="active">进行中</option>
                  <option value="completed">已完成</option>
                  <option value="paused">已暂停</option>
                </select>
                <textarea placeholder="描述" value={editGoalForm.goal_description} onChange={(e) => setEditGoalForm({ ...editGoalForm, goal_description: e.target.value })} rows={2} />
                <div className="form-actions">
                  <button className="btn-primary" onClick={handleSaveGoal}><Save size={14} /> 保存</button>
                  <button className="btn-secondary" onClick={() => setEditingGoalId(null)}><X size={14} /> 取消</button>
                </div>
              </>
            ) : (
              <>
                <div className="info-card-header">
                  <h3>{g.goal_title}</h3>
                  <div className="info-card-actions">
                    <button className="btn-icon" onClick={() => startEditGoal(g)} title="编辑">
                      <Pencil size={14} />
                    </button>
                    <button className="btn-icon danger" onClick={() => handleDeleteGoal(g.id)} title="删除">
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
                <span className={`tag ${g.status === "active" ? "success" : ""}`}>{g.status}</span>
                {g.target_level && <span className="tag">{g.target_level}</span>}
                {g.deadline && <span className="tag">截止: {g.deadline}</span>}
                {g.goal_description && <p className="info-card-desc">{g.goal_description}</p>}
              </>
            )}
          </div>
        ))}
        {goals.length === 0 && <div className="empty-state">暂无学习目标</div>}
      </div>
    </div>
  );
}
