/* Scratch: baseline console capture for Commit 19 research (not part of the app). */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const BASE = 'http://localhost:8081'
const OUT = __dirname

async function main() {
  const browser = await chromium.launch()
  const page = await browser.newPage()
  const messages = []
  const pageErrors = []
  const failedRequests = []

  page.on('console', (msg) => {
    messages.push({
      type: msg.type(),
      text: msg.text().slice(0, 500),
      url: msg.location().url,
    })
  })
  page.on('pageerror', (err) => pageErrors.push(String(err).slice(0, 500)))
  page.on('requestfailed', (req) =>
    failedRequests.push({ url: req.url(), error: req.failure()?.errorText }),
  )

  const routes = ['/', '/library', '/jam-practice']
  for (const route of routes) {
    messages.push({ type: 'nav', text: `=== ${route} ===`, url: '' })
    await page.goto(BASE + route, { waitUntil: 'networkidle', timeout: 60000 }).catch((e) => {
      messages.push({ type: 'nav-error', text: String(e), url: route })
    })
    await page.waitForTimeout(3000)
  }

  const summary = {
    capturedAt: new Date().toISOString(),
    routes,
    totalConsole: messages.filter((m) => m.type !== 'nav' && m.type !== 'nav-error').length,
    byType: {},
    pageErrors,
    failedRequests,
    messages,
  }
  for (const m of messages) summary.byType[m.type] = (summary.byType[m.type] || 0) + 1

  fs.writeFileSync(path.join(OUT, 'baseline', 'console-capture.json'), JSON.stringify(summary, null, 2))
  const lines = messages.map((m) => `[${m.type}] ${m.text}`)
  fs.writeFileSync(path.join(OUT, 'baseline', 'console-capture.txt'), lines.join('\n'))
  console.log('totalConsole:', summary.totalConsole, 'byType:', JSON.stringify(summary.byType))
  console.log('pageErrors:', pageErrors.length, 'failedRequests:', failedRequests.length)
  await browser.close()
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
