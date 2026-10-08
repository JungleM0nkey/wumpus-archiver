// The portal smoke suite: `npm run smoke` builds the portal, then runs these tests.
//
// Playwright's web server seeds a small archive (tests/smoke_archive.py) into
// portal/.smoke-archive and serves it with `wumpus-archiver serve`, the same
// composition a user runs, over the portal build. The server runs from the archive
// directory so a developer's .env is not read, and with blank tokens so scrape
// control is read-only whatever the shell exports.
//
// Environment:
//   SMOKE_PYTHON  the Python that has wumpus-archiver installed (default: ../.venv/bin/python)
//   SMOKE_PORT    the port to serve on (default: 4317)
//   SMOKE_CHROMIUM  a Chromium executable to launch instead of Playwright's own
import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, defineConfig, devices } from '@playwright/test';

const portalDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(portalDir, '..');
const archiveDir = resolve(portalDir, '.smoke-archive');
const python = process.env.SMOKE_PYTHON ?? resolve(repoRoot, '.venv/bin/python');
const port = Number(process.env.SMOKE_PORT ?? 4317);

// A machine with browsers preinstalled for another Playwright release keeps one at
// /opt/pw-browsers/chromium; use it when this release's own Chromium is missing.
const PREINSTALLED_CHROMIUM = '/opt/pw-browsers/chromium';
function chromiumExecutable(): string | undefined {
	if (process.env.SMOKE_CHROMIUM) return process.env.SMOKE_CHROMIUM;
	if (existsSync(chromium.executablePath())) return undefined;
	return existsSync(PREINSTALLED_CHROMIUM) ? PREINSTALLED_CHROMIUM : undefined;
}

const sh = (s: string) => `'${s.replaceAll("'", `'\\''`)}'`;

export default defineConfig({
	testDir: './smoke',
	fullyParallel: true,
	forbidOnly: !!process.env.CI,
	retries: 0,
	reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
	use: {
		baseURL: `http://127.0.0.1:${port}`,
		trace: 'retain-on-failure',
		launchOptions: { executablePath: chromiumExecutable() }
	},
	projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
	webServer: {
		command: [
			`${sh(python)} -m tests.smoke_archive ${sh(archiveDir)}`,
			`cd ${sh(archiveDir)}`,
			`exec ${sh(python)} -m wumpus_archiver.cli serve archive.db --port ${port} -a attachments`
		].join(' && '),
		cwd: repoRoot,
		url: `http://127.0.0.1:${port}/api/guilds`,
		env: { DISCORD_BOT_TOKEN: '', API_AUTH_TOKEN: '' },
		reuseExistingServer: false,
		stdout: 'pipe',
		timeout: 60_000
	}
});
