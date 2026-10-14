# WhatsApp Daily Greeting Bot 🌅

Automation that sends a daily "good morning" image on WhatsApp Web — every day at 6:00 AM, unattended.

It searches Google Images for a greeting image, picks one that was **never sent before**, converts it to JPG, and sends it to a contact with a caption.

> **Built for personal use** — I made it to send a blessed good morning message to my godfather every day.
> But the flow (*find content → prepare it → send it on WhatsApp → on a schedule*) works for **any recurring task**:
> daily reminders, reports, birthday messages, team notifications...
> The code is fully commented, so it is easy to customize.

## How it works

```
Windows Task Scheduler (06:00)
        │
        ▼
1. Attach Selenium to an already-open Chrome (dedicated profile, WhatsApp logged in)
2. Search Google Images in a new tab → pick a random image not sent before
3. Download it and convert to JPG
4. Copy the image to the Windows clipboard → paste (Ctrl+V) into the chat
5. Add the caption and send
6. Save to history (avoids repeats) and log everything
```

## Tech stack

- **Python 3** + **Selenium 4**
- **Pillow**: image conversion
- **pywin32**: Windows clipboard
- **Windows Task Scheduler**: daily execution

## Challenges solved

Real problems found while building it, and how each one was solved:

| Problem | Solution |
|---|---|
| Selenium can't control the Chrome you already use (Chrome 136+ blocks automation on the default profile) | Dedicated Chrome profile started with `--remote-debugging-port`; Selenium **attaches** to it instead of opening a new browser |
| WhatsApp Web changes its HTML often, so fixed selectors break | Elements found by **partial names** via JavaScript (e.g. any icon containing `send`), plus fallbacks |
| `ElementClickInterceptedException`: an invisible layer covered the target | Only accept elements that are **actually on top** (`document.elementFromPoint`) and focus via JS instead of clicking |
| Image arrived as a **sticker** instead of a photo (wrong hidden file input) | Image copied to the clipboard and **pasted** into the chat, which always opens as a photo |
| ChromeDriver's `send_keys` doesn't support emoji | Caption typed with the browser's `insertText` |
| Same image sent twice | URL + SHA-256 hash history (`historico.json`) |
| Retry after an uncertain send could duplicate the message | Uncertain confirmation only logs a warning; it doesn't retry |
| Google page structure changes | Generic image detection by size; fallback to a local `imagens_reserva/` folder |

## Getting started

```bash
py -m pip install -r requirements.txt
```

1. Set the contact number as an environment variable (country code + area code + number, digits only). It stays on your computer, out of the code:
   ```bat
   setx PADRINHO_TELEFONE "55XXXXXXXXXXX"
   ```
2. Run a test (downloads the image but **does not send**):
   ```bash
   py bom_dia_padrinho.py --teste
   ```
   Chrome opens with a dedicated profile. Go to `web.whatsapp.com` and scan the QR Code **once**.
3. Schedule it daily at 6:00 AM:
   ```bat
   schtasks /create /tn "Bom dia padrinho" /tr "\"C:\path\to\rodar_bom_dia.bat\"" /sc daily /st 06:00 /it
   ```
   In Task Scheduler, also enable *"Wake the computer to run this task"* and *"Run task as soon as possible after a scheduled start is missed"*.

## Customizing

All settings are at the top of `bom_dia_padrinho.py`:

| Setting | What it does |
|---|---|
| `PADRINHO_TELEFONE` (env var) | Contact who receives the message |
| `LEGENDA` | Caption sent with the image (emoji supported) |
| `TERMOS_PESQUISA` | Google search terms (one is picked at random each day) |
| `imagens_reserva/` | Optional folder with backup images in case Google fails |

To adapt it to another task, swap `buscar_imagem_google()` for any content source (a file, an API, a spreadsheet...) and keep the WhatsApp sending part as it is.

## Requirements

- Windows, Google Chrome
- Computer on (or asleep) and user logged in at the scheduled time

## Disclaimer

Personal project, for learning and personal use. WhatsApp does not officially support automation of WhatsApp Web. Use it responsibly, for low-volume personal messages only.
