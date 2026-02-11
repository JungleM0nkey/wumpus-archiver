<script lang="ts">
	import '../lib/styles/global.css';
	import Nav from '../lib/components/Nav.svelte';

	let { children } = $props();
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

{@render children()}
