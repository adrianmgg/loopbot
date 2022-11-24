import asyncio
from typing import AsyncGenerator, Literal, Optional, Union
import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path
import yt_dlp

from loopbot import remixatron

ytdl = yt_dlp.YoutubeDL({
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',  # bind to ipv4 since ipv6 addresses cause issues sometimes # (their comment, not mine. TODO - is this accurate?)
})

ffmpeg_options = {
    'options': '-vn',
}

async def ytdl_async_download_helper(url):
    data = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(url, download=True))
    assert data is not None
    # take first item from playlist
    if 'entries' in data:
        data = data['entries'][0]
    filename = ytdl.prepare_filename(data)
    # TODO expose title, url, etc. also
    return filename

# https://stackoverflow.com/a/53996189/8762161
def jukebox_process_async_helper(input_file):
    loop = asyncio.get_event_loop()
    queue = asyncio.Queue[tuple[float, str]]()
    def on_progress(percentage: float, message: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, (percentage, message))
    async def get_progress() -> AsyncGenerator[tuple[float, str], None]:
        while True:
            yield await queue.get()
    def make_jukebox():
        return remixatron.InfiniteJukebox(filename=input_file, progress_callback=on_progress, do_async=True)
    jukebox_aio = loop.run_in_executor(None, make_jukebox)
    return jukebox_aio, get_progress()



# https://github.com/Rapptz/discord.py/blob/24b61a71c1e5e24c9f722eb95313debb2d873816/examples/basic_voice.py#L35-L54
class InfiniteJukeboxYTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, volume=0.5):
        super().__init__(source, volume)

    @classmethod
    async def from_url(cls, url):
        filename = await ytdl_async_download_helper(url=url)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options))


class LoopBotCog(commands.GroupCog, name='loopbot'):
    voice_client: Optional[discord.VoiceClient]
    bot: commands.Bot

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.voice_client = None
        super().__init__()

    @app_commands.command(name='invitelink')
    async def cmd_invite_link(self, interaction: discord.Interaction) -> None:
        from .util import bot_invite_link
        client_id = interaction.client.application_id
        assert client_id is not None
        invite_link = bot_invite_link(client_id=client_id, permissions='2150629376')
        await interaction.response.send_message(f'🔗 invite link: {invite_link}')

    @app_commands.command(name='joinvc')
    async def cmd_join_vc(self, interaction: discord.Interaction, channel: discord.VoiceChannel) -> None:
        await interaction.response.defer(thinking=True)
        if self.voice_client is not None:
            try:
                await self.voice_client.move_to(channel=channel)
                await interaction.followup.send(content=f'✅ moved to channel {channel.name}')
            except Exception as ex:
                print('failed to move to voice channel', ex)
                await interaction.followup.send(content=f'❌ unable to move to channel {channel.name}')
        else:
            try:
                self.voice_client = await channel.connect()
                await interaction.followup.send(content=f'✅ connected to channel {channel.name}')
            except Exception as ex:
                print('failed to connect to voice channel', ex)
                await interaction.followup.send(content=f'❌ unable to connect to channel {channel.name}')

    @app_commands.command(name='leavevc')
    async def cmd_leave_vc(self, interaction: discord.Interaction) -> None:
        if self.voice_client is None:
            await interaction.response.send_message(content='❌ not connected to any voice channel')
        else:
            await self.voice_client.disconnect()
            await interaction.response.send_message(content='✅ disconnected')

    @app_commands.command(name='play')
    async def cmd_play(self, interaction: discord.Interaction, url: str) -> None:
        assert self.voice_client is not None
        await interaction.response.send_message('downloading...')
        filename = await ytdl_async_download_helper(url=url)
        await interaction.edit_original_response(content='processing...')
        jukebox_aio, jukebox_aio_progress = jukebox_process_async_helper(filename)
        async for percent, message in jukebox_aio_progress:
            await interaction.edit_original_response(content=f'processing - {percent*100}% - "{message}"')
        jukebox = await jukebox_aio
        # await interaction.edit_original_response(content='playing...')
        # self.voice_client.play(player, after=lambda e: print(f'player error: {e}') if e else None)



# based on https://stackoverflow.com/a/63107461/8762161
class CogWithOwnPrefix(commands.Cog):
    def get_prefixes(self, bot: Union[commands.Bot, commands.AutoShardedBot], message: discord.Message) -> list[str]:
        return []

    async def cog_check(self, ctx) -> bool:
        return super().cog_check(ctx) and ctx.prefix in self.get_prefixes(ctx.bot, ctx.message)

class PingCommandCog(CogWithOwnPrefix):
    def get_prefixes(self, bot, message) -> list[str]:
        return super().get_prefixes(bot, message) + commands.when_mentioned(bot, message)


# from https://gist.github.com/AbstractUmbra/a9c188797ae194e592efe05fa129c57f#sync-command-example
class SyncMentionCog(PingCommandCog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command()
    @commands.guild_only()
    @commands.is_owner()
    async def sync(self, ctx: commands.Context, guilds: commands.Greedy[discord.Guild], spec: Optional[Literal["~", "*", "^"]] = None) -> None:
        if not guilds:
            if spec == "~":
                assert ctx.guild is not None
                synced = await self.bot.tree.sync(guild=ctx.guild)
            elif spec == "*":
                assert ctx.guild is not None
                self.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "^":
                assert ctx.guild is not None
                self.bot.tree.clear_commands(guild=ctx.guild)
                await self.bot.tree.sync(guild=ctx.guild)
                synced = []
            else:
                synced = await self.bot.tree.sync()
            await ctx.send(
                f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}"
            )
            return
        ret = 0
        for guild in guilds:
            try:
                await self.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                ret += 1
        await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")

def bot_command_prefix(bot: commands.Bot, message: discord.Message) -> list[str]:
    prefixes = []
    for cog in bot.cogs.values():
        if isinstance(cog, CogWithOwnPrefix):
            prefixes += cog.get_prefixes(bot, message)
    return prefixes

async def init_bot():
    intents = discord.Intents.none()
    intents.guilds = True
    intents.messages = True
    intents.message_content = False
    intents.voice_states = True
    bot = commands.Bot(command_prefix=bot_command_prefix, intents=intents)
    await bot.add_cog(LoopBotCog(bot))
    await bot.add_cog(SyncMentionCog(bot))
    return bot



