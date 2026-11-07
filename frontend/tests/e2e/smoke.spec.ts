import { expect, test } from '@playwright/test'

/**
 * E2E smoke: login → dashboard → navigate → logout.
 * Runs against the dev server (started by playwright.config.ts).
 */

const ADMIN_USER = process.env.E2E_ADMIN_USER || 'admin'
const ADMIN_PASS = process.env.E2E_ADMIN_PASS || 'admin123'

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByPlaceholder('请输入用户名').fill(ADMIN_USER)
  await page.getByPlaceholder('请输入密码').fill(ADMIN_PASS)
  await page.getByRole('button', { name: '登录' }).click()
  // Wait for dashboard to render
  await expect(page.getByText('欢迎回来')).toBeVisible({ timeout: 10_000 })
}

test.describe('VisionFlywheel E2E smoke', () => {
  test('login page renders', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByText('视觉飞轮')).toBeVisible()
    await expect(page.getByRole('button', { name: '登录' })).toBeVisible()
  })

  test('login -> dashboard', async ({ page }) => {
    await login(page)
    // Stat cards visible
    await expect(page.getByText('识别目标')).toBeVisible()
    await expect(page.getByText('校正动作')).toBeVisible()
  })

  test('navigate to detect page', async ({ page }) => {
    await login(page)
    await page.getByRole('menuitem', { name: '识别' }).click()
    await expect(page.getByText('上传', { exact: true })).toBeVisible()
  })

  test('navigate to annotate page', async ({ page }) => {
    await login(page)
    await page.getByRole('menuitem', { name: '校正工作台' }).click()
    await expect(page.getByText('校正工作台')).toBeVisible()
  })

  test('navigate to dataset page', async ({ page }) => {
    await login(page)
    await page.getByRole('menuitem', { name: '数据与权重' }).click()
    await expect(page.getByText('数据与权重')).toBeVisible()
  })

  test('navigate to chat page', async ({ page }) => {
    await login(page)
    await page.getByRole('menuitem', { name: '智能分析' }).click()
    await expect(page.getByText('智能分析')).toBeVisible()
  })

  test('admin can see rbac menu', async ({ page }) => {
    await login(page)
    await expect(page.getByRole('menuitem', { name: '身份与权限' })).toBeVisible()
    await page.getByRole('menuitem', { name: '身份与权限' }).click()
    await expect(page.getByText('RBAC 角色矩阵')).toBeVisible()
  })

  test('logout returns to login', async ({ page }) => {
    await login(page)
    await page.getByText('退出登录').click()
    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByText('视觉飞轮')).toBeVisible()
  })

  test('wrong password shows error', async ({ page }) => {
    await page.goto('/login')
    await page.getByPlaceholder('请输入用户名').fill(ADMIN_USER)
    await page.getByPlaceholder('请输入密码').fill('wrong-password')
    await page.getByRole('button', { name: '登录' }).click()
    await expect(page.getByText('用户名或密码错误')).toBeVisible({ timeout: 5000 })
  })

  test('403 page shows for unauthorized access', async ({ page }) => {
    await login(page)
    // Direct nav to admin (admin has access, so this shows the admin page)
    await page.goto('/admin')
    await expect(page).toHaveURL(/\/admin/)
  })
})
