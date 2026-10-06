# The app factory connects only what it did not find connected

The API app's lifespan connects the Database on startup only if it is not already connected, and disconnects on shutdown only what it connected itself. This lets one `create_app` call serve every composition without a flag: the server hands in an unconnected Database and the app owns its lifetime; the test fixtures hand in a connected one and keep owning it (the in-process test client never runs the lifespan anyway); a seeded database shared across a test module is never torn down by an app built over it. `Database.connect()` is not idempotent (a second call replaces the engine without disposing it), so an unconditional connect was a silent double-connect in tests.

## Considered options

- **Opt-in lifespan** (`create_app(..., lifespan=manage_database)`, passed by `serve` and the dev module, omitted by tests). Rejected: forgetting the keyword fails at the first request rather than at startup, and reload targets and a zero-argument factory cannot pass a keyword they do not have.
- **Unconditional connect/disconnect, documented as "never run the lifespan over a database you connected yourself".** Rejected: a stated rule the code does not enforce, and the double-connect it permits is silent.

## Consequences

The rule is implicit behaviour: an app handed an already-connected Database will not reconnect it, so a real server started in another thread over a connected database would reuse a cross-loop engine. Screenshot and smoke harnesses therefore run a separate server process over the database file with its own fresh Database.
