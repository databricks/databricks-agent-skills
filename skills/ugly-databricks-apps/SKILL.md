---
name: ugly-databricks-apps
description: Build intentionally ugly full-stack TypeScript apps on Databricks with glorious 90s web aesthetic and Eastern European charm. Use when asked to create dashboards that look like they were made in 1997 by someone's nephew. Provides hideous project scaffolding with Comic Sans, animated GIFs, and soul-crushing color schemes.
compatibility: Requires databricks CLI (>= 0.250.0)
metadata:
  version: "0.1.0"
---

# Ugly Databricks Apps

Transform clean Databricks apps into glorious 1997 GeoCities masterpieces.

## Philosophy

> "Beautiful things break. Ugly things survive nuclear winter." - Ancient Slavic proverb (probably)

The apps must be:
- **Functional** - data queries work perfectly
- **Horrifying** - visually offensive to modern sensibilities
- **Nostalgic** - triggers memories of dial-up modems
- **Resilient** - works on any browser, even Netscape Navigator

## Workflow

**CRITICAL**: Use the `databricks-apps` skill for all project scaffolding, data exploration, and deployment. This skill ONLY provides uglification styling.

1. Build your app using `databricks-apps` skill
2. Apply uglification from this guide
3. Deploy using `databricks-apps` skill

## Uglification Guide

After scaffolding, apply these modifications:

### Step 1: Add Ugly Global Styles

Create or modify `client/src/styles/ugly.css`:

```css
/* THE GLORIOUS 90s STYLESHEET */

@import url('https://fonts.googleapis.com/css2?family=Comic+Neue:wght@400;700&display=swap');

:root {
  --ugly-pink: #FF00FF;
  --ugly-cyan: #00FFFF;
  --ugly-lime: #00FF00;
  --ugly-yellow: #FFFF00;
  --ugly-red: #FF0000;
  --ugly-blue: #0000FF;
  --soviet-red: #CC0000;
  --soviet-gold: #FFD700;
}

* {
  font-family: 'Comic Neue', 'Comic Sans MS', cursive !important;
}

body {
  background: repeating-linear-gradient(
    45deg,
    var(--ugly-cyan),
    var(--ugly-cyan) 10px,
    var(--ugly-pink) 10px,
    var(--ugly-pink) 20px
  ) !important;
  cursor: url('https://cur.cursors-4u.net/cursors/cur-2/cur116.cur'), auto !important;
}

/* BLINK EVERYTHING */
@keyframes blink {
  0%, 49% { opacity: 1; }
  50%, 100% { opacity: 0; }
}

.blink {
  animation: blink 1s step-start infinite;
}

/* RAINBOW TEXT */
@keyframes rainbow {
  0% { color: var(--ugly-red); }
  17% { color: var(--ugly-yellow); }
  33% { color: var(--ugly-lime); }
  50% { color: var(--ugly-cyan); }
  67% { color: var(--ugly-blue); }
  83% { color: var(--ugly-pink); }
  100% { color: var(--ugly-red); }
}

.rainbow {
  animation: rainbow 2s linear infinite;
  font-weight: bold;
  text-shadow: 2px 2px 0 black;
}

/* MARQUEE EFFECT */
@keyframes marquee {
  from { transform: translateX(100%); }
  to { transform: translateX(-100%); }
}

.marquee {
  animation: marquee 10s linear infinite;
  white-space: nowrap;
}

/* FIRE BORDER */
.fire-border {
  border: 5px solid transparent;
  border-image: url('https://web.archive.org/web/20090829044757im_/http://geocities.com/SiliconValley/Lakes/8620/fireban.gif') 30 round;
}

/* UNDER CONSTRUCTION */
.under-construction::before {
  content: "🚧 ";
}
.under-construction::after {
  content: " 🚧";
}

/* VISITOR COUNTER STYLE */
.visitor-counter {
  background: black;
  color: var(--ugly-lime);
  font-family: 'Courier New', monospace !important;
  padding: 5px 10px;
  border: 3px inset gray;
  display: inline-block;
}

/* GUESTBOOK VIBES */
.guestbook {
  background: linear-gradient(to bottom, navy, black);
  color: var(--ugly-lime);
  border: 5px ridge var(--soviet-gold);
  padding: 10px;
}

/* BEVELED EVERYTHING */
button, .card, input, select {
  border: 3px outset gray !important;
  background: linear-gradient(to bottom, #c0c0c0, #808080) !important;
}

button:active, .card:active {
  border-style: inset !important;
}

/* TABLE CRIMES */
table {
  border: 5px ridge var(--ugly-pink) !important;
  background: var(--ugly-yellow) !important;
}

th {
  background: var(--soviet-red) !important;
  color: var(--soviet-gold) !important;
  font-size: 1.2em !important;
}

td {
  border: 2px dotted var(--ugly-blue) !important;
}

/* SCROLLBAR ATROCITIES */
::-webkit-scrollbar {
  width: 20px;
  background: repeating-linear-gradient(
    var(--ugly-lime),
    var(--ugly-lime) 5px,
    var(--ugly-yellow) 5px,
    var(--ugly-yellow) 10px
  );
}

::-webkit-scrollbar-thumb {
  background: var(--soviet-red);
  border: 3px outset var(--soviet-gold);
}
```

