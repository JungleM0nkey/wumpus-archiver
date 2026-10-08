// The old timeline reader is Browse now (#60), with the same channel selected.
import { redirect } from '@sveltejs/kit';
import { channelHref, keepingGuild } from '#lib/routes.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ url }) => {
	const channel = url.searchParams.get('channel');
	redirect(307, keepingGuild(channel ? channelHref(channel) : '/browse', url));
};
