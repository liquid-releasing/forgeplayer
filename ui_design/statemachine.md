Bruce, here’s the **state machine diagram** and the **config file format**—clean, deterministic, and ready for a code generator.  
I’m keeping everything modular and automation‑friendly so it maps directly onto your CLI architecture.

---

# 🔥 **STATE MACHINE DIAGRAM (ASCII + semantic states)**  
### *This is the authoritative lifecycle for the Premium‑authenticated audio downloader.*

```
                          ┌──────────────────────┐
                          │        Idle          │
                          └──────────┬───────────┘
                                     │
                                     │ login
                                     ▼
                          ┌──────────────────────┐
                          │    Authenticating    │
                          └──────────┬───────────┘
                                     │ success
                                     ▼
                          ┌──────────────────────┐
                          │    Authenticated     │
                          └──────────┬───────────┘
                                     │ get <video>
                                     ▼
                          ┌──────────────────────┐
                          │  Fetching Manifest   │
                          └──────────┬───────────┘
                        manifest ok  │   manifest fail
                                     ▼
                          ┌──────────────────────┐
                          │  Selecting Stream    │
                          └──────────┬───────────┘
                                     │ success
                                     ▼
                          ┌──────────────────────┐
                          │  Downloading Stream  │
                          └──────────┬───────────┘
                                     │ success
                                     ▼
                          ┌──────────────────────┐
                          │      Converting      │
                          └──────────┬───────────┘
                                     │ success
                                     ▼
                          ┌──────────────────────┐
                          │        Done          │
                          └──────────────────────┘


         ┌──────────────────────────────────────────────────────────────┐
         │                         FALLBACK PATH                        │
         └──────────────────────────────────────────────────────────────┘

Any failure in:  
- Fetching Manifest  
- Selecting Stream  
- Downloading Stream  
- Converting  

Triggers:

```
[Fallback Capture]
       │
       ▼
[Capturing System Audio]
       │
       ▼
[Converting]
       │
       ▼
[Done]
```

---

# 🔧 **STATE DEFINITIONS (for code generators)**

| State | Description | Entry Conditions | Exit Conditions |
|-------|-------------|------------------|-----------------|
| `Idle` | CLI waiting for user input | Program start | `login`, `get` |
| `Authenticating` | OAuth login flow | `login` | token acquired |
| `Authenticated` | Token valid + stored | login success | `get` |
| `FetchingManifest` | Requesting YouTube manifest | `get` | manifest ok/fail |
| `SelectingStream` | Choosing best audio stream | manifest ok | stream ok |
| `DownloadingStream` | Downloading audio-only stream | stream ok | download ok |
| `Converting` | Converting to MP3/WAV | download ok | convert ok |
| `FallbackCapture` | WASAPI loopback capture | any failure | capture ok |
| `Done` | Operation complete | convert ok | return to Idle |

---

# 🧱 **CONFIG FILE FORMAT (YAML)**  
### *This is the recommended format: human‑readable, code‑friendly, and stable.*

Save as:

```
~/.yt-audio-cli/config.yaml
```

---

## **🔧 Global Settings**
```yaml
version: 1

downloads:
  directory: "./downloads"
  overwrite: false
  filename_template: "{video_id}-{title}"

audio:
  default_format: "mp3"        # mp3 | wav | m4a
  bitrate: 320                 # kbps for mp3
  normalize: false             # future option
  trim_silence: false          # future option

oauth:
  token_path: "~/.yt-premium-auth.json"
  client_id: "YOUR_CLIENT_ID"
  client_secret: "YOUR_CLIENT_SECRET"
  redirect_uri: "http://localhost:8080/oauth/callback"
  scopes:
    - "https://www.googleapis.com/auth/youtube.readonly"
    - "https://www.googleapis.com/auth/userinfo.profile"

fallback:
  enabled: true
  capture_device: "default"    # WASAPI loopback
  capture_format: "wav"
  auto_trigger: true           # fallback on failure

logging:
  level: "info"                # debug | info | warn | error
  file: "~/.yt-audio-cli/logs.txt"

network:
  retries: 3
  timeout_seconds: 10
```

---

# 🧩 **CONFIG FILE FORMAT (JSON)**  
### *If you want a machine‑only version.*

```json
{
  "version": 1,
  "downloads": {
    "directory": "./downloads",
    "overwrite": false,
    "filename_template": "{video_id}-{title}"
  },
  "audio": {
    "default_format": "mp3",
    "bitrate": 320,
    "normalize": false,
    "trim_silence": false
  },
  "oauth": {
    "token_path": "~/.yt-premium-auth.json",
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "redirect_uri": "http://localhost:8080/oauth/callback",
    "scopes": [
      "https://www.googleapis.com/auth/youtube.readonly",
      "https://www.googleapis.com/auth/userinfo.profile"
    ]
  },
  "fallback": {
    "enabled": true,
    "capture_device": "default",
    "capture_format": "wav",
    "auto_trigger": true
  },
  "logging": {
    "level": "info",
    "file": "~/.yt-audio-cli/logs.txt"
  },
  "network": {
    "retries": 3,
    "timeout_seconds": 10
  }
}
```

---

# 🏁 **You now have:**

### ✔ A complete state machine diagram  
### ✔ A full config file format (YAML + JSON)  
### ✔ Both are code‑generator‑ready  
### ✔ Both map directly to your folder structure and file stubs  

If you want, I can now generate:

### ✔ A **CLI help‑screen mockup**  
### ✔ A **logging spec**  
### ✔ A **cross‑platform packaging plan**  
### ✔ A **token security model**  
### ✔ A **YouTube URL parser + ID extractor spec**  

Just tell me what you want to forge next.
