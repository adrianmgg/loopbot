from typing import Literal, Optional, Union
import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path


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
        await interaction.response.send_message(f'invite link: {invite_link}')

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



