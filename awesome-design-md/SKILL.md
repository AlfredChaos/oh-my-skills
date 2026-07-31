---
name: awesome-design-md
description: Fetch Design System Inspiration from 50+ websites (Stripe, Linear, Apple, etc.) to use as a style guide for frontend generation.
---
# Awesome Design MD Skill

You have access to 50+ curated design system languages inspired by top developer-focused websites and brands. 
This skill enables you to query and fetch the design guidelines (colors, typography, spacing, UI components) and use them as reference for front-end development tasks.

## How to use this skill

1. **Suggest References**: When asked to build a modern UI or design a web application, suggest using one of the available design styles if the user hasn't specified one. 
2. **Fetch Design Information**: If the user wants a UI inspired by a specific brand, you MUST execute the following command to download the corresponding `DESIGN.md`:
   
   ```bash
   npx getdesign@latest add <brand-name>
   ```
   
   *Tip: To avoid cluttering the user's project, you can run this in a temporary folder (e.g. `cd /tmp && npx -y getdesign@latest add <brand-name>`) and then read `/tmp/DESIGN.md`.*

3. **Read and Apply**: Once `DESIGN.md` is generated, read the file using your standard file reading tools. Strictly apply the extracted design principles, primarily:
   - **Colors**: Exact hex codes, gradients, shadows.
   - **Typography**: Specific font families (import them via Google Fonts if necessary), font weights, sizes, and tracking.
   - **Layout/Spacing**: Padding, margins, and border radii.
   - **Components**: Stylistic nuances of buttons, cards, headers, etc.

4. **Answer Questions**: You can also fetch a reference to answer design-related questions (e.g., "What shadow does Stripe use for their cards?").

## Available Design Systems

You can run the `getdesign` command with any of the following ids:

airbnb, airtable, apple, bmw, cal, claude, clay, clickhouse, cohere, coinbase, composio, cursor, elevenlabs, expo, ferrari, figma, framer, hashicorp, ibm, intercom, kraken, lamborghini, linear.app, lovable, minimax, mintlify, miro, mistral.ai, mongodb, notion, nvidia, ollama, opencode.ai, pinterest, posthog, raycast, renault, replicate, resend, revolut, runwayml, sanity, semrush, sentry, spacex, spotify, stripe, supabase, superhuman, tesla, together.ai, uber, vercel, voltagent, warp, webflow, wise, x.ai, zapier

## Strict Guidelines
- **Always read the generated `DESIGN.md`**. Never assume or hallucinate the colors, fonts, or styles for these brands.
- Extract the specific design variables and use them in the exact framework the user is utilizing (e.g., Tailwind CSS, plain CSS, React).
- Do NOT generate generic designs when a brand is specified. The `DESIGN.md` serves as your source of truth.
