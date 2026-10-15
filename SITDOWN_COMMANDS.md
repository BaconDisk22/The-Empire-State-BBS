# 🤌 The Sitdown BBS — Radio commands

Send these commands as **direct messages to your BBS radio**, not to a public channel.

| Command | Action |
| --- | --- |
| `/sitdown`, `/menu`, `/cancel` | Main menu |
| `/help`, `/ayyy` | Quick help |
| `/mail`, `/inbox` | Check mail |
| `/boards`, `/socialclub` | Bulletin boards |
| `/fortune` | Random fortune |
| `/tools`, `/utilities` | Utilities menu |

The existing one-letter menu options and existing quick commands remain available. These shortcuts are exact matches, case insensitive. In mail or bulletin text-entry steps, most shortcuts are ignored to avoid mangling content; `/cancel`, `/menu`, `/sitdown` and `/help` remain available.

## Design palette

`sitdown_theme.json` defines the **future desktop UI** palette: charcoal and black, Italian red and green, mozzarella white, diner gold. There are **no Joker colors**. The JSON is a design resource; the Python server currently has no desktop GUI to render it.

## Development

Run alias unit tests with:

```sh
python -m unittest discover -s tests -p 'test_sitdown_commands.py'
```

Radio integration and packaging still require hardware/runtime validation.
