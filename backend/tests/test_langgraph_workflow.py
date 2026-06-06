"""Tests for LangGraph runtime orchestration.

Covers:
1. Graph compilation
2. Intent routing (conditional edges)
3. Resource generation node
4. Assessment node
5. Fallback to serial on failure
6. Anti-hanging (timeout)
7. WorkflowState structure
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.core.enums import AgentName, AgentTaskStatus
# Force-import service submodules so unittest.mock.patch can find them
from app.services import agent_runtime, assess_agent, master_agent, model_gateway  # noqa: F401
from app.workflows.langgraph_runtime import (
    WorkflowState,
    build_langgraph_app,
    node_aggregate,
    node_assess_agent,
    node_exercise_agent,
    node_general_chat,
    node_master_agent,
    node_profile_agent,
    node_quality_agent,
    node_recommendation_agent,
    node_resource_planner,
    node_tutor_agent,
    route_after_master,
    route_after_path,
    route_after_profile,
    run_langgraph_workflow,
)
from app.workflows.learning_graph import run_fallback_workflow, run_workflow


# ── 1. Compilation ─────────────────────────────────────────────────────────


class TestCompilation:
    def test_graph_compiles(self):
        app = build_langgraph_app()
        if app is None:
            pytest.skip("LangGraph is not installed in this environment")
        assert app is not None

    def test_graph_has_all_nodes(self):
        # Mock the underlying services, then rebuild graph so it picks up mocks
        with patch("app.services.master_agent.detect_intent") as mock_detect:
            mock_detect.return_value = (MagicMock(value="general_chat"), 0.9, "keyword")
            with patch("app.services.model_gateway.generate_text", return_value="你好"):
                app = build_langgraph_app()
                if app is None:
                    pytest.skip("LangGraph is not installed in this environment")
                state = {
                    "user_id": str(uuid4()),
                    "message": "你好",
                    "workflow_id": str(uuid4()),
                    "errors": [],
                    "completed_steps": [],
                    "node_timings": {},
                    "tasks": [],
                    "events": [],
                }
                result = app.invoke(state, {"recursion_limit": 25})
                assert "completed_steps" in result
                assert "aggregate" in result["completed_steps"]


# ── 2. Intent Routing ──────────────────────────────────────────────────────


class TestIntentRouting:
    def _make_state(self, intent: str) -> WorkflowState:
        return {
            "user_id": str(uuid4()),
            "message": "test",
            "intent": intent,
            "workflow_id": str(uuid4()),
            "errors": [],
            "completed_steps": [],
            "node_timings": {},
            "tasks": [],
            "events": [],
        }

    def test_tutoring_routes_to_tutor(self):
        assert route_after_master(self._make_state("tutoring")) == "tutor_agent"

    def test_resource_gen_routes_to_profile(self):
        assert route_after_master(self._make_state("resource_generation")) == "profile_agent"

    def test_learning_path_routes_to_profile(self):
        assert route_after_master(self._make_state("learning_path")) == "profile_agent"

    def test_assessment_routes_to_assess(self):
        assert route_after_master(self._make_state("assessment")) == "assess_agent"

    def test_exercise_routes_to_exercise(self):
        assert route_after_master(self._make_state("exercise")) == "exercise_agent"

    def test_general_chat_routes_to_chat(self):
        assert route_after_master(self._make_state("general_chat")) == "general_chat"

    def test_unknown_intent_routes_to_chat(self):
        assert route_after_master(self._make_state("unknown_intent")) == "general_chat"

    def test_profile_routes_to_path(self):
        state = self._make_state("resource_generation")
        assert route_after_profile(state) == "path_agent"

    def test_path_routes_to_resource_for_resource_gen(self):
        state = self._make_state("resource_generation")
        assert route_after_path(state) == "resource_planner"

    def test_path_routes_to_aggregate_for_learning_path(self):
        state = self._make_state("learning_path")
        assert route_after_path(state) == "aggregate"


# ── 3. MasterAgent Node ────────────────────────────────────────────────────


class TestMasterAgentNode:
    @patch("app.services.master_agent.detect_intent")
    def test_detects_intent(self, mock_detect):
        mock_detect.return_value = (MagicMock(value="tutoring"), 0.95, "keyword")
        state: WorkflowState = {
            "user_id": str(uuid4()), "message": "什么是二叉树",
            "workflow_id": str(uuid4()), "errors": [], "completed_steps": [],
            "node_timings": {}, "tasks": [], "events": [],
        }
        result = node_master_agent(state)
        assert result["intent"] == "tutoring"
        assert result["intent_confidence"] == 0.95
        assert "master_agent" in result["completed_steps"]
        assert "master_agent" in result["node_timings"]

    @patch("app.services.master_agent.detect_intent")
    def test_fallback_on_error(self, mock_detect):
        mock_detect.side_effect = RuntimeError("LLM down")
        state: WorkflowState = {
            "user_id": str(uuid4()), "message": "test",
            "workflow_id": str(uuid4()), "errors": [], "completed_steps": [],
            "node_timings": {}, "tasks": [], "events": [],
        }
        result = node_master_agent(state)
        assert result["intent"] == "general_chat"
        assert len(result["errors"]) == 1
        assert result["errors"][0]["node"] == "master_agent"


# ── 4. Resource Generation Node ────────────────────────────────────────────


class TestResourceNode:
    def test_plans_resources(self):
        state: WorkflowState = {
            "user_id": str(uuid4()), "message": "学习数据结构",
            "subject": "数据结构", "knowledge_point": "二叉树",
            "resource_types": ["document"], "difficulty": "beginner",
            "workflow_id": str(uuid4()), "errors": [], "completed_steps": [],
            "node_timings": {}, "tasks": [], "events": [],
        }
        result = node_resource_planner(state)
        assert result["resource_plan"] == ["document"]
        assert "resource_planner" in result["completed_steps"]

    def test_plans_multiple_resource_types(self):
        state: WorkflowState = {
            "user_id": str(uuid4()), "message": "test",
            "subject": "test", "knowledge_point": "test",
            "resource_types": ["document", "quiz"], "difficulty": "beginner",
            "workflow_id": str(uuid4()), "errors": [], "completed_steps": [],
            "node_timings": {}, "tasks": [], "events": [],
        }
        result = node_resource_planner(state)
        assert result["resource_plan"] == ["document", "quiz"]
        assert "resource_planner" in result["completed_steps"]


# ── 5. Assessment Node ─────────────────────────────────────────────────────


class TestAssessNode:
    @patch("app.services.assess_agent")
    def test_returns_assessment(self, mock_assess):
        mock_assess.assess_learning.return_value = {
            "status": "ok", "mastery_score": 0.75, "summary": "good",
        }
        state: WorkflowState = {
            "user_id": str(uuid4()), "message": "test",
            "workflow_id": str(uuid4()), "errors": [], "completed_steps": [],
            "node_timings": {}, "tasks": [], "events": [],
        }
        result = node_assess_agent(state)
        assert result["assessment"]["status"] == "ok"
        assert "assess_agent" in result["completed_steps"]

    @patch("app.services.assess_agent")
    def test_degrades_on_error(self, mock_assess):
        mock_assess.assess_learning.side_effect = RuntimeError("DB down")
        state: WorkflowState = {
            "user_id": str(uuid4()), "message": "test",
            "workflow_id": str(uuid4()), "errors": [], "completed_steps": [],
            "node_timings": {}, "tasks": [], "events": [],
        }
        result = node_assess_agent(state)
        assert result["assessment"]["status"] == "failed"
        assert len(result["errors"]) == 1


# ── 6. Fallback Mechanism ──────────────────────────────────────────────────


class TestFallback:
    def test_run_workflow_falls_back_when_langgraph_unavailable(self):
        """If run_langgraph_workflow returns None, fallback to serial."""
        with patch("app.workflows.langgraph_runtime.run_langgraph_workflow", return_value=None):
            with patch("app.workflows.learning_graph.run_fallback_workflow") as mock_fb:
                mock_fb.return_value = ([], [])
                wf_id = uuid4()
                user_id = uuid4()
                run_workflow(wf_id, user_id, {"goal": "test"})
                mock_fb.assert_called_once()

    def test_run_workflow_uses_langgraph_when_available(self):
        """If run_langgraph_workflow returns valid result, don't call fallback."""
        mock_result = {
            "tasks": [],
            "events": [],
        }
        with patch("app.workflows.langgraph_runtime.run_langgraph_workflow", return_value=mock_result):
            with patch("app.workflows.learning_graph.run_fallback_workflow") as mock_fb:
                wf_id = uuid4()
                user_id = uuid4()
                run_workflow(wf_id, user_id, {"goal": "test"})
                mock_fb.assert_not_called()


