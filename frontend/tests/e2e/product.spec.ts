import { expect, type Page, test } from "@playwright/test";

const IGNORED_ERROR_PATTERNS = [
  "404",
  "WebSocket",
  "ws://",
  "HMR",
  "hot update",
  "analytics",
  "favicon",
  "ResizeObserver",
  "Non-Error promise rejection",
];

async function expectNoConsoleErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      const text = message.text();
      if (!IGNORED_ERROR_PATTERNS.some((p) => text.includes(p))) {
        errors.push(text);
      }
    }
  });
  return errors;
}

test("profile workspace and resource gear render", async ({ page }, testInfo) => {
  const errors = await expectNoConsoleErrors(page);
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await expect(page.getByRole("heading", { name: /两周内掌握|新建学习画像|掌握/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "新创画像" })).toBeVisible();
  await expect(page.getByRole("button", { name: "历史画像" })).toBeVisible();
  await expect(page.getByTestId("learning-start-panel")).toBeVisible();
  await expect(page.getByTestId("resource-gear")).toBeVisible();
  await expect(page.getByTestId("resource-gear")).toContainText(/文档|图解|视频|代码|练习|数字人老师/);
  await testInfo.attach("workspace", { body: await page.screenshot({ fullPage: true }), contentType: "image/png" });

  if (testInfo.project.name === "mobile") {
    expect(errors).toEqual([]);
    return;
  }

  await page.getByRole("button", { name: "发送并更新画像" }).click();
  await expect(page.getByText(/本轮画像聊天已完成|画像、学习路径和资源已按最新对话刷新/)).toBeVisible();

  await page.getByRole("button", { name: "代码" }).click();
  await expect(page.getByTestId("resources-tab")).toContainText(/代码|class|Stack/);

  await page.getByRole("button", { name: "数字人老师" }).click();
  await expect(page.getByText("数字人老师讲解")).toBeVisible();
  await testInfo.attach("teacher", { body: await page.screenshot({ fullPage: true }), contentType: "image/png" });

  expect(errors).toEqual([]);
});

test("resource generation failure is visible", async ({ page }) => {
  await page.route("**/api/v1/learning/start", (route) => route.fulfill({ status: 500, body: "forced failure" }));
  await page.goto("/");
  await page.getByRole("button", { name: "发送并更新画像" }).click();
  await expect(page.getByText(/资源生成失败|POST \/learning\/start failed/)).toBeVisible();
});
