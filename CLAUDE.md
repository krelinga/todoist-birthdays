# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project goals and design

THe design doc for this project is located at `docs/design/birthday-todoist-reminder-design.md`.

The goal of this project is to build a system to automatically generate birthday reminders in todoist.

## Project status

This repository is currently an empty scaffold. It contains only a devcontainer
configuration and the design doc (`docs/design/birthday-todoist-reminder-design.md`)
— no application code, README, build tooling, or tests exist yet.

## Development environment

The devcontainer is based on `mcr.microsoft.com/devcontainers/base:noble` with:
- Node.js (LTS) via the `ghcr.io/devcontainers/features/node:2` feature
- Python 3.12 via the `ghcr.io/devcontainers/features/python:1` feature
- Docker-in-Docker via the `ghcr.io/devcontainers/features/docker-in-docker:2` feature
- The Claude Code CLI feature (`ghcr.io/anthropics/devcontainer-features/claude-code:1.0`)

No package.json, language-specific tooling, or dependency manifest exists yet,
so there are no build/lint/test commands to document.

## Next steps for future instances

Once real code is added to this repository, update this file with:
- Build, lint, and test commands (including how to run a single test)
- The chosen language/framework and how the Todoist API integration is structured
- Any authentication/config setup needed to run the project locally
