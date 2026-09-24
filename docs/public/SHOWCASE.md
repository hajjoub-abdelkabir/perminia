# Demonstrating the technical MVP

## Scope

Two synthetic schools, six role accounts, two walkthrough lessons and eight color/shape exercises. No real pupil history is included. A small initial reading event and task make the connected school workflow discoverable; assessment evidence is created by your own demo answers.

The source implements both private-data development workflows and this distributable showcase. The latter requires no scraper output, API key or manually prepared database.

## Record a short demo

1. Start with the learner's **اليوم** screen. Keep the synthetic-demo banner visible.
2. Show a lesson, save progress, refresh and show that the reading position persists.
3. Answer the shape exercise, confirm selections, and show the saved session and review. Explain that the question content is synthetic and the scoring/persistence are real application behavior.
4. Switch to the matching instructor (keep credentials off-screen). Show the learner's reading/task status and assign another lesson.
5. Switch to the school manager. Show membership and instructor assignment, without opening password-recovery tokens.
6. Close with the architecture and next milestone: reviewed curriculum and a supervised school pilot.

Do not claim the public demo provides working generative answers: its AI is deliberately disabled. If separately showing the development AI integration, use only non-private sample conversations, disclose the draft-source status, and keep keys/provider dashboards out of the recording.

## Publishing handoff

Use **the generated `release/perminia-github` folder**, not a wholesale upload of the working directory. It contains only allowlisted source, public documentation and assets, with a SHA-256 manifest.

```sh
python scripts/prepare_public_release.py --check
python scripts/prepare_public_release.py
```

The export refuses to overwrite an existing snapshot. A root `.env`, imported bank, backups, private logins, internal progress reports and old prototype are not copied. Inspect the manifest and Git's staged-file list before uploading. Keep the generated `data/showcase` directory ignored if you run the exported copy.

Suggested repository name: `perminia`. Suggested description: `A Moroccan driving-school learning platform: React, FastAPI, PostgreSQL, role-based workflows and an isolated synthetic MVP showcase.`

The source can then be initialized as a Git repository and pushed to your chosen GitHub destination. No remote repository or LinkedIn post is created by these scripts. Choose the repository visibility and original-code license deliberately.

## Release gates

- [ ] Fresh start from the exported copy without original `data/` or `.env`.
- [ ] Synthetic fixtures only; no private-dataset dependency in the showcase path.
- [ ] Public integration suite and frontend tests pass.
- [ ] Root page, role login, lesson progress and timed practice are usable.
- [ ] Public-source audit passes; inspect staged files and media credits.
- [ ] README differentiates working behavior, mocked/disabled providers and future work.
- [ ] Screenshots/recording contain no keys, passwords, invitation/recovery tokens or private conversations.
- [ ] GitHub checks are green after upload; no assertion of remote success before it runs.

## Pilot release remains a different milestone

Reviewed Moroccan driving content, production hosting/security/monitoring, externally tested backup restoration, school-level costs, real-phone user testing and an actual school pilot remain required. Calling this a **technical MVP** communicates its real stage without hiding that work.
