#!/usr/bin/env python3
"""
JARVIS (all-in-one) - Android phone assistant + HUD screen (Termux + Gemini free tier)
No pip packages needed beyond Python itself.

Setup (Termux):
  pkg install python termux-api
  termux-setup-storage
  1) Get a FREE key (no card): https://aistudio.google.com/apikey
  2) export GEMINI_API_KEY="your-key"
  3) python jarvis_all.py            -> HUD screen: open Chrome at http://localhost:8080
     python jarvis_all.py --text     -> type commands in terminal
     python jarvis_all.py --voice    -> terminal voice mode, say "Jarvis ..."

If you get a "model not found" error, open AI Studio, pick a current Flash model
and run:  export GEMINI_MODEL="that-model-name"
"""
import os, sys, json, subprocess, threading, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
WAKE = "jarvis"
TEXT_MODE = "--text" in sys.argv
VOICE_MODE = "--voice" in sys.argv

APPS = {
    "youtube": "com.google.android.youtube",
    "whatsapp": "com.whatsapp",
    "facebook": "com.facebook.katana",
    "instagram": "com.instagram.android",
    "tiktok": "com.zhiliaoapp.musically",
    "chrome": "com.android.chrome",
    "camera": "com.android.camera",
    "settings": "com.android.settings",
    "maps": "com.google.android.apps.maps",
    "gmail": "com.google.android.gm",
    "spotify": "com.spotify.music",
    "capcut": "com.lemon.lvoverseas",
}

SYSTEM = (
    "You are JARVIS, a helpful voice assistant living on the user's Android phone. "
    "The user speaks Sinhala or English; reply in the language they used. "
    "Keep spoken replies to 1-2 short sentences. Use the provided functions to act on the phone. "
    "For calls and SMS the user is asked to confirm automatically, so just call the function."
)

def sh(*cmd, inp=None):
    r = subprocess.run(cmd, capture_output=True, text=True, input=inp)
    return (r.stdout or r.stderr).strip()

def speak(text):
    print("JARVIS:", text)
    sh("termux-tts-speak", text)

def listen():
    if TEXT_MODE:
        return input("You: ").strip()
    return sh("termux-speech-to-text")

def confirm(msg):
    speak(msg + " තහවුරු කරන්න, yes කියන්න.")
    ans = listen().lower()
    return any(w in ans for w in ("yes", "ok", "හරි", "ඔව්", "ඔව"))

# ---------- Actions ----------
def act_flashlight(on):
    sh("termux-torch", "on" if on else "off"); return "done"

def act_call(number):
    if not confirm(f"{number} ට call කරන්නද?"): return "cancelled by user"
    sh("termux-telephony-call", number); return "calling"

def act_sms(number, message):
    if not confirm(f"{number} ට SMS යවන්නද?"): return "cancelled by user"
    sh("termux-sms-send", "-n", number, message); return "sent"

def act_open_app(name):
    pkg = APPS.get(name.lower().strip(), name)
    sh("monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1")
    return f"opened {name}"

def act_open_url(url):
    sh("termux-open-url", url); return "opened"

def act_volume(level):  # 0-15
    sh("termux-volume", "music", str(int(level))); return "ok"

def act_battery():
    return sh("termux-battery-status")

def act_location():
    return sh("termux-location", "-p", "network")

def act_notify(title, text):
    sh("termux-notification", "--title", title, "--content", text); return "ok"

def act_clipboard_set(text):
    sh("termux-clipboard-set", text); return "copied"

def act_wifi(on):
    sh("termux-wifi-enable", "true" if on else "false"); return "ok"

def act_brightness(level):  # 0-255
    sh("termux-brightness", str(int(level))); return "ok"

def act_photo():
    path = os.path.expanduser("~/storage/dcim/jarvis.jpg")
    sh("termux-camera-photo", "-c", "0", path); return f"saved {path}"

def act_alarm(hour, minute, label="Jarvis"):
    sh("am", "start", "-a", "android.intent.action.SET_ALARM",
       "--ei", "android.intent.extra.alarm.HOUR", str(hour),
       "--ei", "android.intent.extra.alarm.MINUTES", str(minute),
       "--es", "android.intent.extra.alarm.MESSAGE", label,
       "--ez", "android.intent.extra.alarm.SKIP_UI", "true")
    return f"alarm set {hour:02d}:{minute:02d}"

