/**
 * AutoLearning 软件杯比赛演示完整流程
 *
 * 演示路径:
 * 1. 首页 → 注册 → 入学诊断
 * 2. 学习工作区 → 追问式对话 → 情感识别
 * 3. 学习流程 → 画像→路径→7种资源→推荐
 * 4. 苏格拉底辩论模式
 * 5. 教师看板
 */

import { expect, test } from "@playwright/test";

test.describe("Competition Demo Flow", () => {

  test("Full demo: register → onboard → learn → debate → dashboard", async ({ page }) => {
    // ── Step 1: Home page ──────────────────────────────────────
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "AutoLearning" })).toBeVisible();
    await expect(page.getByText("AI 驱动的自适应学习系统")).toBeVisible();

    // Auth modal opens automatically
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await page.getByText("没有账号，去注册").click();

    // Register
    await page.getByPlaceholder("用户名").fill("demo_player");
    await page.getByPlaceholder("密码").fill("demo123456");
    await page.getByRole("button", { name: /OK|登录|注册/ }).last().click();
    await page.waitForTimeout(2000);

    // ── Step 2: Onboard diagnostic ──────────────────────────────
    await expect(page.getByText(/欢迎|入学诊断/).first()).toBeVisible({ timeout: 5000 });

    // Fill onboarding form
    const majorInput = page.getByPlaceholder("专业");
    const gradeInput = page.getByPlaceholder("年级");
    const goalInput = page.getByPlaceholder(/目标|学习目标/);

    if (await majorInput.isVisible()) await majorInput.fill("计算机科学");
    if (await gradeInput.isVisible()) await gradeInput.fill("大三");
    if (await goalInput.isVisible()) await goalInput.fill("掌握数据结构与算法");

    // Start diagnostic
    const startBtn = page.getByRole("button", { name: /开始诊断|开始评测/ });
    if (await startBtn.isVisible()) await startBtn.click();
    await page.waitForTimeout(3000);

    // ── Step 3: Navigate to chat workspace ──────────────────────
    await page.getByRole("button", { name: "学习工作区" }).click();
    await expect(page).toHaveURL(/\/chat/);
    await page.waitForTimeout(1000);

    // Verify workspace layout
    await expect(page.locator(".chat-panel")).toBeVisible();
    await expect(page.locator(".floating-learning-input")).toBeVisible();
    await expect(page.locator(".resource-panel-group")).toBeVisible();

    // ── Step 4: Show proactive follow-up ────────────────────────
    // Type "我是学计算机的" to trigger follow-up question
    const inputField = page.locator(".floating-learning-input input, .chat-input-main input").first();
    await inputField.fill("我是学计算机的");
    await page.keyboard.press("Enter");
    await page.waitForTimeout(3000);
    // Should get a follow-up response
    await expect(page.getByText(/方向|后端|前端|算法/)).toBeVisible({ timeout: 5000 });

    // ── Step 5: Trigger emotion detection ───────────────────────
    await inputField.fill("太难了，学不会递归算法");
    await page.keyboard.press("Enter");
    await page.waitForTimeout(3000);
    // Should trigger frustrated emotion card
    await expect(page.locator(".emotion-card")).toBeVisible({ timeout: 5000 });

    // ── Step 6: Resource generation ──────────────────────────────
    await inputField.fill("给我生成一份关于栈的学习文档");
    await page.keyboard.press("Enter");
    await page.waitForTimeout(4000);
    // Should get resource cards
    await expect(page.locator(".chat-resource-card")).toBeVisible({ timeout: 10000 });

    // ── Step 7: Switch to debate mode ────────────────────────────
    await page.getByRole("button", { name: "苏格拉底" }).click();
    await page.waitForTimeout(2000);
    // Debate panel should appear
    await expect(page.locator(".debate-panel")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText(/学霸|杠精/)).toBeVisible();

    // Close debate
    await page.locator(".debate-close").click();
    await page.waitForTimeout(500);

    // ── Step 8: Teacher dashboard ────────────────────────────────
    await page.getByRole("button", { name: "教师看板" }).click();
    await expect(page).toHaveURL(/\/teacher/);
    await page.waitForTimeout(2000);
    await expect(page.getByText("教师看板")).toBeVisible();
    await expect(page.getByText(/名学生/)).toBeVisible();
    await expect(page.locator(".dashboard-card")).toBeVisible();

    // ── Step 9: Knowledge graph ──────────────────────────────────
    await page.getByRole("button", { name: "图谱管理" }).click();
    await expect(page).toHaveURL(/\/graphs/);
    await page.waitForTimeout(3000);
    await expect(page.getByText("知识图谱管理")).toBeVisible();

    // ── Step 10: Practice mode ───────────────────────────────────
    await page.getByRole("button", { name: "练习模式" }).click();
    await expect(page).toHaveURL(/\/practice/);
    await page.waitForTimeout(1000);
    await expect(page.getByText(/练习模式|题库管理/)).toBeVisible();

    console.log("✅ Competition demo flow completed successfully!");
  });

});
