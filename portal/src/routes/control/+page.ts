// /control was the Archive screen's address: it redirects to /archive, keeping the
// query (the selected `guild`).
import { redirect } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ url }) => {
	redirect(308, `/archive${url.search}`);
};