# ── 7. Anti-hanging (Timeout) ──────────────────────────────────────────────


class TestAntiHanging:
    def test_timeout_returns_none(self):
        """LangGraph execution that exceeds timeout returns None."""
        with patch("app.workflows.langgraph_runtime._get_app") as mock_get:
            slow_app = MagicMock()

            def slow_invoke(state, config):
                time.sleep(2)
                return state

            slow_app.invoke = slow_invoke
            mock_get.return_value = slow_app

            result = run_langgraph_workflow(
                user_id=uuid4(),
                message="test",
                timeout_seconds=1,
            )
            assert result is None


# ── 8. WorkflowState Structure ─────────────────────────────────────────────


class TestWorkflowState:
    def test_has_all_required_fields(self):
        """WorkflowState should accept all documented fields."""
        state: WorkflowState = {
            "user_id": "test",
            "message": "test",
            "conversation_id": None,
            "base_agent_id": None,
            "resource_types": ["document"],
            "difficulty": "beginner",
            "subject": "test",
            "knowledge_point": "test",
            "intent": "tutoring",
            "intent_confidence": 0.9,
            "intent_method": "keyword",
            "profile": {},
            "learning_path": {},
            "generated_resources": [],
            "quality_report": {},
            "recommendations": [],
            "assessment": {},
            "tutor_answer": {},
            "exercise": {},
            "errors": [],
            "completed_steps": [],
            "node_timings": {},
            "workflow_id": "test",
            "tasks": [],
            "events": [],
        }
        assert state["intent"] == "tutoring"
        assert state["user_id"] == "test"