ACTIONS = {
    "flashlight": lambda a: act_flashlight(a["on"]),
    "call": lambda a: act_call(a["number"]),
    "send_sms": lambda a: act_sms(a["number"], a["message"]),
    "open_app": lambda a: act_open_app(a["name"]),
    "open_url": lambda a: act_open_url(a["url"]),
    "set_volume": lambda a: act_volume(a["level"]),
    "battery": lambda a: act_battery(),
    "location": lambda a: act_location(),
    "notify": lambda a: act_notify(a["title"], a["text"]),
    "copy_text": lambda a: act_clipboard_set(a["text"]),
    "wifi": lambda a: act_wifi(a["on"]),
    "brightness": lambda a: act_brightness(a["level"]),
    "take_photo": lambda a: act_photo(),
    "set_alarm": lambda a: act_alarm(a["hour"], a["minute"], a.get("label", "Jarvis")),
}


def tool(name, desc, props=None, req=None):
    d = {"name": name, "description": desc}
    if props:
        d["parameters"] = {"type": "object", "properties": props, "required": req or []}
    return d

DECLS = [
    tool("flashlight", "Turn flashlight on/off", {"on": {"type": "boolean"}}, ["on"]),
    tool("call", "Phone call a number", {"number": {"type": "string"}}, ["number"]),
    tool("send_sms", "Send an SMS", {"number": {"type": "string"}, "message": {"type": "string"}}, ["number", "message"]),
    tool("open_app", "Open an app by name (youtube, whatsapp, facebook, ...) or package", {"name": {"type": "string"}}, ["name"]),
    tool("open_url", "Open a URL or a search in the browser", {"url": {"type": "string"}}, ["url"]),
    tool("set_volume", "Set media volume 0-15", {"level": {"type": "integer"}}, ["level"]),
    tool("battery", "Get battery status"),
    tool("location", "Get current location"),
    tool("notify", "Show a notification", {"title": {"type": "string"}, "text": {"type": "string"}}, ["title", "text"]),
    tool("copy_text", "Copy text to clipboard", {"text": {"type": "string"}}, ["text"]),
    tool("wifi", "Turn WiFi on/off", {"on": {"type": "boolean"}}, ["on"]),
    tool("brightness", "Set screen brightness 0-255", {"level": {"type": "integer"}}, ["level"]),
    tool("take_photo", "Take a photo with the back camera"),
    tool("set_alarm", "Set an alarm (24h time)", {"hour": {"type": "integer"}, "minute": {"type": "integer"}, "label": {"type": "string"}}, ["hour", "minute"]),
]


history = []

def call_gemini():
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM}]},
        "contents": history,
        "tools": [{"function_declarations": DECLS}],
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:300]
        if e.code == 429:
            return {"error": "free limit reached for now, try again later"}
        return {"error": f"HTTP {e.code}: {msg}"}

def think(user_text):
    history.append({"role": "user", "parts": [{"text": user_text}]})
    for _ in range(6):  # function-call loop
        data = call_gemini()
        if "error" in data:
            history.pop()
            return data["error"]
        try:
            content = data["candidates"][0]["content"]
        except (KeyError, IndexError):
            history.pop()
            return "No response."
        history.append(content)  # keep as-is (includes thought signatures)
        calls = [p["functionCall"] for p in content.get("parts", []) if "functionCall" in p]
        if not calls:
            return "".join(p.get("text", "") for p in content.get("parts", [])) or "Done."
        results = []
        for c in calls:
            try:
                out = ACTIONS[c["name"]](c.get("args", {}))
            except Exception as e:
                out = f"error: {e}"
            results.append({"functionResponse": {"name": c["name"], "response": {"result": str(out)}}})
        history.append({"role": "user", "parts": results})
    return "Done."


def confirm_dialog(msg):  # popup used in HUD mode (mic lives in the browser)
    out = sh("termux-dialog", "confirm", "-t", "Jarvis", "-i", msg)
    try:
        return json.loads(out).get("text") == "yes"
    except Exception:
        return False

PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>JARVIS</title><style>
:root{--c:#27e6ff;--bg:#02070d}
*{box-sizing:border-box}html,body{height:100%;margin:0;background:var(--bg);color:var(--c);
font-family:ui-monospace,Consolas,monospace;overflow:hidden}
body{display:flex;flex-direction:column;align-items:center;padding:env(safe-area-inset-top) 12px 12px;
background:radial-gradient(circle at 50% 38%,#06263a 0,var(--bg) 65%)}
h1{letter-spacing:.6em;font-size:14px;margin:18px 0 0;opacity:.8}
#status{font-size:12px;letter-spacing:.3em;margin-top:6px;opacity:.7;height:16px}
#hud{position:relative;width:min(78vw,320px);aspect-ratio:1;margin:22px 0 14px;flex:none}
.ring{position:absolute;inset:0;border-radius:50%;border:2px solid transparent;border-top-color:var(--c);
border-bottom-color:var(--c);animation:spin 8s linear infinite;box-shadow:0 0 18px #27e6ff55}
.r2{inset:9%;border-style:dashed;border-color:#27e6ff88;animation-duration:14s;animation-direction:reverse;box-shadow:none}
.r3{inset:18%;border-left-color:var(--c);border-right-color:var(--c);border-top-color:transparent;
border-bottom-color:transparent;animation-duration:5s}
#orb{position:absolute;inset:28%;border-radius:50%;border:0;cursor:pointer;color:var(--c);font:inherit;
background:radial-gradient(circle,#bff8ff 0,#27e6ff 35%,#0a6b85 75%,#04303f);box-shadow:0 0 40px #27e6ffaa;
animation:pulse 3s ease-in-out infinite}
body.listen #orb{animation-duration:.8s;box-shadow:0 0 70px #27e6ff}
body.think .ring{animation-duration:1.5s}body.think #orb{background:radial-gradient(circle,#fff0c0,#ffb627 40%,#6b4a0a)}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{50%{transform:scale(1.07)}}
#log{flex:1;width:100%;max-width:520px;overflow-y:auto;border:1px solid #27e6ff44;border-radius:8px;
padding:10px;font-size:14px;line-height:1.5;background:#03121c99}
.u{opacity:.65}.u:before{content:"> "}.j{color:#fff;margin-bottom:8px}.j:before{content:"JARVIS: ";color:var(--c)}
#bar{display:flex;gap:8px;width:100%;max-width:520px;margin-top:10px}
input{flex:1;background:#03121c;border:1px solid #27e6ff66;color:#fff;padding:10px;border-radius:8px;font:inherit}
button.s{background:transparent;border:1px solid var(--c);color:var(--c);border-radius:8px;padding:0 14px;font:inherit}
</style></head><body>
<h1>J.A.R.V.I.S</h1><div id="status">ONLINE</div>
<div id="hud"><div class="ring"></div><div class="ring r2"></div><div class="ring r3"></div>
<button id="orb">TAP</button></div>
<div id="log"></div>
<div id="bar"><input id="t" placeholder="type a command..."><button class="s" id="lang">SI</button>
<button class="s" id="go">SEND</button></div>
<script>
const $=id=>document.getElementById(id),log=$('log');let lang='si-LK',busy=false;
function add(c,t){const d=document.createElement('div');d.className=c;d.textContent=t;log.appendChild(d);log.scrollTop=1e9}
function state(s,t){document.body.className=s;$('status').textContent=t}
async function ask(text){
  if(!text||busy)return;busy=true;add('u',text);state('think','PROCESSING');
  try{const r=await fetch('/ask',{method:'POST',body:JSON.stringify({text})});
    add('j',(await r.json()).reply)}catch(e){add('j','connection error')}
  busy=false;state('','ONLINE')}
$('go').onclick=()=>{ask($('t').value.trim());$('t').value=''};
$('t').onkeydown=e=>{if(e.key==='Enter')$('go').click()};
$('lang').onclick=()=>{lang=lang==='si-LK'?'en-US':'si-LK';$('lang').textContent=lang==='si-LK'?'SI':'EN'};
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
$('orb').onclick=()=>{
  if(!SR){add('j','Speech not supported here. Open in Chrome.');return}
  const r=new SR();r.lang=lang;r.interimResults=false;
  r.onstart=()=>state('listen','LISTENING');
  r.onresult=e=>ask(e.results[0][0].transcript);
  r.onerror=e=>{state('','ONLINE');add('j','mic error: '+e.error)};
  r.onend=()=>{if(!busy)state('','ONLINE')};r.start()};
add('j','සූදානම්. Orb එක ඔබලා කතා කරන්න.');
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(PAGE.encode())
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        text = json.loads(self.rfile.read(n) or b"{}").get("text", "")
        reply = think(text)
        del history[:-20]
        threading.Thread(target=sh, args=("termux-tts-speak", reply), daemon=True).start()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"reply": reply}).encode())


def run_terminal():
    speak("Jarvis සූදානම්.")
    while True:
        try:
            heard = listen()
            if not heard:
                continue
            print("Heard:", heard)
            low = heard.lower()
            if not TEXT_MODE:
                if WAKE not in low:
                    continue
                heard = heard[low.index(WAKE) + len(WAKE):].strip(" ,.") or "hello"
            if heard.lower() in ("exit", "quit", "stop jarvis"):
                speak("Bye."); break
            speak(think(heard))
            del history[:-20]
        except KeyboardInterrupt:
            break

def main():
    global confirm
    if not API_KEY:
        print('Set your key first:  export GEMINI_API_KEY="..."'); return
    if TEXT_MODE or VOICE_MODE:
        run_terminal()
    else:
        confirm = confirm_dialog
        print("Jarvis HUD running -> open Chrome: http://localhost:8080")
        ThreadingHTTPServer(("127.0.0.1", 8080), H).serve_forever()

if __name__ == "__main__":
    main()
