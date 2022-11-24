import asyncio
from pathlib import Path

from .bot import init_bot

from .secrets import load_secrets
# from . import bot

root_dir = Path.cwd()

secrets = load_secrets(root_dir/'secrets.toml')

bot = asyncio.run(init_bot())

bot.run(token=secrets.token)


# bot.client.run(token=secrets.token)




