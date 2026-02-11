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
			<span class="version mono">v0.1.0</span>
		</div>
	</div>
</nav>

<style>
	.nav {
		height: var(--nav-height);
		background: var(--bg-surface);
		border-bottom: 1px solid var(--border);
		flex-shrink: 0;
		z-index: 100;
	}

	.nav-inner {
		height: 100%;
		max-width: 1400px;
		margin: 0 auto;
		padding: 0 var(--sp-6);
		display: flex;
		align-items: center;
		gap: var(--sp-8);
	}

	.brand {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
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
		color: var(--accent-text);
		font-family: var(--font-mono);
		font-weight: 500;
	}

	.nav-links {
		display: flex;
		align-items: center;
		gap: var(--sp-1);
	}

	.nav-link {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		padding: var(--sp-2) var(--sp-3);
		border-radius: var(--radius-md);
		font-size: 14px;
		font-weight: 500;
		color: var(--text-secondary);
		transition: all 0.15s var(--ease-out);
		text-decoration: none;
	}

	.nav-link:hover {
		color: var(--text-primary);
		background: var(--bg-hover);
		text-decoration: none;
	}

	.nav-link.active {
		color: var(--accent-text);
		background: var(--accent-glow);
	}

	.nav-icon {
		font-size: 15px;
		opacity: 0.7;
	}

	.nav-right {
		margin-left: auto;
		display: flex;
		align-items: center;
		gap: var(--sp-3);
	}

	.version {
		font-size: 11px;
		color: var(--text-muted);
		padding: 2px 8px;
		border-radius: var(--radius-sm);
		background: var(--bg-raised);
		border: 1px solid var(--border);
	}
</style>
