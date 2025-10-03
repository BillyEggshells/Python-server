import os
import asyncio
import sys
import threading
import socket
import struct
import time
import base64

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn
import websockets

# -------------------- Terminal colors --------------------
ANSI_COLORS = [
    "\033[91m",  # Red
    "\033[92m",  # Green
    "\033[93m",  # Yellow
    "\033[94m",  # Blue
    "\033[95m",  # Magenta
    "\033[96m",  # Cyan
    "\033[97m",  # White
]
ANSI_RESET = "\033[0m"

WEB_COLORS = [
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
]

# -------------------- Clear terminal --------------------
os.system('cls' if os.name == 'nt' else 'clear')

app = FastAPI()
clients = set()
client_info = {}  # websocket -> {"id": int, "color_idx": int}
next_user_id = 1
lock = asyncio.Lock()

# -------------------- IP & color --------------------
def assign_color(user_id):
    return (user_id - 1) % len(ANSI_COLORS)

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

# -------------------- Password encoding --------------------
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

def base36_encode(number: int) -> str:
    if number == 0:
        return "0"
    result = []
    while number:
        number, rem = divmod(number, 36)
        result.append(ALPHABET[rem])
    return ''.join(reversed(result))

def base36_decode(s: str) -> int:
    n = 0
    for ch in s:
        n = n * 36 + ALPHABET.index(ch)
    return n

def encode_ip_port(ip: str, port: int) -> str:
    ip_int = struct.unpack("!I", socket.inet_aton(ip))[0]
    combined = (ip_int << 16) + port
    return base36_encode(combined)[:14]

def decode_ip_port(code: str):
    combined = base36_decode(code)
    port = combined & 0xFFFF
    ip_int = combined >> 16
    ip = socket.inet_ntoa(struct.pack("!I", ip_int))
    return ip, port

# -------------------- XOR “encryption” --------------------
ENCRYPTION_KEY = "supersecret"

def encrypt_message(message: str, key=ENCRYPTION_KEY) -> str:
    key_len = len(key)
    encrypted_bytes = bytes([b ^ ord(key[i % key_len]) for i, b in enumerate(message.encode())])
    return base64.b64encode(encrypted_bytes).decode()

def decrypt_message(message: str, key=ENCRYPTION_KEY) -> str:
    try:
        encrypted_bytes = base64.b64decode(message)
        decrypted_bytes = bytes([b ^ ord(key[i % len(key)]) for i, b in enumerate(encrypted_bytes)])
        return decrypted_bytes.decode()
    except:
        return message

# -------------------- FastAPI Web --------------------
@app.get("/", response_class=HTMLResponse)
async def get():
    return f"""
<!DOCTYPE html>
<html>
<head>
<title>Terminal Style Chat</title>
<style>
body {{
    background: black;
    color: #0f0;
    font-family: monospace;
    margin: 0; padding: 10px;
    height: 100vh;
    display: flex;
    flex-direction: column;
}}
#chat {{
    flex-grow: 1;
    overflow-y: auto;
    white-space: pre-wrap;
    padding-bottom: 10px;
}}
#inputLine {{
    display: flex;
}}
#prompt {{
    user-select: none;
    padding-right: 5px;
}}
#msg {{
    flex-grow: 1;
    background: black;
    border: none;
    color: #0f0;
    font-family: monospace;
    font-size: 1em;
    outline: none;
    caret-color: #0f0;
}}
#msg:focus {{
    border-bottom: 1px solid #0f0;
    animation: blink 1s step-end infinite;
}}
@keyframes blink {{
    from, to {{ border-color: transparent }}
    50% {{ border-color: #0f0 }}
}}
.usercolor {{
    font-weight: bold;
    margin-right: 4px;
}}
</style>
</head>
<body>
<div id="chat"></div>
<div id="inputLine">
    <div id="prompt">&gt;</div>
    <input id="msg" autocomplete="off" autofocus />
</div>
<script>
const chat = document.getElementById('chat');
const input = document.getElementById('msg');
let ws;
const USER_COLORS = {WEB_COLORS};

function parseMessage(message) {{
    const colonPos = message.indexOf(':');
    if (colonPos > -1) {{
        const colorIdx = parseInt(message.slice(0, colonPos));
        const text = message.slice(colonPos + 1);
        const color = USER_COLORS[colorIdx % USER_COLORS.length] || 'white';
        if (text.trim() === '') {{
            return `<span style="color:${{color}}">|</span>`;
        }} else {{
            return `<span style="color:${{color}}">|</span> ${{text}}`;
        }}
    }}
    return message;
}}

function appendMessage(message) {{
    chat.innerHTML += parseMessage(message) + '\\n';
    chat.scrollTop = chat.scrollHeight;
}}

function connect() {{
    const protocol = location.protocol === 'https:' ? 'wss://' : 'ws://';
    ws = new WebSocket(protocol + location.host + '/ws');
    ws.onopen = () => appendMessage('[Connected to server]');
    ws.onmessage = (event) => appendMessage(event.data);
    ws.onclose = () => appendMessage('[Disconnected]');
    ws.onerror = () => appendMessage('[Connection error]');
}}

input.addEventListener('keydown', e => {{
    if (e.key === 'Enter') {{
        e.preventDefault();
        const msg = input.value.trim();
        if (msg !== "") {{
            appendMessage('| ' + msg);
            ws.send(msg);
            input.value = '';
        }}
    }}
}});

connect();
</script>
</body>
</html>
"""

