import asyncio
import ssl
import certifi
import aiohttp
import discord
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

TOKEN = os.environ["DISCORD_TOKEN"]
WATCHED_USER_ID = int(os.environ["WATCHED_USER_ID"])
FORBIDDEN_ROLE_ID = int(os.environ["FORBIDDEN_ROLE_ID"])

intents = discord.Intents.default()
intents.members = True


async def main():
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)  # ✅ inside async context

    client = discord.Client(intents=intents, connector=connector)

    @client.event
    async def on_ready():
        log.info("Logged in as %s (id=%s)", client.user, client.user.id)
        log.info("Watching user_id=%s for role_id=%s", WATCHED_USER_ID, FORBIDDEN_ROLE_ID)

    @client.event
    async def on_member_update(before: discord.Member, after: discord.Member):
        if after.id != WATCHED_USER_ID:
            return
        forbidden_role = after.guild.get_role(FORBIDDEN_ROLE_ID)
        if forbidden_role is None:
            log.warning("Forbidden role id=%s not found in guild %s", FORBIDDEN_ROLE_ID, after.guild)
            return
        had_role = forbidden_role in before.roles
        has_role = forbidden_role in after.roles
        if not had_role and has_role:
            log.info(
                "User %s (%s) received forbidden role '%s' — removing it.",
                after.display_name,
                after.id,
                forbidden_role.name,
            )
            try:
                await after.remove_roles(forbidden_role, reason="Auto-demote: forbidden role assignment detected.")
                log.info("Successfully removed role '%s' from %s.", forbidden_role.name, after.display_name)
            except discord.Forbidden:
                log.error("Missing permissions to remove role '%s'.", forbidden_role.name)
            except discord.HTTPException as e:
                log.error("Failed to remove role: %s", e)

    async with client:
        await client.start(TOKEN)  # ✅ instead of client.run()


asyncio.run(main())