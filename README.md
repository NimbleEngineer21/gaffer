# Gaffer

Gaffer is a Home Assistant custom integration. It checks whether your automations
had the result you expected, and explains why when they did not.

Home Assistant can show you that an automation *ran*. It cannot show you that the
light came on or that the speaker volume changed. A command can be valid and still
have no effect: for example, some speakers ignore a volume change until playback
starts. Gaffer watches each run, works out what each action should do, checks the
devices afterwards, and reports each mismatch with a likely cause.

> **Status: early development.** Gaffer is not installable yet. This repository
> holds the integration skeleton and its test setup.

Gaffer runs locally. It makes no outbound network calls, and in its first version
it never changes an automation or a device.

Gaffer is not affiliated with Home Assistant or the Open Home Foundation.

## Development

You need [uv](https://docs.astral.sh/uv/) 0.13.4 or newer.

```sh
uv sync --locked
uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest
```

To test against the oldest supported Home Assistant release:

```sh
uv run --no-default-groups --group minimum pytest
```

## License

[MIT](LICENSE)
