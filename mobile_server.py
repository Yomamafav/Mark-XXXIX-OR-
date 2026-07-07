import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

_log_entries: list[str] = []
_log_lock = threading.Lock()
_command_callback: Callable | None = None
_state = {"value": "OFFLINE"}

MOBILE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
  <title>JARVIS Remote</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0;}
    body{background:#07090f;color:#b8cce8;font-family:'Courier New',monospace;height:100dvh;display:flex;flex-direction:column;overflow:hidden;}
    #hdr{background:#080e1a;border-bottom:1px solid #162840;padding:10px 16px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}
    #title{color:#3da8f5;font-size:15px;font-weight:bold;letter-spacing:3px;}
    #badge{padding:3px 10px;border-radius:10px;font-size:11px;font-weight:bold;letter-spacing:1px;transition:all .3s;}
    .LISTENING{background:#071a0e;color:#3de87a;border:1px solid #3de87a;}
    .SPEAKING{background:#07071a;color:#7088ff;border:1px solid #7088ff;}
    .THINKING{background:#1a0f05;color:#f0a030;border:1px solid #f0a030;}
    .OFFLINE{background:#1a0707;color:#f03030;border:1px solid #f03030;}
    #log{flex:1;overflow-y:auto;padding:12px 14px;display:flex;flex-direction:column;gap:7px;scroll-behavior:smooth;}
    .e{padding:8px 12px;border-radius:8px;font-size:13px;line-height:1.45;max-width:88%;word-break:break-word;}
    .you{background:#071830;border:1px solid #1a4870;color:#90c8f8;align-self:flex-end;}
    .jarvis{background:#07180e;border:1px solid #1a5030;color:#70d890;align-self:flex-start;}
    .sys{background:#141005;border:1px solid #302808;color:#887730;align-self:center;font-size:11px;font-style:italic;}
    .alert{background:#1a0505;border:1px solid #cc2020;color:#ff5555;align-self:center;font-weight:bold;animation:alertpulse 2s ease-out;}
    #bar{background:#080e1a;border-top:1px solid #162840;padding:10px 14px;display:flex;gap:8px;align-items:center;flex-shrink:0;}
    #inp{flex:1;background:#050a12;border:1px solid #162840;border-radius:18px;color:#b8cce8;font-family:inherit;font-size:14px;padding:9px 15px;outline:none;}
    #inp:focus{border-color:#3da8f5;}
    #inp::placeholder{color:#2a4060;}
    button{background:none;border:none;cursor:pointer;border-radius:50%;width:42px;height:42px;display:flex;align-items:center;justify-content:center;font-size:19px;flex-shrink:0;}
    #snd{background:#062040;}
    #snd:active{background:#0a3060;}
    #mic{background:#062015;}
    #mic:active,#mic.on{background:#3a0808;animation:pulse 1s infinite;}
    @keyframes pulse{0%,100%{opacity:1;}50%{opacity:.55;}}
    @keyframes alertpulse{0%{box-shadow:0 0 12px #cc2020;}100%{box-shadow:none;}}
    ::-webkit-scrollbar{width:3px;}
    ::-webkit-scrollbar-track{background:transparent;}
    ::-webkit-scrollbar-thumb{background:#162840;border-radius:3px;}
  </style>
</head>
<body>
<div id="hdr">
  <div id="title">&#9889; JARVIS</div>
  <div id="badge" class="OFFLINE">OFFLINE</div>
</div>
<div id="log"></div>
<div id="bar">
  <input id="inp" type="text" placeholder="Send a command&#8230;" autocomplete="off" autocorrect="off" spellcheck="false">
  <button id="mic" title="Voice">&#127908;</button>
  <button id="snd" title="Send">&#10148;</button>
</div>
<script>
const logEl=document.getElementById('log'),
      inp=document.getElementById('inp'),
      badge=document.getElementById('badge'),
      snd=document.getElementById('snd'),
      mic=document.getElementById('mic');
let seen=0, micOn=false;

function addEntry(t){
  const d=document.createElement('div');
  if(t.startsWith('You: ')){d.className='e you';d.textContent=t.slice(5);}
  else if(t.startsWith('Jarvis: ')){d.className='e jarvis';d.textContent=t.slice(8);}
  else if(t.startsWith('ALERT: ')){d.className='e alert';d.textContent='⚠ '+t.slice(7);playAlert();}
  else{d.className='e sys';d.textContent=t;}
  logEl.appendChild(d);
  logEl.scrollTop=logEl.scrollHeight;
}
function playAlert(){
  try{
    const ctx=new(window.AudioContext||window.webkitAudioContext)();
    [0,150,300].forEach((delay,i)=>{
      const o=ctx.createOscillator(),g=ctx.createGain();
      o.connect(g);g.connect(ctx.destination);
      o.type='sine';o.frequency.value=i===2?1046:880;
      const t=ctx.currentTime+delay/1000;
      g.gain.setValueAtTime(0.25,t);
      g.gain.exponentialRampToValueAtTime(0.001,t+0.25);
      o.start(t);o.stop(t+0.25);
    });
  }catch(e){}
}

async function poll(){
  try{
    const [lr,sr]=await Promise.all([fetch('/log?since='+seen),fetch('/status')]);
    const ld=await lr.json();
    if(ld.entries&&ld.entries.length){ld.entries.forEach(addEntry);seen=ld.total;}
    const sd=await sr.json();
    const s=sd.state||'OFFLINE';
    badge.textContent=s;badge.className=s;
  }catch(e){badge.textContent='OFFLINE';badge.className='OFFLINE';}
}

async function send(t){
  t=(t||'').trim();if(!t)return;
  inp.value='';
  try{await fetch('/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});}catch(e){}
}

snd.addEventListener('click',()=>send(inp.value));
inp.addEventListener('keydown',e=>{if(e.key==='Enter')send(inp.value);});

const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
if(SR){
  const r=new SR();r.continuous=false;r.interimResults=false;
  r.onresult=e=>{const t=e.results[0][0].transcript;inp.value=t;send(t);};
  r.onend=()=>{micOn=false;mic.classList.remove('on');};
  r.onerror=()=>{micOn=false;mic.classList.remove('on');};
  mic.addEventListener('click',()=>{
    if(micOn){r.stop();}else{r.start();micOn=true;mic.classList.add('on');}
  });
}else{mic.style.opacity='0.35';mic.title='Voice not supported (use Chrome)';}

setInterval(poll,1500);poll();
</script>
</body>
</html>"""


class _Handler(BaseHTTPRequestHandler):

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", MOBILE_HTML.encode("utf-8"))

        elif self.path.startswith("/log"):
            since = 0
            if "since=" in self.path:
                try:
                    since = int(self.path.split("since=")[1].split("&")[0])
                except (ValueError, IndexError):
                    since = 0
            with _log_lock:
                entries = list(_log_entries)
            total = len(entries)
            new_entries = entries[max(0, since):] if since < total else []
            body = json.dumps({"entries": new_entries, "total": total}).encode()
            self._send(200, "application/json", body)

        elif self.path == "/status":
            body = json.dumps({"state": _state["value"]}).encode()
            self._send(200, "application/json", body)

        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self) -> None:
        if self.path == "/send":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
                text = str(data.get("text", "")).strip()
                if text and _command_callback:
                    _command_callback(text)
                    self._send(200, "application/json", b'{"ok":true}')
                else:
                    self._send(400, "application/json", b'{"ok":false}')
            except Exception as exc:
                err = json.dumps({"ok": False, "error": str(exc)}).encode()
                self._send(400, "application/json", err)
        else:
            self._send(404, "text/plain", b"Not found")

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, *args) -> None:
        pass


def push_log(entry: str) -> None:
    with _log_lock:
        _log_entries.append(entry)


def set_status(state: str) -> None:
    _state["value"] = state


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _try_upnp(port: int) -> str | None:
    import urllib.request
    import urllib.parse
    import xml.etree.ElementTree as ET

    # --- SSDP discovery ---
    SSDP_ADDR = "239.255.255.250"
    SSDP_PORT = 1900
    msg = (
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
        'MAN: "ssdp:discover"\r\n'
        "MX: 2\r\n"
        "ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n\r\n"
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.settimeout(3)
    try:
        sock.sendto(msg.encode(), (SSDP_ADDR, SSDP_PORT))
        location = None
        while True:
            try:
                data, _ = sock.recvfrom(2048)
                for line in data.decode("utf-8", errors="ignore").splitlines():
                    if line.upper().startswith("LOCATION:"):
                        location = line.split(":", 1)[1].strip()
                        break
                if location:
                    break
            except socket.timeout:
                break
    finally:
        sock.close()

    if not location:
        print("[Mobile] ⚠️  UPnP: no gateway found")
        return None

    # --- Fetch device XML ---
    try:
        with urllib.request.urlopen(location, timeout=5) as r:
            xml_data = r.read()
        root = ET.fromstring(xml_data)
    except Exception as e:
        print(f"[Mobile] ⚠️  UPnP: device fetch failed: {e}")
        return None

    # --- Find WANIPConnection or WANPPPConnection control URL ---
    parsed_loc = urllib.parse.urlparse(location)
    base = f"{parsed_loc.scheme}://{parsed_loc.netloc}"
    control_url = None
    service_type = None
    for svc in root.iter():
        tag = svc.tag.split("}")[-1]
        if tag == "service":
            st  = next((c.text for c in svc if c.tag.split("}")[-1] == "serviceType"), "") or ""
            cu  = next((c.text for c in svc if c.tag.split("}")[-1] == "controlURL"),  "") or ""
            if ("WANIPConnection" in st or "WANPPPConnection" in st) and cu:
                control_url  = base + cu if cu.startswith("/") else base + "/" + cu
                service_type = st.strip()
                break

    if not control_url:
        print("[Mobile] ⚠️  UPnP: no WAN service found")
        return None

    def _soap(action: str, body: str) -> bytes:
        envelope = (
            '<?xml version="1.0"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            f"<s:Body>{body}</s:Body></s:Envelope>"
        )
        req = urllib.request.Request(
            control_url,
            data=envelope.encode(),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f'"{service_type}#{action}"',
            },
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.read()

    # --- Get external IP ---
    external_ip = None
    try:
        ip_resp = _soap(
            "GetExternalIPAddress",
            f'<u:GetExternalIPAddress xmlns:u="{service_type}"/>',
        )
        for el in ET.fromstring(ip_resp).iter():
            if "NewExternalIPAddress" in el.tag and el.text:
                external_ip = el.text.strip()
                break
    except Exception as e:
        print(f"[Mobile] ⚠️  UPnP: get IP failed: {e}")

    # --- Add port mapping ---
    local_ip = _get_local_ip()
    try:
        _soap(
            "AddPortMapping",
            f'<u:AddPortMapping xmlns:u="{service_type}">'
            "<NewRemoteHost></NewRemoteHost>"
            f"<NewExternalPort>{port}</NewExternalPort>"
            "<NewProtocol>TCP</NewProtocol>"
            f"<NewInternalPort>{port}</NewInternalPort>"
            f"<NewInternalClient>{local_ip}</NewInternalClient>"
            "<NewEnabled>1</NewEnabled>"
            "<NewPortMappingDescription>JARVIS Remote</NewPortMappingDescription>"
            "<NewLeaseDuration>86400</NewLeaseDuration>"
            "</u:AddPortMapping>",
        )
    except Exception as e:
        print(f"[Mobile] ⚠️  UPnP: port mapping failed: {e}")

    return external_ip


def start(command_callback: Callable, port: int = 5252) -> tuple[str, int]:
    global _command_callback
    _command_callback = command_callback
    server = HTTPServer(("0.0.0.0", port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    local_ip = _get_local_ip()
    print(f"[Mobile] 📱 Local:  http://{local_ip}:{port}")
    threading.Thread(target=_announce_public, args=(port,), daemon=True).start()
    return local_ip, port


def _announce_public(port: int) -> None:
    public_ip = _try_upnp(port)
    if public_ip:
        print(f"[Mobile] 🌐 Public: http://{public_ip}:{port}  ← use this off-network")
