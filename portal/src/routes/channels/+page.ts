// The old channel grid is Browse's channel pane now (#60).
import { redirect } from '@sveltejs/kit';
import { keepingGuild } from '#lib/routes.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ url }) => {
	redirect(307, keepingGuild('/browse', url));
};
