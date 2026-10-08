// The old channel reader is Browse now (#60), keeping a message link's message. Its
// gallery below stays a route of its own.
import { redirect } from '@sveltejs/kit';
import { channelHref, keepingGuild } from '#lib/routes.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ params, url }) => {
	const message = url.searchParams.get('message') ?? undefined;
	redirect(307, keepingGuild(channelHref(params.id, { message }), url));
};
