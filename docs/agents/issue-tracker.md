# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues on `JungleM0nkey/wumpus-archiver`. Use the `gh` CLI for all operations, or the GitHub MCP tools where a session has those instead of `gh`.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v`; `gh` does this automatically when run inside a clone.

## Tickets from a plan

`/to-tickets` publishes one issue per ticket, labelled `ready-for-agent`, as **sub-issues of an epic issue** (GitHub's native hierarchy) in dependency order. Each ticket's body carries a `## Blocked by` list of issue references. A ticket is unblocked when every issue it lists is closed; work the frontier, blockers first.

Where a session can reach the REST dependencies endpoint, mirror the `Blocked by` list as native issue dependencies: `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>` (the blocker's numeric database id from `gh api repos/<owner>/<repo>/issues/<n> --jq .id`, not its `#number`).

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

GitHub shares one number space across issues and PRs, so a bare `#42` may be either: resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.
