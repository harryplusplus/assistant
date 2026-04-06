# Assistant

A personal AI assistant built with Discord and Codex.

## Requirements

Codex CLI
```sh
codex --version # codex-cli 0.118.0
```

Set the following environment variables:

```dotenv
DISCORD_TOKEN=your-token
DISCORD_GUILD_ID=your-guild-id
```

## Running

For local development:

```sh
ASSISTANT_HOME=$(pwd) uv run -m assistant
```

For personal deployment:

`ASSISTANT_HOME` defaults to `$HOME/.assistant`.

```sh
uv run -m assistant
```
