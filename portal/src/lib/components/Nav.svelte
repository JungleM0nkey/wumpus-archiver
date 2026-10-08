<script lang="ts">
	import { page } from '$app/state';
	import Icon from './ui/Icon.svelte';
	import type { IconName } from './ui/icons.ts';

	const links: { href: string; label: string; icon: IconName }[] = [
		{ href: '/', label: 'Dashboard', icon: 'dashboard' },
		{ href: '/timeline', label: 'Timeline', icon: 'rows' },
		{ href: '/search', label: 'Search', icon: 'search' },
		{ href: '/channels', label: 'Channels', icon: 'hash' },
		{ href: '/gallery', label: 'Gallery', icon: 'images' },
		{ href: '/users', label: 'Users', icon: 'users' },
		{ href: '/control', label: 'Control', icon: 'server' }
	];

	function isActive(href: string): boolean {
		if (href === '/') return page.url.pathname === '/';
		return page.url.pathname.startsWith(href);
	}
</script>

<nav class="nav">
	<div class="nav-inner">
		<a href="/" class="brand">
			<span class="brand-mark"><Icon name="archive" size={18} /></span>
			<span class="brand-text">wumpus<span class="brand-accent">.archive</span></span>
		</a>

		<div class="nav-links">
			{#each links as link (link.href)}
				{@const active = isActive(link.href)}
				<a
					href={link.href}
					class="nav-link"
					class:active
					aria-current={active ? 'page' : undefined}
				>
					<Icon name={link.icon} />
					{link.label}
				</a>
			{/each}
		</div>

		<div class="nav-right">
			<span class="version mono">v{__PORTAL_VERSION__}</span>
		</div>
	</div>
</nav>

<style>
	.nav {
		height: var(--size-topbar);
		background: var(--bg-surface);
		border-bottom: 1px solid var(--border-subtle);
		flex-shrink: 0;
		z-index: 100;
	}

	.nav-inner {
		height: 100%;
		max-width: 1400px;
		margin: 0 auto;
		padding: 0 var(--space-6);
		display: flex;
		align-items: center;
		gap: var(--space-8);
	}

	.brand {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		color: var(--text-primary);
		font: var(--type-heading-sm);
	}

	.brand:hover {
		color: var(--text-primary);
	}

	.brand-mark {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 28px;
		height: 28px;
		border-radius: var(--radius-sm);
		background: var(--accent-muted);
		color: var(--accent);
	}

	.brand-accent {
		color: var(--text-secondary);
		font-weight: 500;
	}

	.nav-links {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		min-width: 0;
		overflow-x: auto;
	}

	.nav-link {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		height: 32px;
		padding: 0 var(--space-3);
		border-radius: var(--radius-sm);
		font: var(--type-label-md);
		color: var(--text-secondary);
		white-space: nowrap;
		transition:
			background-color var(--duration-micro) var(--ease-out-quint),
			color var(--duration-micro) var(--ease-out-quint);
	}

	.nav-link:hover {
		color: var(--text-primary);
		background: var(--bg-hover);
	}

	.nav-link.active {
		color: var(--text-primary);
		background: var(--bg-active);
	}

	.nav-link.active :global(.icon) {
		color: var(--accent);
	}

	.nav-right {
		margin-left: auto;
		display: flex;
		align-items: center;
		gap: var(--space-3);
	}

	.version {
		font: var(--type-mono-sm);
		color: var(--text-tertiary);
		padding: 3px 8px;
		border-radius: var(--radius-xs);
		background: var(--bg-raised);
		border: 1px solid var(--border-subtle);
	}
</style>