# ── 9. General Chat Node ───────────────────────────────────────────────────


class TestGeneralChatNode:
    @patch("app.services.model_gateway")
    def test_returns_reply(self, mock_gw):
        mock_gw.generate_text.return_value = "你好！"
        state: WorkflowState = {
            "user_id": str(uuid4()), "message": "你好",
            "workflow_id": str(uuid4()), "errors": [], "completed_steps": [],
            "node_timings": {}, "tasks": [], "events": [],
        }
        result = node_general_chat(state)
        assert "tutor_answer" in result
        assert "general_chat" in result["completed_steps"]

    @patch("app.services.model_gateway")
    def test_fallback_on_llm_error(self, mock_gw):
        mock_gw.generate_text.side_effect = RuntimeError("timeout")
        state: WorkflowState = {
            "user_id": str(uuid4()), "message": "你好",
            "workflow_id": str(uuid4()), "errors": [], "completed_steps": [],
            "node_timings": {}, "tasks": [], "events": [],
        }
        result = node_general_chat(state)
        assert "tutor_answer" in result
        assert result["tutor_answer"]["answer"]


# ── 10. Deep Merge ────────────────────────────────────────────────────────


class TestDeepMerge:
    def test_merge_dict_merges_nested_keys(self):
        from app.workflows.langgraph_runtime import _merge_dict
        old = {"a": 1, "b": {"c": 2, "d": 3}}
        new = {"b": {"c": 10}, "e": 5}
        result = _merge_dict(old, new)
        assert result == {"a": 1, "b": {"c": 10, "d": 3}, "e": 5}

    def test_merge_dict_overwrites_scalar(self):
        from app.workflows.langgraph_runtime import _merge_dict
        assert _merge_dict({"a": 1}, {"a": 2}) == {"a": 2}

    def test_merge_dict_empty_old(self):
        from app.workflows.langgraph_runtime import _merge_dict
        assert _merge_dict({}, {"a": 1}) == {"a": 1}

    def test_merge_dict_empty_new(self):
        from app.workflows.langgraph_runtime import _merge_dict
        assert _merge_dict({"a": 1}, {}) == {"a": 1}

    def test_merge_dict_deep_nesting(self):
        from app.workflows.langgraph_runtime import _merge_dict
        old = {"a": {"b": {"c": 1, "d": 2}}}
        new = {"a": {"b": {"c": 99}}}
        assert _merge_dict(old, new) == {"a": {"b": {"c": 99, "d": 2}}}


