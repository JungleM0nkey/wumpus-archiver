// The Media screen's arithmetic: what kind an attachment is, the shape its tile takes,
// the justified rows tiles are laid out in, and month groups merged across pages.
// Kept apart from the screen so a second view of media (Browse's Media tab) can reuse it.
import type { GalleryAttachment, TimelineGalleryGroup } from './types';

/** The kinds the gallery timeline filters by; `media` is all of them together. */
export type MediaType = 'image' | 'video' | 'gif';
export type TimelineContentType = MediaType | 'media';

/** The kind of tile an attachment gets: a video, an (animated) GIF, or a still image. */
export function mediaKind(attachment: Pick<GalleryAttachment, 'content_type'>): MediaType {
	const type = attachment.content_type ?? '';
	if (type.startsWith('video/')) return 'video';
	if (type === 'image/gif') return 'gif';
	return 'image';
}

/** Whether an attachment is media the Lightbox shows (an image, a GIF or a video), not a file. */
export function isMedia(attachment: Pick<GalleryAttachment, 'content_type'>): boolean {
	const type = attachment.content_type ?? '';
	return type.startsWith('image/') || type.startsWith('video/');
}

/** The aspect ratio a tile takes when an attachment's size is neither recorded nor measured yet. */
export const FALLBACK_ASPECT = 1;

/** Tiles keep their natural shape within these bounds, so a sliver never fills a row alone. */
const MIN_ASPECT = 0.4;
const MAX_ASPECT = 3;

/**
 * A tile's width over its height: the attachment's recorded size, else the size the
 * browser measured once it loaded, else square.
 */
export function aspectOf(
	attachment: Pick<GalleryAttachment, 'width' | 'height'>,
	measured?: number
): number {
	const { width, height } = attachment;
	const natural = width && height ? width / height : measured;
	if (!natural || !Number.isFinite(natural)) return FALLBACK_ASPECT;
	return Math.min(MAX_ASPECT, Math.max(MIN_ASPECT, natural));
}

/** One justified row: tiles `start` up to (not including) `end`, all `height` px tall. */
export interface JustifiedRow {
	start: number;
	end: number;
	height: number;
}

/**
 * Lay tiles of the given aspect ratios out in rows that fill `width` exactly, each as
 * close to `target` px tall as the tiles allow, with `gap` px between tiles. A row
 * ends where its height comes nearest the target. The last row keeps the target
 * height rather than stretching to fill the width.
 */
export function justify(aspects: number[], width: number, target: number, gap: number): JustifiedRow[] {
	const rows: JustifiedRow[] = [];
	if (width <= 0) return rows;
	let start = 0;
	let sum = 0;
	/** The height that makes tiles start..end fill the width, given their aspect sum. */
	const fill = (end: number, aspectSum: number) => (width - gap * (end - start - 1)) / aspectSum;

	for (let i = 0; i < aspects.length; i++) {
		sum += aspects[i];
		const height = fill(i + 1, sum);
		if (height > target) continue;
		// Adding tile i takes the row below the target: end it here, or before tile i
		// if that comes nearer the target.
		const without = i > start ? fill(i, sum - aspects[i]) : Infinity;
		if (without - target < target - height) {
			rows.push({ start, end: i, height: without });
			start = i;
			sum = aspects[i];
			// Tile i starts the next row, which may already be full on its own.
			const alone = fill(i + 1, sum);
			if (alone <= target) {
				rows.push({ start, end: i + 1, height: alone });
				start = i + 1;
				sum = 0;
			}
		} else {
			rows.push({ start, end: i + 1, height });
			start = i + 1;
			sum = 0;
		}
	}
	if (start < aspects.length) {
		rows.push({ start, end: aspects.length, height: Math.min(target, fill(aspects.length, sum)) });
	}
	return rows;
}

/**
 * `groups` with `page`'s groups appended. The gallery timeline groups each page on its
 * own, so a month split across pages arrives twice under one period key: it is merged
 * into one group, and the screen shows one header for it.
 */
export function mergeGroups(
	groups: TimelineGalleryGroup[],
	page: TimelineGalleryGroup[]
): TimelineGalleryGroup[] {
	const merged = groups.map((g) => ({ ...g }));
	for (const group of page) {
		const same = merged.find((g) => g.period === group.period);
		if (same) {
			same.attachments = [...same.attachments, ...group.attachments];
			same.count = same.attachments.length;
		} else {
			merged.push({ ...group });
		}
	}
	return merged;
}
