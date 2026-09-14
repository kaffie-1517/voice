# Relay — Devpost submission text

Paste each section into the matching field on the "Enter a Submission" form.
Track: **Everyday Agents**.

---

## Tagline (one line)

A voice for people with aphasia: hears broken fragments, offers the sentence they meant, speaks it, and does what it asked.

---

## Inspiration

Aphasia takes away the path from a thought to the words for it. About two million people in the US live with it, most after a stroke. The person is entirely there — comprehension, intelligence, opinions — but the sentence gets stuck on the way out. A phone call is the worst case: no gestures, no face, a receptionist who will hang up. Many people with aphasia simply stop making calls, and hand their independence to whoever is willing to make them instead.

Existing tools either need weeks of training recordings before they work, or give the user a keyboard and wish them luck. We wanted something that works from the first syllable, and that never puts words in someone's mouth without their say-so.

## What it does

Relay listens to whatever *does* come out — a syllable, a broken word, a tapped concept — and, while the person is still mid-sentence, shows three or four complete things they might be trying to say. They tap one. It is spoken aloud in a natural voice. If the sentence asked for something to happen — a reminder, a document sent to their doctor, a message to their son — a Strands agent does it.

- **Live call view.** A simulated receptionist, pharmacy, or family member is on the line. When they ask a question, Relay's replies appear *before the user has said anything*, then sharpen as fragments come in. Tap, and it is spoken. Press 1–4 from the keyboard.
- **Say view.** Voice notes, messages, in-person conversation — the same engine with different length and tone.
- **Telegram.** Family members message or voice-note the bot; the user gets reply candidates on their phone and taps one; it is delivered. In *any* chat, `@relay1517_bot om tues` pops up the candidates and sends the chosen one as their own message.
- **Actions.** "Send my scan to Dr. Chen" makes the agent call `send_document`, and a PDF lands in Dr. Chen's Telegram chat. "Tell Sam I'll be late" reaches Sam's phone. "Call Dr. Chen for an appointment" asks Dr. Chen to ring her and opens the assisted-call view. "Remind me in two minutes" makes her phone buzz two minutes later — the agent computes the time, the server fires it.
- **Emergencies.** "Help, there's a fire" is detected in code, not left to the model: the agent alerts every adult contact on Telegram with her exact words and a map pin of where she is (shared with her consent through Telegram's own location prompt), and logs the call to the fire brigade or ambulance. She cannot dial 911 and explain; this is the next best thing, in one tap.
- **It learns.** Every sentence the user chooses is remembered and recalled by sound — after picking "I want to go home" once, a mumbled "om" brings that phrasing back. Share a contact card from your phone book and Relay knows that person; `/note my neighbour Ruth checks on me on Fridays` and it knows that too. Only what she chooses to share — Relay never reads other chats, call logs or notes.
- **It never goes silent.** If the model is slow, throttled, or unreachable, an offline engine answers within the deadline — with emergency rules for "fire" and "help", and the user's own words offered verbatim if nothing else fits.

## How we built it

**Strands Agents, used in two deliberately different shapes.**

The *prediction loop* is a Strands `Agent` with no tools and a Pydantic `structured_output_model` — one constrained call, no agent loop. Someone is waiting on the line; a correct suggestion that lands two seconds late is a failed suggestion. We force the structured-output tool from the first request (Strands otherwise spends a second round trip asking for it) and hold the whole thing to an eight-second deadline before falling back offline.

The *action executor* is the opposite: a real Strands agent with `@tool` functions (`send_document`, `set_reminder`, `send_message`, `place_call`, `share_location`, `alert_emergency`, `order_item`) and a genuine tool loop. It runs once, after the user commits, and is allowed to think. We watched it chain `send_document` and `set_reminder` from a single sentence without being told to. Tools read the client session from Strands' `ToolContext`, so each person's activity feed is their own.

A third small Strands agent plays the person on the other end of the call, with a persona prompt and a one-question-at-a-time rule.

**Everything else:**
- Python / FastAPI backend; React + Vite PWA frontend.
- Speech in: Groq Whisper with a vocabulary hint from the user's profile, and a confidence filter for Whisper's silence hallucinations. The browser captures raw PCM with a 350 ms pre-roll so the soft "h" in "home" is never clipped.
- Speech out: Groq's neural TTS with two distinct voices, browser voices as fallback.
- Model providers are a config choice — Bedrock, Anthropic, OpenAI, Groq — because Strands normalises them all behind one `Agent`.
- Personalisation: every choice recorded; retrieval by fuzzy sound match; Amazon Bedrock AgentCore Memory backend (events + semantic retrieval) coded behind the same interface as the local store.
- Telegram Bot API via long-polling, so the demo needs no public URL.

## Challenges we ran into

- **Latency versus honesty.** The first live model wrote "Tuesday at 3pm" from the fragment "tues". Our top prompt rule is *never invent facts*; we back it with a guard that keeps the user's clearly-spoken words on screen and offers them verbatim if the model drops them.
- **The model fought the user.** Told the fragments were "toothpaste, toothpaste", it kept suggesting clinic appointments because that is what callers to a clinic usually want. Fixing that took a prompt rule ("her words win"), a code-level guard, and stripping unrelated past choices out of the prompt — a sentence she chose yesterday was leaking into today's suggestions as a fact.
- **Speech recognition autocorrects the wrong way.** The browser's recogniser turned broken speech into fluent, wrong words. Whisper with a glossary keeps fragments as fragments — but hallucinates on silence, so we filter on its own confidence scores.
- **Free-tier limits are demo killers.** Strands retried a throttled provider six times with backoff — 130 seconds with someone on the line. Retries are now off on the hot path, with a hard deadline and an offline engine underneath.

## Accomplishments that we're proud of

- Suggestions appear *before* the user speaks, from the other side's question alone. That is the moment people point at.
- The two-tier Strands design: a single constrained call where latency is the feature, a real tool-using agent where deliberation is.
- A message chosen by tapping a button arrives on a family member's real phone; a document requested in three broken words lands in the doctor's chat.
- Zero enrolment. It works on the first sentence.
- It degrades gracefully instead of going blank — and says so on screen.

## What we learned

That the hard part of an assistive agent is not what it can do but what it must *refuse* to do: invent a time, swap a topic, speak without a tap. Most of our engineering went into guards around the model, not the model. And that Strands lets you choose the shape of each call — a structured single shot or a full agent loop — which is exactly the choice a latency-critical product needs.

## What's next for Relay

- Real telephony (Twilio media streams) — the reply engine is already built for it.
- Real reminders and calendar through the same tool interface.
- AgentCore Memory in production, so the phrasebook follows the user across devices.
- Claude Haiku on Bedrock for the prediction tier — faster and more rule-abiding than the open models we tested.
- Onboarding for families and speech therapists to build the profile that makes "chuh" resolve to "Dr. Chen".

---

## Built with (tags)

strands-agents, python, fastapi, react, typescript, vite, groq, whisper, telegram-bot-api, amazon-bedrock-agentcore, pydantic

## Links

- Repo: https://github.com/kaffie-1517/voice
- Telegram bot: https://t.me/relay1517_bot
