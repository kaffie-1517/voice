# Relay — 5-minute video walkthrough

**Setup:** Phone A = Maya (you). Phone B = Sam, later the Fire Brigade (a
friend, or Telegram Desktop on a second account). Laptop = web app + slides.
Record the laptop screen; film or screen-record the phones; cut together.

**Speak in fragments the whole way.** "doc… tues…", not sentences. Leave ~1 s
between fragments — a pause is what sends the clip. After you speak, **stop
and wait for the buttons**.

## Before you press record (3 min, off camera)

| Where | Do |
|---|---|
| Groq console | Accept the TTS terms: console.groq.com/playground?model=canopylabs/orpheus-v1-english |
| Laptop | Refresh the web tab; the pill must say **Groq** |
| Phone A → bot | Send `hi`. Tap **📍 Share my location** |
| Phone B → bot | Send `/link Sam` |
| Everyone | Leave the bot alone for 60 s so the minute budget is full |

---

## 1 · 0:00 — Why (title slide, 25 s)

> Two million people in the US live with aphasia. They know exactly what
> they want to say — the sentence gets stuck on the way out. Phone calls are
> the worst: no face, no gestures, a receptionist who will hang up. Relay
> gives them their words back in time — and then does what the words asked.

## 2 · 0:25 — A message (Phone A → Phone B, 35 s)

Phone A, voice note: **"tell… Sam… late… lunch"**
→ four buttons. Tap *"Tell Sam I'll be late for lunch."*
→ a **voice bubble** of the sentence appears in her chat (play it) → *Working
on it…* → receipt.
**Cut to Phone B:** Sam has *"I'll be late for lunch."*

> Three syllables in. A finished sentence out, in her voice — and it reached
> her son.

## 3 · 1:00 — Say it out loud, in the room (Phone A, 25 s)

Voice note: **"tea… please… no sugar"** → tap → play the voice bubble,
holding the phone toward the camera.

> No one on the other end here. She's ordering in a café. She taps, the phone
> speaks for her. Nothing is said without that tap.

## 4 · 1:25 — Being messaged (Phone B → Phone A, 35 s)

Phone B (Sam), **voice note**: *"Mum, do you need a lift on Tuesday?"*
→ Phone A gets *Sam: 🎤 …* with four replies → tap *"Yes, I need a lift on
Tuesday."* → **Phone B receives it.**

> Family don't install anything. They message her, she taps, they get a full
> sentence back.

## 5 · 2:00 — The emergency (Phone A + Phone B, 45 s)

Phone B: send `/link Fire Brigade` — say *"this chat stands in for a
dispatcher."*
Phone A, voice note: **"fire… home… help"**
→ tap *"There is a fire at my home…"*
→ **Phone B**: 🚒 *EMERGENCY CALL via Relay for Maya Ellis…* with a **map
pin**. Say that Sam, Dr. Chen and Nadia each got a 🚨 alert with her exact
words and the pin at the same moment (show Phone B as Sam if you have a third
account; otherwise say it).

> She cannot dial 911 and explain. One tap tells everyone who can act, and
> where she is. This path is hard-coded — it runs even if the AI provider is
> down.

## 6 · 2:45 — Call the doctor → the live call (Phone A → laptop, 80 s)

Phone A, voice note: **"call… doctor… appoint…"** → tap *"Call Dr. Chen for
an appointment."* → receipt: *Dr. Chen asked to call her back — open the Call
tab.*

> Real phone lines are the next step. The hard part is already built: replying
> in time. Watch.

Laptop, **Call → Book an appointment.** Dani answers. Say **"doc… chen…"** →
replies → tap. Dani asks *"when?"* → **point at the screen: replies are there
before you've said a word.** Tap *"Tuesday morning, if you have it."* Dani
confirms. Hang up. Click **Done** — the booking receipt is there.

Then, still on the laptop, **Say** tab: **"remind… pills… two minutes"** →
tap.

> The suggestions after "when?" came from Dani's question alone. She never had
> to find those words.

## 7 · 4:05 — How it's built (architecture slide, 40 s)

> Two Strands agents, deliberately different. The prediction loop is one
> constrained call — no tools, no loop — because someone's waiting on the
> line. The executor is a real agent with tools: message, document, reminder,
> call, location, emergency alert. Whisper on the way in, a neural voice on
> the way out, and every sentence she chooses is remembered — so it gets
> better at being *her*. Groq today; Bedrock is a config line.

**Phone A buzzes: 🔔 Reminder: take my pills.** Hold it up.

> Nothing spoken, nothing sent, without her tap. Relay — your words, on time.

**4:45. Done.**

---

## If it goes wrong on camera

| You see | Do |
|---|---|
| Pill says *Offline* / "(offline engine)" | Groq minute budget. Stop for 60 s, retake that beat. Message + emergency still work offline. |
| No buttons after a voice note | Whisper dropped it as noise. Speak closer, or type: `tell sam late lunch` |
| Phone B got nothing | Not linked. Send `/link Sam` there again. |
| Bot says *Use /link* to Phone A | Send `/me` from Phone A. |
| Two replies to one message | Ignore — it was a restart overlap, won't recur. |
| No voice bubble | TTS terms not accepted yet; the text still shows. |
