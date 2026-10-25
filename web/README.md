# DineAssist evaluation website

This is the public, browser-only demo for Vercel. The full Python/Streamlit application remains in the project unchanged.

## What judges can try

- Select any of the 14 mapped tables.
- Record a simulated greeting and watch the greeting count and queue update.
- Simulate guests leaving, then confirm cleaning.
- Seat a sample party and simulate a five-minute greeting delay.
- Reset the scenario, watch the saved detector video, and read how the project works.

The initial scenario has 3 available tables, 11 occupied tables, and 4 greeting alerts. Its layout and person counts were prepared from the saved recording; service statuses are illustrative. These are not live restaurant observations. Actions are held in browser memory and reset on reload. No guest records, private notification topics, database, credentials, or camera streams are published.

## Build and preview

From the project root:

```sh
npm run build
python3 -m http.server 4173 --bind 127.0.0.1 --directory dist
```

Open http://127.0.0.1:4173. No npm dependencies are needed for this build.

## Deploy on Vercel

Import `Akashchalla/DineAssist` into Vercel, keeping the repository root as the Root Directory. Use the **Other** framework preset. The included `vercel.json` sets `npm run build` as the build command and `dist` as the output directory. No environment variables or database are needed.

Alternatively, sign into the official Vercel CLI and deploy from the root:

```sh
npx vercel login
npx vercel --prod
```

The build copies only the public HTML, styles, JavaScript, sample scene, licensed font, and output video into `dist`. The MOV source stays in `output`; the build publishes a browser-playable MP4-named copy without adding another source video to GitHub.

Hosting the full live system requires a separate service that can run the detector and API continuously; it is not provided by this static demo.