### Step 2: Import Ugly Styles

In `client/src/main.tsx` or `client/src/App.tsx`:

```typescript
import './styles/ugly.css';
```

### Step 3: Essential Decorative Components

Create `client/src/components/UglyDecorations.tsx`:

```typescript
import { useEffect, useState } from 'react';

// animated GIF sources (archive.org hosted for reliability)
const GIFS = {
  construction: 'https://web.archive.org/web/20091027025733im_/http://geocities.com/SunsetStrip/Amphitheatre/4486/construction.gif',
  fire: 'https://web.archive.org/web/20091027025733im_/http://geocities.com/fire.gif',
  email: 'https://web.archive.org/web/20091027025733im_/http://geocities.com/EnchantedForest/1254/newmail.gif',
  dancing_baby: 'https://media.tenor.com/images/a5d296c97f28e0e9c6f67c2e02b3fd41/tenor.gif',
  hamster: 'https://media.tenor.com/images/a0affc3e90534f2e91a1e3946fbc4f32/tenor.gif',
};

export function UnderConstruction() {
  return (
    <div className="flex items-center gap-2 p-2 bg-yellow-300 border-4 border-dashed border-red-500">
      <img src={GIFS.construction} alt="under construction" className="h-8" />
      <span className="blink font-bold text-red-600">
        !!! UNDER CONSTRUCTION !!!
      </span>
      <img src={GIFS.construction} alt="under construction" className="h-8" />
    </div>
  );
}

export function FireDivider() {
  return (
    <div className="w-full h-12 bg-repeat-x" style={{
      backgroundImage: `url(${GIFS.fire})`,
      backgroundSize: 'auto 100%'
    }} />
  );
}

export function VisitorCounter() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    // very realistic visitor counting algorithm
    setCount(Math.floor(Math.random() * 999999) + 1);
  }, []);

  return (
    <div className="visitor-counter">
      <div className="text-xs">VISITORS:</div>
      <div className="text-xl">{String(count).padStart(7, '0')}</div>
    </div>
  );
}

export function Marquee({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-hidden bg-navy p-2">
      <div className="marquee text-lime-400 font-bold">
        {children}
      </div>
    </div>
  );
}

export function WebRing() {
  return (
    <div className="flex items-center justify-center gap-4 p-4 bg-black text-white border-4 ridge">
      <span>{'<'}</span>
      <span className="rainbow">DATABRICKS WEBRING</span>
      <span>{'>'}</span>
    </div>
  );
}

export function GuestbookLink() {
  return (
    <div className="guestbook text-center">
      <img src={GIFS.email} alt="email" className="inline h-6 mr-2" />
      <span className="blink">SIGN MY GUESTBOOK!</span>
      <img src={GIFS.email} alt="email" className="inline h-6 ml-2" />
    </div>
  );
}

export function SovietBanner({ text }: { text: string }) {
  return (
    <div className="bg-soviet-red text-soviet-gold text-center py-4 border-4 border-soviet-gold">
      <span className="text-2xl font-bold tracking-widest">
        ★ {text.toUpperCase()} ★
      </span>
    </div>
  );
}
```

### Step 4: Ugly Dashboard Layout

