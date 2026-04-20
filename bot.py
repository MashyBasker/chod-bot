import asyncio
import ssl
import certifi
import aiohttp
import discord
import logging
import os
from datetime import timedelta
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

GIF_TIMEOUT = timedelta(minutes=10)
SPAM_TIMEOUT = timedelta(minutes=5)
SPAM_LIMIT = 10

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.messages = True


async def main():
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)  # ✅ inside async context

    client = discord.Client(intents=intents, connector=connector)
    message_count = 0

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

    @client.event
    async def on_message(message: discord.Message):
        nonlocal message_count

        if message.author.id != WATCHED_USER_ID:
            return

        message_count += 1
        log.info("Message count for watched user: %d/%d", message_count, SPAM_LIMIT)

        if message_count >= SPAM_LIMIT:
            message_count = 0
            member = message.guild.get_member(WATCHED_USER_ID)
            if member:
                log.info("User %s hit %d messages — timing out for %s.", member.display_name, SPAM_LIMIT, SPAM_TIMEOUT)
                try:
                    await member.timeout(SPAM_TIMEOUT, reason=f"Sent {SPAM_LIMIT} messages.")
                    log.info("Spam timeout applied to %s.", member.display_name)
                except discord.Forbidden:
                    log.error("Missing permissions to timeout %s.", member.display_name)
                except discord.HTTPException as e:
                    log.error("Failed to timeout member: %s", e)
                return

        is_gif = (
            any(a.filename.lower().endswith(".gif") for a in message.attachments)
            or any(e.type == "gifv" for e in message.embeds)
            or any(e.type == "image" and e.url and e.url.lower().endswith(".gif") for e in message.embeds)
            or "tenor.com/view/" in message.content
            or "giphy.com/gifs/" in message.content
        )

        if not is_gif:
            return

        member = message.guild.get_member(WATCHED_USER_ID)
        if member is None:
            return

        log.info("User %s (%s) sent a GIF — timing out for %s.", member.display_name, member.id, GIF_TIMEOUT)
        try:
            await member.timeout(GIF_TIMEOUT, reason="Sent a GIF.")
            log.info("Timeout applied to %s.", member.display_name)
        except discord.Forbidden:
            log.error("Missing permissions to timeout %s.", member.display_name)
        except discord.HTTPException as e:
            log.error("Failed to timeout member: %s", e)

    async with client:
        await client.start(TOKEN)  # ✅ instead of client.run()


asyncio.run(main())