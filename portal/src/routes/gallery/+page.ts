// The gallery became the Media screen (#62); old links keep working, with their params.
import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ url }) => {
	redirect(308, `/media${url.search}`);
};
