<script lang="ts">
	let {
		label,
		value,
		icon = '',
		sub = '',
	}: {
		label: string;
		value: string | number;
		icon?: string;
		sub?: string;
	} = $props();
</script>

<div class="stat-card">
	{#if icon}
		<span class="stat-icon">{icon}</span>
	{/if}
	<div class="stat-value">{typeof value === 'number' ? value.toLocaleString() : value}</div>
	<div class="stat-label">{label}</div>
	{#if sub}
		<div class="stat-sub mono">{sub}</div>
	{/if}
</div>

<style>
	.stat-card {
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-lg);
		padding: var(--sp-5);
		display: flex;
		flex-direction: column;
		gap: var(--sp-1);
		transition: border-color 0.2s var(--ease-out);
	}

	.stat-card:hover {
		border-color: var(--border-strong);
	}

	.stat-icon {
		font-size: 20px;
		margin-bottom: var(--sp-1);
	}

	.stat-value {
		font-family: var(--font-mono);
		font-size: 28px;
		font-weight: 700;
		letter-spacing: -0.03em;
		color: var(--text-primary);
		line-height: 1.1;
	}

	.stat-label {
		font-size: 13px;
		font-weight: 500;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.stat-sub {
		font-size: 11px;
		color: var(--text-muted);
	}
</style>
