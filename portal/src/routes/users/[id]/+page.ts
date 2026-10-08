// Profiles moved to /people/<id> (#65); old links land there, keeping their params.
import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ params, url }) => {
	redirect(308, `/people/${encodeURIComponent(params.id)}${url.search}`);
};
