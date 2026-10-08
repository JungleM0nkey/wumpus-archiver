// The portal's one icon set: Lucide icons under the names the portal uses for them.
// Icon.svelte renders these; nothing else in the portal draws an icon. Each icon is
// imported on its own so the build carries only these.
import type { Component } from 'svelte';
import type { LucideProps } from '@lucide/svelte';
import Activity from '@lucide/svelte/icons/activity';
import Archive from '@lucide/svelte/icons/archive';
import ArrowDown from '@lucide/svelte/icons/arrow-down';
import ArrowLeft from '@lucide/svelte/icons/arrow-left';
import ArrowRight from '@lucide/svelte/icons/arrow-right';
import ArrowUp from '@lucide/svelte/icons/arrow-up';
import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
import Ban from '@lucide/svelte/icons/ban';
import ChartColumn from '@lucide/svelte/icons/chart-column';
import Check from '@lucide/svelte/icons/check';
import ChevronLeft from '@lucide/svelte/icons/chevron-left';
import ChevronRight from '@lucide/svelte/icons/chevron-right';
import ChevronsUpDown from '@lucide/svelte/icons/chevrons-up-down';
import Circle from '@lucide/svelte/icons/circle';
import CircleCheck from '@lucide/svelte/icons/circle-check';
import CircleDashed from '@lucide/svelte/icons/circle-dashed';
import CircleDot from '@lucide/svelte/icons/circle-dot';
import CircleHelp from '@lucide/svelte/icons/circle-help';
import CircleX from '@lucide/svelte/icons/circle-x';
import Command from '@lucide/svelte/icons/command';
import CornerDownLeft from '@lucide/svelte/icons/corner-down-left';
import Download from '@lucide/svelte/icons/download';
import Folder from '@lucide/svelte/icons/folder';
import Hash from '@lucide/svelte/icons/hash';
import Heart from '@lucide/svelte/icons/heart';
import History from '@lucide/svelte/icons/history';
import ImageOff from '@lucide/svelte/icons/image-off';
import Images from '@lucide/svelte/icons/images';
import Inbox from '@lucide/svelte/icons/inbox';
import Info from '@lucide/svelte/icons/info';
import Keyboard from '@lucide/svelte/icons/keyboard';
import Layers from '@lucide/svelte/icons/layers';
import LayoutDashboard from '@lucide/svelte/icons/layout-dashboard';
import LayoutGrid from '@lucide/svelte/icons/layout-grid';
import Menu from '@lucide/svelte/icons/menu';
import MessageSquare from '@lucide/svelte/icons/message-square';
import MessagesSquare from '@lucide/svelte/icons/messages-square';
import OctagonAlert from '@lucide/svelte/icons/octagon-alert';
import PanelLeftClose from '@lucide/svelte/icons/panel-left-close';
import PanelLeftOpen from '@lucide/svelte/icons/panel-left-open';
import Paperclip from '@lucide/svelte/icons/paperclip';
import Pin from '@lucide/svelte/icons/pin';
import Play from '@lucide/svelte/icons/play';
import Radio from '@lucide/svelte/icons/radio';
import Reply from '@lucide/svelte/icons/reply';
import Rows3 from '@lucide/svelte/icons/rows-3';
import Search from '@lucide/svelte/icons/search';
import SearchX from '@lucide/svelte/icons/search-x';
import Server from '@lucide/svelte/icons/server';
import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
import Users from '@lucide/svelte/icons/users';
import Volume2 from '@lucide/svelte/icons/volume-2';
import X from '@lucide/svelte/icons/x';
// #64 Search: filter chips and result rows.
import Calendar from '@lucide/svelte/icons/calendar';
import File from '@lucide/svelte/icons/file';
import Image from '@lucide/svelte/icons/image';
import Link from '@lucide/svelte/icons/link';
import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
import UserIcon from '@lucide/svelte/icons/user';
import Video from '@lucide/svelte/icons/video';

export const icons = {
	activity: Activity,
	archive: Archive,
	'arrow-down': ArrowDown,
	'arrow-left': ArrowLeft,
	'arrow-right': ArrowRight,
	'arrow-up': ArrowUp,
	'arrow-up-right': ArrowUpRight,
	ban: Ban,
	chart: ChartColumn,
	check: Check,
	'chevron-left': ChevronLeft,
	'chevron-right': ChevronRight,
	'chevrons-up-down': ChevronsUpDown,
	circle: Circle,
	'circle-check': CircleCheck,
	'circle-dashed': CircleDashed,
	'circle-dot': CircleDot,
	'circle-help': CircleHelp,
	'circle-x': CircleX,
	command: Command,
	'corner-down-left': CornerDownLeft,
	download: Download,
	folder: Folder,
	hash: Hash,
	heart: Heart,
	history: History,
	'image-off': ImageOff,
	images: Images,
	inbox: Inbox,
	info: Info,
	keyboard: Keyboard,
	layers: Layers,
	dashboard: LayoutDashboard,
	grid: LayoutGrid,
	menu: Menu,
	message: MessageSquare,
	forum: MessagesSquare,
	'octagon-alert': OctagonAlert,
	'panel-left-close': PanelLeftClose,
	'panel-left-open': PanelLeftOpen,
	paperclip: Paperclip,
	pin: Pin,
	play: Play,
	stage: Radio,
	reply: Reply,
	rows: Rows3,
	search: Search,
	'search-x': SearchX,
	server: Server,
	'triangle-alert': TriangleAlert,
	users: Users,
	voice: Volume2,
	x: X,
	// #64 Search
	calendar: Calendar,
	file: File,
	image: Image,
	link: Link,
	refine: SlidersHorizontal,
	user: UserIcon,
	video: Video
} satisfies Record<string, Component<LucideProps>>;

export type IconName = keyof typeof icons;
