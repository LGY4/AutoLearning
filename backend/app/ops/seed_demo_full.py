"""Full demo data seeder — creates realistic profile, conversations, resources for demo mode."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def seed_full_demo_data(user_id: str) -> dict:
    """Create a complete demo data set for a user. Returns summary dict."""
    from app.core.config import get_settings
    settings = get_settings()
    if settings.repository_backend != "postgres":
        return {"seeded": False, "reason": "not using postgres backend"}

    from app.db.session import SessionLocal
    from app.db.models import (
        StudentProfileModel, ConversationSessionModel, ConversationMessageModel,
        LearningPathModel, LearningPathNodeModel, LearningResourceModel,
    )
    from sqlalchemy import select

    with SessionLocal() as db:
        results = {}

        # Check if already has meaningful data (completeness > 0.3 means real data)
        from sqlalchemy import func
        existing = db.scalar(
            select(StudentProfileModel.completeness_score)
            .where(StudentProfileModel.user_id == user_id)
            .order_by(StudentProfileModel.completeness_score.desc())
            .limit(1)
        )
        if existing and existing > 0.3:
            return {"seeded": False, "reason": "user already has data", "completeness": existing}

        now = datetime.now(timezone.utc)

        # ── Profile ───────────────────────────────────────────────────
        profile_json = {
            "profile_id": "00000000-0000-0000-0000-000000000001",
            "user_id": user_id,
            "version": 1,
            "completeness_score": 0.72,
            "confidence_score": 0.85,
            "basic_info": {"major": "计算机科学", "grade": "大三", "school": "软件杯大学"},
            "knowledge_profile": {
                "overall_level": "intermediate",
                "known_topics": ["数组", "链表", "栈", "队列", "二叉树", "哈希表"],
                "weak_topics": ["动态规划", "图算法", "并发编程"],
                "mastery_level": {"数据结构": 0.75, "算法设计": 0.60, "系统设计": 0.40},
                "topic_dimensions": {
                    "数据结构": {"mastery": "high", "application": "mid", "memory": "high", "understanding": "mid"},
                    "算法设计": {"mastery": "mid", "application": "low", "memory": "mid", "understanding": "mid"},
                    "图算法": {"mastery": "low", "application": "low", "memory": "low", "understanding": "low"},
                },
            },
            "learning_goal": {"current_goal": "系统掌握数据结构与算法", "target_course": "数据结构", "target_level": "project_practice", "deadline": "2026-06-30"},
            "learning_preference": {"learning_style": "visual", "resource_preference": {"document": 0.8, "video": 0.6, "quiz": 0.5}, "difficulty_preference": "step_by_step"},
            "learning_behavior": {"average_study_minutes": 45, "active_period": "evening", "completion_rate": 0.65, "recent_scores": [85, 72, 90, 78], "last_knowledge_point": "二叉树遍历"},
            "cognitive_profile": {"cognitive_style": "visual", "abstract_understanding": "high", "hands_on_ability": "medium", "reading_patience": "medium"},
            "dynamic_update": {"last_updated_at": now.isoformat(), "update_source": "demo_seed", "update_reason": "Demo data initialization"},
        }

        profile = StudentProfileModel(
            user_id=user_id,
            profile_json=profile_json,
            profile_version=1,
            completeness_score=0.72,
            confidence_score=0.85,
            created_at=now,
            updated_at=now,
        )
        db.add(profile)
        results["profile"] = True

        # ── Learning Path ──────────────────────────────────────────────
        path = LearningPathModel(
            user_id=user_id,
            title="数据结构与算法学习路径",
            strategy={"algorithm": "topological", "personalized": True},
            status="active",
            path_version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(path)
        db.flush()

        nodes_data = [
            ("栈的基本概念", 1, "available", 30),
            ("队列与栈的对比", 2, "available", 25),
            ("链表操作", 3, "locked", 35),
            ("二叉树遍历", 4, "locked", 40),
            ("哈希表原理", 5, "locked", 30),
        ]
        for name, order, status, mins in nodes_data:
            db.add(LearningPathNodeModel(
                path_id=path.id,
                node_order=order,
                node_status=status,
                expected_duration_minutes=mins,
                unlock_condition={"previous_completed": True} if status == "locked" else None,
                created_at=now,
            ))
        results["path"] = {"nodes": len(nodes_data)}

        # ── Conversation ───────────────────────────────────────────────
        conv = ConversationSessionModel(
            user_id=user_id,
            title="学习数据结构基础",
            conversation_type="learning",
            profile_id=profile.id,
            created_at=now,
            updated_at=now,
        )
        db.add(conv)
        db.flush()

        messages = [
            {"role": "user", "content": "什么是栈？", "intent": "tutor_question"},
            {"role": "assistant", "content": "栈是一种后进先出的线性数据结构，只能在一端进行插入和删除操作……", "intent": "tutor_answer"},
            {"role": "user", "content": "栈和队列有什么区别？", "intent": "tutor_question"},
            {"role": "assistant", "content": "栈是后进先出，队列是先进先出。栈像一叠盘子，队列像排队……", "intent": "tutor_answer"},
            {"role": "user", "content": "给我生成一份关于栈的学习文档", "intent": "resource_generation"},
            {"role": "assistant", "content": "好的，我已经为你生成了7种学习资源……", "intent": "resource_result"},
        ]
        for i, msg in enumerate(messages):
            db.add(ConversationMessageModel(
                session_id=conv.id,
                user_id=user_id,
                role=msg["role"],
                content=msg["content"],
                intent=msg["intent"],
            ))
        results["conversation"] = {"messages": len(messages)}

        # ── Resources ──────────────────────────────────────────────────
        resources_data = [
            ("栈的学习文档", "document", "# 栈 学习指南\n\n栈是一种后进先出的线性数据结构……", "栈"),
            ("栈思维导图", "mindmap", "# 栈 思维导图\n\n- 栈\n  - 基本概念\n  - 实现方式\n  - 应用场景", "栈"),
            ("栈练习题", "quiz", '{"title":"栈 练习题","questions":[{"type":"choice","stem":"栈的特点是？","options":["A. FIFO","B. LIFO","C. FILO","D. LILO"],"answer":"B. LIFO"}]}', "栈"),
            ("栈与队列对比", "reading", "# 栈与队列 拓展阅读\n\n深入对比两种数据结构……", "栈"),
        ]
        for title, rtype, content, kp in resources_data:
            db.add(LearningResourceModel(
                user_id=user_id,
                title=title,
                resource_type=rtype,
                content_summary=content[:200],
                status="generated",
                quality_score=0.85,
                created_at=now,
                updated_at=now,
            ))
        results["resources"] = len(resources_data)

        db.commit()
        logger.info("Demo data seeded successfully: %s", json.dumps(results, ensure_ascii=False))
        return {"seeded": True, "results": results}
