# AI-Driven Smart Public Grievance Redressal System

A Flask web platform for public grievance registration, intelligent routing, status tracking, and notification-driven accountability.

## Run locally

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## First administrator (no demo accounts)

Before first start, set secure local values in PowerShell. Do not commit these values.

```powershell
$env:SMARTGOV_ADMIN_NAME="System Administrator"
$env:SMARTGOV_ADMIN_EMAIL="your-admin-email@example.com"
$env:SMARTGOV_ADMIN_PASSWORD="choose-a-strong-password"
python app.py
```

The administrator is created only once. Remove the three environment variables afterwards.

## Twilio WhatsApp alerts

Every newly registered grievance sends an alert to `+91 63749 52773` by default. Configure your Twilio account before starting the app:

```powershell
$env:TWILIO_ACCOUNT_SID="AC..."
$env:TWILIO_AUTH_TOKEN="your_auth_token"
$env:TWILIO_WHATSAPP_FROM="whatsapp:+14155238886"
$env:TWILIO_ALERT_TO="whatsapp:+916374952773"
python app.py
```

For a Twilio Sandbox sender, the recipient must first join your sandbox through Twilio's provided WhatsApp link/code. For production, use an approved WhatsApp sender and templates where Twilio/WhatsApp policy requires them.

## WhatsApp bot (incoming messages)

The app also exposes an inbound bot webhook at `POST /whatsapp/webhook`. Send `help`, then reply `1` to register a complaint through a guided flow (name, category, description, and location). It returns a SmartGov reference number when complete. You can later use `track SGRS-12345` to see its status. Reply `cancel` at any point to abandon an unfinished registration.

1. Start the app and expose it through a public HTTPS URL (for example, using ngrok).
2. Set `TWILIO_WEBHOOK_URL` in `.env` to the exact public URL, such as `https://your-domain.ngrok-free.app/whatsapp/webhook`.
3. In the Twilio Console, open your WhatsApp Sandbox or WhatsApp sender and set **When a message comes in** to that URL with method **POST**.
4. Send `help` from a WhatsApp number that has joined the sandbox.

Webhook signatures are verified using `TWILIO_AUTH_TOKEN`. For a local manual POST test only, set `TWILIO_VALIDATE_WEBHOOK=false`; do not use that setting in production.

## Persistent Twilio setup

1. Copy `.env.example` to `.env` in the project root.
2. Fill in the Twilio Account SID, Auth Token, approved WhatsApp sender, and content-template SID.
3. Create an approved **utility** template with four variables: grievance reference, issue title, department, and priority.
4. If testing via Twilio Sandbox, join the Sandbox from WhatsApp number `+91 63749 52773` using the Sandbox QR code or `join <sandbox-code>` message shown in the Twilio Console.
5. Restart `python app.py` after saving `.env`.