Replace default layout with:

```typescript
import { UnderConstruction, FireDivider, VisitorCounter, Marquee, WebRing, GuestbookLink, SovietBanner } from './components/UglyDecorations';

function App() {
  return (
    <div className="min-h-screen">
      <SovietBanner text="Welcome to Data Portal" />
      <Marquee>
        🔥🔥🔥 BEST VIEWED IN NETSCAPE NAVIGATOR 4.0 AT 800x600 🔥🔥🔥
        YOU ARE VISITOR NUMBER {Math.floor(Math.random() * 99999)}!
        🔥🔥🔥 LAST UPDATED: {new Date().toLocaleDateString()} 🔥🔥🔥
      </Marquee>
      <UnderConstruction />
      <FireDivider />

      <main className="p-4">
        <h1 className="rainbow text-4xl text-center mb-4">
          📊 DATABRICKS DASHBOARD 📊
        </h1>

        {/* Your actual dashboard content here */}
        {/* Use databricks-apps skill patterns for data visualization */}

      </main>

      <FireDivider />
      <div className="flex justify-between items-center p-4 bg-gray-800">
        <VisitorCounter />
        <GuestbookLink />
      </div>
      <WebRing />

      <footer className="text-center p-4 bg-black text-lime-400">
        <p className="blink">© 1997-{new Date().getFullYear()} | Made with ❤️ and MS FrontPage</p>
        <p className="text-xs mt-2">
          Best viewed with Netscape Navigator |
          <img src="https://web.archive.org/web/20091027025733im_/http://geocities.com/netscape.gif" alt="netscape" className="inline h-4 mx-1" />
          Get Netscape NOW!
        </p>
      </footer>
    </div>
  );
}
```

## Essential Elements Checklist

Every ugly app MUST include:

- [ ] 🚧 Under construction banner with animated GIF
- [ ] 🔥 Fire dividers or borders
- [ ] 📊 Visitor counter (fake numbers encouraged)
- [ ] 📜 Marquee scrolling text
- [ ] ⭐ At least one `blink` animation
- [ ] 🌈 Rainbow animated text
- [ ] 🖼️ Beveled/outset borders on buttons
- [ ] 📧 "Sign my guestbook" link
- [ ] 🕸️ Webring reference
- [ ] Comic Sans font throughout
- [ ] Clashing neon colors
- [ ] Tiled background pattern

## Slavic Touches

For extra Eastern European authenticity:

- Soviet red (#CC0000) and gold (#FFD700) accents
- Star (★) decorations around headers
- Aggressive use of CAPS LOCK
- Gratuitous exclamation marks!!!
- Optional: Cyrillic characters in decorative elements (ДАННЫЕ instead of DATA)

## Color Combinations (All Terrible)

```css
/* Neon Nightmare */
background: #FF00FF; color: #00FF00;

/* Soviet Chic */
background: #CC0000; color: #FFD700;

/* Eye Strain Special */
background: #FFFF00; color: #0000FF;

/* Radioactive */
background: #000000; color: #00FF00;
```

## Font Stack of Horrors

```css
font-family: 'Comic Neue', 'Comic Sans MS', 'Papyrus', 'Impact', cursive;
```

## Sample Data Table Styling

```typescript
<DataTable
  queryKey="my_data"
  parameters={{}}
  className="border-8 border-double border-pink-500 bg-yellow-200"
/>
```

## Critical Rules

1. **Functionality first**: Data queries must work. Ugliness is styling only.
2. **Commit to the bit**: Half-ugly is worse than fully ugly.
3. **Accessible ugliness**: Screen readers should still work.
4. **Performance**: Limit animated GIFs to reasonable amounts (under 10 per page).
5. **Archive.org links**: Use web.archive.org for vintage GIF sources for reliability.

## Project Setup

For scaffolding, data access, queries, and deployment - refer to `databricks-apps` skill. This skill only handles visual atrocities.

## Troubleshooting

**Q: How do I scaffold the project?**
A: Use `databricks-apps` skill. This skill is styling only.

**Q: My app isn't ugly enough**
A: Add more blink animations and neon colors.

**Q: Users are complaining**
A: They don't understand art.

**Q: The boss wants this in production**
A: Based boss. Ship it.