# ── 11. Reset App ─────────────────────────────────────────────────────────


class TestResetApp:
    def test_reset_clears_cache(self):
        from app.workflows.langgraph_runtime import _get_app, reset_langgraph_app
        app1 = _get_app()
        if app1 is None:
            pytest.skip("LangGraph is not installed in this environment")
        assert app1 is not None
        reset_langgraph_app()
        app2 = _get_app()
        assert app2 is not None
        reset_langgraph_app()  # cleanup


# ── 12. Emit Progress ─────────────────────────────────────────────────────


class TestEmitProgress:
    @patch("app.services.master_agent.detect_intent")
    def test_emit_progress_called_during_node(self, mock_detect):
        mock_detect.return_value = (MagicMock(value="general_chat"), 0.9, "keyword")
        from app.workflows.langgraph_runtime import _trace_ctx, node_master_agent
        events: list = []
        _trace_ctx.emit_progress = lambda e: events.append(e)
        try:
            state: WorkflowState = {
                "user_id": str(uuid4()), "message": "test",
                "workflow_id": str(uuid4()), "errors": [], "completed_steps": [],
                "node_timings": {}, "tasks": [], "events": [],
            }
            node_master_agent(state)
            assert len(events) == 2
            assert events[0]["status"] == "running"
            assert events[0]["stage"] == "langgraph_node"
            assert events[1]["status"] == "done"
            assert events[1]["node"] == "master_agent"
            assert events[1]["duration_ms"] >= 0
        finally:
            if hasattr(_trace_ctx, "emit_progress"):
                del _trace_ctx.emit_progress

    @patch("app.services.master_agent.detect_intent")
    def test_emit_progress_on_failure(self, mock_detect):
        mock_detect.side_effect = RuntimeError("LLM down")
        from app.workflows.langgraph_runtime import _trace_ctx, node_master_agent
        events: list = []
        _trace_ctx.emit_progress = lambda e: events.append(e)
        try:
            state: WorkflowState = {
                "user_id": str(uuid4()), "message": "test",
                "workflow_id": str(uuid4()), "errors": [], "completed_steps": [],
                "node_timings": {}, "tasks": [], "events": [],
            }
            node_master_agent(state)
            assert len(events) == 2
            assert events[0]["status"] == "running"
            assert events[1]["status"] == "failed"
            assert "LLM down" in events[1]["hint"]
        finally:
            if hasattr(_trace_ctx, "emit_progress"):
                del _trace_ctx.emit_progress

    def test_emit_trace_noop_without_callback(self):
        """_emit_trace should not raise when no callback is set."""
        from app.workflows.langgraph_runtime import _emit_trace
        # Should not raise
        _emit_trace({"test": True})
