# sv

Everything you need to build a Svelte project, powered by [`sv`](https://github.com/sveltejs/cli).

## Creating a project

If you're seeing this, you've probably already done this step. Congrats!

```sh
# create a new project
npx sv create my-app
```

To recreate this project with the same configuration:

```sh
# recreate this project
npx sv create --template minimal --types ts --install npm portal
```

## Developing

Once you've created a project and installed dependencies with `npm install` (or `pnpm install` or `yarn`), start a development server:

```sh
npm run dev

# or start the server and open the app in a new browser tab
npm run dev -- --open
```

## Building

To create a production version of your app:

```sh
npm run build
```

You can preview the production build with `npm run preview`.

> To deploy your app, you may need to install an [adapter](https://svelte.dev/docs/kit/adapters) for your target environment.

## Smoke suite

`npm run smoke` builds the portal, seeds a small test archive (`../tests/smoke_archive.py`), serves it with `wumpus-archiver serve` and opens every route in Chromium. A route fails on a page error, a console error or a 4xx/5xx response. It runs the archiver from `../.venv` unless `SMOKE_PYTHON` names another Python; on a new machine, install the browser once with `npx playwright install chromium`. Known failures, each with the ticket that removes it, are in `smoke/known-failures.ts`.
