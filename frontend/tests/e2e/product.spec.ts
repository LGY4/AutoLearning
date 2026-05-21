import { expect, type Page, test } from "@playwright/test";

async function collectErrors(page: Page): Promise<string[]> {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().includes("404") && !message.text().includes("500")) {
      errors.push(message.text());
    }
  });
  return errors;
}

test("home page renders with hero content", async ({ page }) => {
  const errors = await collectErrors(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "AutoLearning" })).toBeVisible();
  await expect(page.getByText("AI 驱动的自适应学习系统")).toBeVisible();
  await expect(page.getByRole("button", { name: "开始学习" })).toBeVisible();
  // Auth modal should appear since user is not logged in
  await expect(page.getByRole("dialog")).toBeVisible();
  expect(errors).toEqual([]);
});

test("sidebar navigation renders all sections", async ({ page }) => {
  await page.goto("/");
  const sidebar = page.locator(".profile-sidebar");
  await expect(sidebar).toBeVisible();
  await expect(sidebar.getByText("AutoLearning")).toBeVisible();
  await expect(sidebar.getByRole("button", { name: "新对话" })).toBeVisible();
  await expect(sidebar.getByRole("button", { name: "学习工作区" })).toBeVisible();
  await expect(sidebar.getByRole("button", { name: "资源库" })).toBeVisible();
});

test("chat page shows workspace layout", async ({ page }) => {
  const errors = await collectErrors(page);
  await page.goto("/chat");
  // Auth modal opens since not logged in
  await expect(page.getByRole("dialog")).toBeVisible();
  // Close the dialog and check layout
  await page.locator(".ant-modal-close").click();
  // Workspace should have chat panel
  await expect(page.locator(".chat-panel")).toBeVisible();
  await expect(page.locator(".chat-messages")).toBeVisible();
  await expect(page.locator(".floating-learning-input")).toBeVisible();
  // Resource panel group should be visible
  await expect(page.locator(".resource-panel-group")).toBeVisible();
  expect(errors).toEqual([]);
});

test("media studio page renders tabs and form", async ({ page }) => {
  const errors = await collectErrors(page);
  await page.goto("/media-studio");
  await expect(page.getByRole("heading", { name: "媒体工坊" })).toBeVisible();
  await expect(page.locator(".tab-bar")).toBeVisible();
  await expect(page.locator(".form-card")).toBeVisible();
  await page.getByText("图片生成").click();
  await expect(page.getByText("AI 图片生成")).toBeVisible();
  await page.getByText("图片分析").click();
  await expect(page.getByText("图片内容分析")).toBeVisible();
  expect(errors).toEqual([]);
});

test("practice page shows empty state", async ({ page }) => {
  await page.goto("/practice");
  await expect(page.getByText("练习模式")).toBeVisible();
  await expect(page.getByRole("button", { name: "题库管理" })).toBeVisible();
});

test("dashboard page loads without crash", async ({ page }) => {
  const errors = await collectErrors(page);
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "数据看板" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("navigation via sidebar works", async ({ page }) => {
  await page.goto("/chat");
  await page.locator(".ant-modal-close").click();
  await page.getByRole("button", { name: "练习模式" }).click();
  await expect(page).toHaveURL(/\/practice/);
  await page.getByRole("button", { name: "资源库" }).click();
  await expect(page).toHaveURL(/\/resources/);
  await page.getByRole("button", { name: "学习工作区" }).click();
  await expect(page).toHaveURL(/\/chat/);
});
