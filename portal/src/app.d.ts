// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}

	/** The portal's package version, from package.json (see vite.config.ts). */
	const __PORTAL_VERSION__: string;
}

export {};
