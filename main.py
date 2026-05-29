import discord
from discord.ext import commands
import virtualbox
import json
import asyncio
import time
import uuid
import subprocess

# config & vm setup
with open('config.json', 'r') as g:
    CONFIG = json.load(g)

with open('scancodes.json', 'r') as f:
    KEY_MAP = json.load(f)

VM_NAME = CONFIG.get('vmname')
BOT_TOKEN = CONFIG.get('token')

vbox_manager = virtualbox.Manager()
vbox = vbox_manager.get_virtualbox()
machine = vbox.find_machine(VM_NAME)
session = virtualbox.Session()
machine.lock_machine(session, virtualbox.library.LockType.shared)

# dc bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# vm core logic
def get_key_scancode(keyname):
    return KEY_MAP.get(keyname.lower(), None)

def split_into_keys(scancode_list):
    keys = []
    i = 0
    while i < len(scancode_list):
        if scancode_list[i] == 224 and i + 1 < len(scancode_list):
            keys.append([224, scancode_list[i + 1]])
            i += 2
        else:
            keys.append([scancode_list[i]])
            i += 1
    return keys

def generate_break_code(key_sequence):
    if len(key_sequence) == 2 and key_sequence[0] == 224:
        return [224, key_sequence[1] + 128]
    return [key_sequence[0] + 128]

def press_key(scancode_input, shift=False):
    if not scancode_input: return
    scancode_list = scancode_input if isinstance(scancode_input, list) else [scancode_input]
    if shift: session.console.keyboard.put_scancodes([42])
    session.console.keyboard.put_scancodes(scancode_list)
    time.sleep(0.05)
    keys = split_into_keys(scancode_list)
    for key in reversed(keys):
        session.console.keyboard.put_scancodes(generate_break_code(key))
    if shift: session.console.keyboard.put_scancodes([170])

def move_mouse(x, y):
    session.console.mouse.put_mouse_event(dx=x, dy=y, dz=0, dw=0, button_state=0)

def click_mouse(type):
    session.console.mouse.put_mouse_event(dx=0, dy=0, dz=0, dw=0, button_state=type)
    session.console.mouse.put_mouse_event(dx=0, dy=0, dz=0, dw=0, button_state=0)

def scroll_mouse(num):
    session.console.mouse.put_mouse_event(dx=0, dy=0, dz=num, dw=0, button_state=0)

def revert_vm():
    global session
    try:
        if session.state == virtualbox.library.SessionState.locked:
            session.unlock_machine()
            
        print("Shutting down VM for revert...")
        subprocess.run(['VBoxManage', 'controlvm', VM_NAME, 'poweroff'], check=True, capture_output=True)
        
        print(f"Reverting '{VM_NAME}' to latest snapshot...")
        subprocess.run(['VBoxManage', 'snapshot', VM_NAME, 'restorecurrent'], check=True, capture_output=True)
        
        add_sys_message("Reverted to latest snapshot successfully!")
        
        machine = vbox.find_machine(VM_NAME)
        machine.lock_machine(session, virtualbox.library.LockType.shared)
        
    except subprocess.CalledProcessError as e:
        print(f"VBoxManage error: {e.stderr.decode().strip()}")
        add_sys_message("Revert failed due to VBoxManage error.")
    except Exception as e:
        print(f"Error reverting: {e}")
        add_sys_message("Revert failed.")
# dc commands (async)
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.command()
async def key(ctx, key_name: str):
    code = get_key_scancode(key_name)
    if code:
        await asyncio.to_thread(press_key, code)
        await ctx.send(f"Pressed {key_name}")
    else:
        await ctx.send("Unknown key.")

@bot.command()
async def type(ctx, *, text: str):
    def typing_task():
        for char in text:
            is_upper = char.isupper()
            scancode = get_key_scancode(char.lower())
            if scancode: press_key(scancode, shift=is_upper)
    await asyncio.to_thread(typing_task)
    await ctx.send(f"Typed: {text}")

@bot.command()
async def move(ctx, x: int, y: int):
    await asyncio.to_thread(move_mouse, x, y)
    await ctx.send(f"Moved mouse to {x}, {y}")

@bot.command()
async def rebertical(ctx):
    await ctx.send("Initiating VM revert...")
    await asyncio.to_thread(revert_vm)
    await ctx.send("VM reverted and ready.")
@bot.command()
async def wait(ctx, seconds: int):
    if seconds > 30:
        await ctx.send("I can only wait for up to 30 seconds to keep the event loop healthy.")
        return
    await ctx.send(f"Waiting for {seconds} seconds...")
    await asyncio.sleep(seconds)
    await ctx.send("Resuming!")

@bot.command()
async def click(ctx, btn: str = "left"):
    btns = {"left": 1, "right": 2, "middle": 4}
    code = btns.get(btn.lower(), 1)
    await asyncio.to_thread(click_mouse, code)
    await ctx.send(f"Clicked {btn}")

bot.run(BOT_TOKEN)
