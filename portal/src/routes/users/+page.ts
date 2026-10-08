// The People screen moved to /people (#65); old links land there, keeping their params.
import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ url }) => {
	redirect(308, `/people${url.search}`);
};
