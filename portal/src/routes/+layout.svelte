<script lang="ts">
	import '../lib/styles/global.css';
	import Nav from '../lib/components/Nav.svelte';
	import { checkAuth, setApiToken } from '$lib/api';

	let { children } = $props();

	// Restore API token from localStorage on load
	const stored = typeof window !== 'undefined' ? localStorage.getItem('wumpus_api_token') : null;
	if (stored) setApiToken(stored);

	// Check if auth is required and prompt if needed
	if (typeof window !== 'undefined') {
		checkAuth().then((res) => {
			if (res.auth_required && !res.authenticated && !stored) {
				const token = prompt('API secret required. Enter your API_SECRET:');
				if (token) {
					localStorage.setItem('wumpus_api_token', token);
					setApiToken(token);
				}
			}
		}).catch(() => {});
	}
</script>

<svelte:head>
	<title>Wumpus Archiver</title>
</svelte:head>

<div class="app-shell">
	<Nav />
	<main class="main-content">
		{@render children()}
	</main>
</div>

<style>
	.app-shell {
		width: 100vw;
		height: 100vh;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.main-content {
		flex: 1;
		overflow-y: auto;
		overflow-x: hidden;
	}
</style>
