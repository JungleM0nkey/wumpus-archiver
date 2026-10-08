// Static generation — all pages prerendered as SPA with fallback
import { loadGuilds } from '#lib/shell.svelte.ts';

export const prerender = false;
export const ssr = false;

// Every screen reads the selected guild (#lib/shell.svelte.ts), so the guilds are read
// once, before any route renders. The load reads nothing from the URL, so it never
// runs again.
export async function load(): Promise<Record<string, never>> {
	await loadGuilds();
	return {};
}