# -------------------- WebSocket --------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global next_user_id
    await websocket.accept()
    async with lock:
        user_id = next_user_id
        next_user_id += 1
        color_idx = assign_color(user_id)
        client_info[websocket] = {"id": user_id, "color_idx": color_idx}
    clients.add(websocket)

    join_msg = f"{color_idx}:"
    await broadcast(join_msg, exclude=None)

    try:
        while True:
            data = await websocket.receive_text()
            user = client_info.get(websocket)
            if user:
                enc_msg = encrypt_message(data)
                msg = f"{user['color_idx']}:{enc_msg}"
                await broadcast(msg, exclude=websocket)
    except WebSocketDisconnect:
        clients.discard(websocket)
        user = client_info.pop(websocket, None)
        if user:
            leave_msg = f"{user['color_idx']}:"
            await broadcast(leave_msg, exclude=None)

async def broadcast(message, exclude=None):
    to_remove = []
    for client in clients:
        if client == exclude:
            continue
        try:
            await client.send_text(message)
        except:
            to_remove.append(client)
    for client in to_remove:
        clients.discard(client)
        client_info.pop(client, None)

# -------------------- Terminal client --------------------
def color_message_terminal(message):
    if ':' in message:
        color_idx_str, text = message.split(':', 1)
        try:
            color_idx = int(color_idx_str)
            color = ANSI_COLORS[color_idx % len(ANSI_COLORS)]
            if text.strip() == "":
                return f"{color}|{ANSI_RESET}"
            else:
                try:
                    text = decrypt_message(text)
                except:
                    pass
                return f"{color}|{ANSI_RESET} {text}"
        except:
            pass
    return message

async def terminal_client(uri):
    print(f"Connecting to server at {uri} ...")
    try:
        async with websockets.connect(uri) as websocket:
            user_color_idx = None
            user_color = None
            print("Connected! Type messages, Ctrl+C to quit.")

            prompt_lock = threading.Lock()

            async def recv():
                nonlocal user_color_idx, user_color
                try:
                    async for message in websocket:
                        if user_color_idx is None:
                            colonPos = message.find(':')
                            if colonPos > 0:
                                try:
                                    idx = int(message[:colonPos])
                                    user_color_idx = idx
                                    user_color = ANSI_COLORS[user_color_idx % len(ANSI_COLORS)]
                                except:
                                    pass
                        with prompt_lock:
                            print("\r" + color_message_terminal(message))
                            if user_color:
                                print(f"{user_color}>{ANSI_RESET} ", end="", flush=True)
                            else:
                                print("> ", end="", flush=True)
                except websockets.ConnectionClosed:
                    print("\nDisconnected from server.")
                    return

            recv_task = asyncio.create_task(recv())
            loop = asyncio.get_event_loop()

            def input_thread():
                while True:
                    with prompt_lock:
                        prompt = f"{user_color}>{ANSI_RESET} " if user_color else "> "
                    try:
                        msg = input(prompt)
                        asyncio.run_coroutine_threadsafe(websocket.send(msg), loop)
                    except EOFError:
                        break

            thread = threading.Thread(target=input_thread, daemon=True)
            thread.start()

            await recv_task
    except Exception as e:
        print("Connection error:", e)

# -------------------- Helper --------------------
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def choose_port(default_port=8000):
    while True:
        port_str = input(f"Enter port to use (default {default_port}): ").strip()
        if port_str == "":
            port = default_port
        else:
            if not port_str.isdigit():
                print("Please enter a valid number.")
                continue
            port = int(port_str)
            if not (1024 <= port <= 65535):
                print("Port must be 1024-65535.")
                continue

        if is_port_in_use(port):
            print(f"Port {port} is already in use.")
            choice = input("Do you want to join as a client instead? (y/n): ").strip().lower()
            if choice == 'y':
                return port, True
            else:
                print("Try another port.")
        else:
            return port, False

def input_ip_port_or_password():
    inp = input("Enter connection password (encoded IP+port) OR IP (e.g. 192.168.x.x or localhost): ").strip()
    if not inp:
        inp = "localhost"
    if all(c in ALPHABET for c in inp) and len(inp) <= 14:
        try:
            ip, port = decode_ip_port(inp)
            print(f"Decoded password to IP: {ip}, port: {port}")
            return ip, port
        except:
            print("Invalid password, enter IP and port manually.")
    ip = inp
    port_str = input("Enter server port (default 8000): ").strip()
    port = 8000
    if port_str.isdigit():
        port = int(port_str)
    return ip, port

# -------------------- Main --------------------
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() == "--terminal":
        ip, port = input_ip_port_or_password()
        asyncio.run(terminal_client(f"ws://{ip}:{port}/ws"))
    else:
        port, join_as_client = choose_port(8000)
        ip = get_local_ip()
        password = encode_ip_port(ip, port)
        print(f"\nServer starting on {ip}:{port} ...")
        print(f"Share this password with others: {password}")
        print(f"Clients can connect via ws://{ip}:{port}/ws or open http://{ip}:{port}/ in browser\n")

        def run_uvicorn():
            uvicorn.run(app, host="0.0.0.0", port=port)
        server_thread = threading.Thread(target=run_uvicorn, daemon=True)
        server_thread.start()

        time.sleep(1)
        asyncio.run(terminal_client(f"ws://{ip}:{port}/ws"))
