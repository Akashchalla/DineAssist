# DineAssist evaluation website

This is the public interactive demo for Vercel, with a small server-side Twinly chat endpoint. The full Python/Streamlit application remains in the project.

## What judges can try

- Select any of the 14 mapped tables.
- Record a simulated greeting and watch the greeting count and queue update.
- Simulate guests leaving, then confirm cleaning.
- Seat a sample party and simulate a five-minute greeting delay.
- Reset the scenario, watch the saved detector video, and read how the project works.
- Open **Ask DineAssist** for table availability, per-table estimates, and general restaurant/project questions.

The initial scenario has 3 available tables, 11 occupied tables, and 4 greeting alerts. Its layout and person counts were prepared from the saved recording; service statuses are illustrative. These are not live restaurant observations. Actions are held in browser memory and reset on reload. No guest records, private notification topics, database, credentials, or camera streams are published.

## Build and preview

From the project root:

```sh
npm run build
npm run preview
```

Open http://127.0.0.1:4174. No npm dependencies are needed. Local table questions work without a key; general AI questions require `TWINLY_API_KEY` in the server environment. Never put it in browser JavaScript or commit it to Git.

## Chat assistant

`api/chat.js` runs on Vercel and uses the documented Twinly `twinly-core` model at `/v1/chat/completions`. Add **TWINLY_API_KEY** as a private Production environment variable in Vercel, then redeploy. A key with only the `chat` scope is sufficient; use a spending cap in Twinly for a hard usage limit. No calls, texts, desktop tasks or computer controls are enabled.

Operational counts and wait calculations are deterministic. The server validates the client demo snapshot against known table IDs and uses template capacities; it never sends caller-provided names or instructions as table data. General questions use Twinly with that context and up to six prior conversation messages. Provider errors are shown honestly. The endpoint has message limits, a timeout, origin checks and a best-effort per-instance burst guard; the burst guard is not a globally enforced rate limit.

Wait estimates default to a 45-minute meal, plus 5 minutes for cleaning, with ±10 minutes on remaining meal time. Inputs are adjustable. These are assumptions, not learned predictions; seat capacities are illustrative, and queues, reservations, meal stages and actual departure times are unknown. The video clock is frozen. An available table has a zero estimated wait only within this demo.

Run the chat checks with `npm test`. They use a fake provider and do not spend API credit.

## Deploy on Vercel

Import `Akashchalla/DineAssist` into Vercel, keeping the repository root as the Root Directory. Use the **Other** framework preset. The included `vercel.json` sets `npm run build` as the build command and `dist` as the output directory. Only the chat endpoint needs the private `TWINLY_API_KEY`; no database is needed.

Alternatively, sign into the official Vercel CLI and deploy from the root:

```sh
npx vercel login
npx vercel --prod
```

The build copies only the public HTML, styles, JavaScript, sample scene, licensed font, and output video into `dist`. The MOV source stays in `output`; the build publishes a browser-playable MP4-named copy without adding another source video to GitHub.

Hosting the full live system requires a separate service that can run the detector and API continuously; it is not provided by this evaluation website.
