<script lang="ts">
	import { page } from '$app/state';

	const links = [
		{ href: '/', label: 'Dashboard', icon: '◈' },
		{ href: '/timeline', label: 'Timeline', icon: '▤' },
		{ href: '/search', label: 'Search', icon: '⌕' },
		{ href: '/channels', label: 'Channels', icon: '≡' },
		{ href: '/gallery', label: 'Gallery', icon: '⊞' },
		{ href: '/users', label: 'Users', icon: '◉' },
		{ href: '/control', label: 'Control', icon: '⚙' },
	];

	function isActive(href: string): boolean {
		if (href === '/') return page.url.pathname === '/';
		return page.url.pathname.startsWith(href);
	}
</script>

<nav class="nav">
	<div class="nav-inner">
		<a href="/" class="brand">
			<span class="brand-icon">⟐</span>
			<span class="brand-text">wumpus<span class="brand-accent">.archive</span></span>
		</a>

		<div class="nav-links">
			{#each links as link}
				<a
					href={link.href}
					class="nav-link"
					class:active={isActive(link.href)}
				>
					<span class="nav-icon">{link.icon}</span>
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
		text-decoration: none;
		color: var(--text-primary);
		font-weight: 600;
		font-size: 16px;
		letter-spacing: -0.02em;
	}

	.brand:hover { color: var(--text-primary); text-decoration: none; }

	.brand-icon {
		font-size: 20px;
		color: var(--accent);
	}

	.brand-accent {
		color: var(--accent);
		font-family: var(--font-mono);
		font-weight: 500;
	}

	.nav-links {
		display: flex;
		align-items: center;
		gap: var(--space-1);
	}

	.nav-link {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-3);
		border-radius: var(--radius-sm);
		font-size: 14px;
		font-weight: 500;
		color: var(--text-secondary);
		transition: all var(--duration-micro) var(--ease-out-quint);
		text-decoration: none;
	}

	.nav-link:hover {
		color: var(--text-primary);
		background: var(--bg-hover);
		text-decoration: none;
	}

	.nav-link.active {
		color: var(--accent);
		background: var(--accent-muted);
	}

	.nav-icon {
		font-size: 15px;
		opacity: 0.7;
	}

	.nav-right {
		margin-left: auto;
		display: flex;
		align-items: center;
		gap: var(--space-3);
	}

	.version {
		font-size: 11px;
		color: var(--text-tertiary);
		padding: 2px 8px;
		border-radius: var(--radius-xs);
		background: var(--bg-raised);
		border: 1px solid var(--border-subtle);
	}
</style>
