// A channel's gallery became the Media screen filtered to that channel (#62). The
// selected guild and any other params come along.
import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ params, url }) => {
	const search = new URLSearchParams(url.searchParams);
	search.set('channel', params.id);
	redirect(308, `/media?${search}`);
};
