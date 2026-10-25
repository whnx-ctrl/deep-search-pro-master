import { test, expect } from '@playwright/test'

test('upload, submit, receive, download and restore history', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('本地后端已连接')).toBeVisible()
  await expect(page.getByRole('heading', { name:/让每一个问题/ })).toBeVisible()
  await page.screenshot({ path:'test-results/workbench-welcome.png', fullPage:true })
  await page.getByLabel('选择上传文件').setInputFiles({
    name:'notes.txt', mimeType:'text/plain', buffer:Buffer.from('测试研究资料'),
  })
  await expect(page.getByText('已上传：notes.txt')).toBeVisible()
  await page.getByLabel('研究问题').fill('根据资料生成报告')
  await page.getByRole('button', { name:'发送问题', exact:true }).click()
  await expect(page.getByRole('heading', { name:'研究报告', exact:true })).toBeVisible({ timeout:20000 })
  await expect(page.getByText('受控测试助手', { exact:false })).toBeVisible()
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('link', { name:'下载 report.md', exact:true }).click(),
  ])
  expect(download.suggestedFilename()).toBe('report.md')
  await page.reload()
  await expect(page.getByRole('heading', { name:'研究报告', exact:true })).toBeVisible()
  await page.screenshot({ path:'test-results/workbench-result.png', fullPage:true })
})

test('failed task has an actionable message and can be retried', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('研究问题').fill('测试失败')
  await page.getByRole('button', { name:'发送问题', exact:true }).click()
  await expect(page.getByRole('alert').filter({ hasText:'任务执行失败' })).toBeVisible({ timeout:20000 })
  await expect(page.getByRole('button', { name:'发送问题', exact:true })).toBeDisabled() // empty composer after accepted run
  await page.getByLabel('研究问题').fill('重新研究')
  await expect(page.getByRole('button', { name:'发送问题', exact:true })).toBeEnabled()
})

test('running task survives refresh and unavailable WebSocket without resubmission', async ({ page }) => {
  let submitted = 0
  page.on('request', request => {
    if (request.method() === 'POST' && request.url().endsWith('/api/task')) submitted++
  })
  await page.goto('/')
  await page.getByLabel('研究问题').fill('刷新后继续接收报告')
  await page.getByRole('button', { name:'发送问题', exact:true }).click()
  await expect(page.getByText('正在研究，请稍候…')).toBeVisible()
  await page.routeWebSocket('**/ws/**', websocket => websocket.close())
  await page.reload()
  await expect(page.getByRole('heading', { name:'研究报告', exact:true })).toBeVisible({ timeout:20000 })
  expect(submitted).toBe(1)
})

test('backend restart keeps the existing session writable and reuses its thread id', async ({ page }) => {
  let instanceId = 'instance-before-restart'
  const submissions: Array<{ thread_id?: string }> = []
  await page.route('**/api/health', route => route.fulfill({
    json: {
      status: 'ok',
      instance_id: instanceId,
      capabilities: { search: true, database: true, knowledge: true },
    },
  }))
  page.on('request', request => {
    if (request.method() === 'POST' && request.url().endsWith('/api/task')) {
      submissions.push(request.postDataJSON())
    }
  })

  await page.goto('/')
  await page.getByLabel('研究问题').fill('重启前的问题')
  await page.getByRole('button', { name:'发送问题', exact:true }).click()
  await expect(page.getByRole('heading', { name:'研究报告', exact:true })).toBeVisible({ timeout:20000 })
  expect(submissions).toHaveLength(1)

  instanceId = 'instance-after-restart'
  await page.reload()
  await expect(page.getByText('旧会话的模型记忆已失效')).toHaveCount(0)
  await page.getByLabel('研究问题').fill('重启后继续追问')
  await expect(page.getByRole('button', { name:'发送问题', exact:true })).toBeEnabled()
  await page.getByRole('button', { name:'发送问题', exact:true }).click()
  await expect.poll(() => submissions.length).toBe(2)
  expect(submissions[1].thread_id).toBe(submissions[0].thread_id)
})

test('deletes a session from the backend and browser history', async ({ page }) => {
  let deletedThread = ''
  page.on('request', request => {
    if (request.method() === 'DELETE' && request.url().includes('/api/sessions/')) {
      deletedThread = request.url().split('/').pop() || ''
    }
  })
  page.on('dialog', dialog => dialog.accept())

  await page.goto('/')
  await page.getByLabel('研究问题').fill('需要删除的研究')
  await page.getByRole('button', { name:'发送问题', exact:true }).click()
  await expect(page.getByRole('heading', { name:'研究报告', exact:true })).toBeVisible({ timeout:20000 })
  await page.getByRole('button', { name:'删除会话：需要删除的研究' }).click()

  await expect(page.getByText('需要删除的研究', { exact:true })).toHaveCount(0)
  expect(deletedThread).toMatch(/^[0-9a-f-]{36}$/)
  await page.reload()
  await expect(page.getByText('需要删除的研究', { exact:true })).toHaveCount(0)
  await expect(page.getByLabel('研究问题')).toBeEnabled()
})

test('mobile drawers and input remain reachable', async ({ page }) => {
  await page.setViewportSize({ width:390, height:844 })
  await page.goto('/')
  await page.getByRole('button', { name:'打开会话列表' }).click()
  await expect(page.getByRole('button', { name:'新建研究', exact:false })).toBeVisible()
  await page.getByRole('button', { name:'关闭会话列表' }).click()
  await page.getByRole('button', { name:'切换执行与文件面板' }).click()
  await page.getByRole('button', { name:'收起执行面板' }).click()
  await expect(page.getByLabel('研究问题')).toBeVisible()
  await page.screenshot({ path:'test-results/workbench-mobile.png', fullPage:true })
})
