# Copilot Instructions for Harmoniq

## Project Overview

Harmoniq is an AI-powered adaptive guitar learning app built with React Native and Expo for iOS, Android, and web. It targets intermediate guitarists who want to play expressively, focusing on musicality over grinding levels. The app analyzes songs, provides personalized practice sessions, and offers AI coaching feedback.

## Tech Stack

- **Frontend**: Expo SDK (~54), React Native, TypeScript
- **Backend**: Python (FastAPI), machine learning for audio analysis
- **UI**: NativeWind (Tailwind CSS), custom components
- **Audio**: Expo AV, audio processing libraries
- **Database**: Expo SQLite for local storage
- **Testing**: Vitest, Playwright, Detox
- **Build**: Metro bundler, Gradle for Android

## Architecture

- **App Structure**: Expo Router for navigation, file-based routing
- **Components**: Reusable UI components in `/components`
- **Screens**: App screens in `/app` directory
- **Backend**: Python app in `/backend` with ML pipelines
- **Assets**: Audio files, fonts, images in `/assets`

## Current Phase (Phase 1)

Finishing the core user flow: song analysis → 5-step practice session → AI review. Key remaining items:

- Fix analyze polling infinite loop (BUG-01)
- Fix Jam Mode AlphaTab crash (BUG-02)
- Implement real waveform scoring in Review
- Add placement session real scores

## Coding Guidelines

- Use TypeScript strictly
- Follow Expo/React Native best practices
- Warm, analog design aesthetic (walnut/amber color palette)
- Slow, intentional animations
- Prefer functional components with hooks
- Use Expo modules for native features

## Key Files

- `README.md`: Product vision and specs
- `PRIORITIES.md`: Engineering roadmap and current tasks
- `docs/E2E_DEMO.md`: Setup and testing guide
- `docs/RESOURCES.md`: External references and documentation links
- `package.json`: Frontend dependencies and scripts
- `backend/requirements.txt`: Backend dependencies

## External Resources

- **AlphaTab Documentation**: https://alphatab.net/docs/introduction (used for tablature rendering)
- **Nicolas Slonimsky Thesaurus**: https://www.lapetitedistribution.org/archive/Nicolas_Slonimsky.pdf (inspiration for warmup exercises)

## Development Setup

1. Install dependencies: `npm install` (frontend), `wsl cd /mnt/c/workspace/harmoniq/backend && pip install -r requirements.txt` (backend in WSL)
2. Start backend: `wsl cd /mnt/c/workspace/harmoniq/backend && uvicorn app.main:app --reload` (in WSL)
3. Start frontend: `npm start` (web) or `npx expo start` (native)

When contributing, check PRIORITIES.md for current phase tasks and ensure changes align with the product vision.
