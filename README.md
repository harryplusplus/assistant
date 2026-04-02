# assistant

## Discord mention printer

Set these variables in `.env`:

```env
DISCORD_TOKEN=your-bot-token
DISCORD_GUILD_ID=123456789012345678
ASSISTANT_LOG_LEVEL=info
DISCORD_LOG_LEVEL=info
```

Run:

```bash
uv run python -m assistant
```

The bot will print only messages from `DISCORD_GUILD_ID` that mention the running bot user.

`ASSISTANT_LOG_LEVEL` defaults to `info`. Set it to `debug` to see the `on_message` debug log.
`DISCORD_LOG_LEVEL` defaults to `info`. Keep it there to avoid Discord debug noise.
