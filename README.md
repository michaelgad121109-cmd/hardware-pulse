# Mikey Tech | Hardware Pulse

A static English-language hardware news digest by the Mikey Tech YouTube channel, designed for GitHub Pages.

YouTube: https://www.youtube.com/@mikey-tech0

## Features
- Responsive dark editorial interface
- GPU, CPU, memory/storage and other hardware categories
- Search and source links
- RSS collection with duplicate filtering
- Optional AI-generated short summaries
- Scheduled GitHub Actions workflow (every 3 hours)
- GitHub Pages deployment workflow

## Setup
1. In **Settings → Pages**, set the source to **GitHub Actions**.
2. Optionally add a repository secret named OPENAI_API_KEY under **Settings → Secrets and variables → Actions**. Without it, summaries use RSS feed descriptions.
3. In **Actions**, run **Update hardware news** manually once. The scheduled job then runs every 3 hours.
4. The Pages workflow deploys the site after pushes. The URL will be https://michaelgad121109-cmd.github.io/hardware-pulse/.

## Important notes
- Never put API keys in index.html, app.js, or any public file.
- RSS availability and terms vary by publisher. Respect source terms and rate limits.
- The site displays original headlines and short summaries with links to publishers; it does not republish full articles.
- Review source permissions before enabling automated use at scale.
