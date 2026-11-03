# KnowRealm-AI ![Platform: Windows x64](https://img.shields.io/badge/Windows-x64-0078D4)

[![Tauri 2](https://img.shields.io/badge/Tauri-2-24C8D8)](apps/desktop/src-tauri/Cargo.toml) [![React 19](https://img.shields.io/badge/React-19-149ECA)](apps/desktop/package.json)

**English** | [简体中文](README.zh-CN.md)

KnowRealm-AI is a local-first learning and AI workspace for students, programmers, professionals, and lifelong learners to collect materials, organize knowledge, and carry out learning tasks through natural language.

<p align="center">
  <img src="apps/desktop/src-tauri/icons/128x128.png" width="88" height="88" alt="KnowRealm app icon" />
</p>

**[Download for Windows](https://github.com/youyu-youth/KnowRealm-AI/releases/latest)** | [Quick Start](#installation-and-quick-start) | [FAQ](#faq) | [Development](#development) | [Feedback](https://github.com/youyu-youth/KnowRealm-AI/issues)

No account is required. Your learning data stays in a local folder you can inspect and move. A Windows x64 desktop installer is available, with no separate server to deploy. The project is under active development; see the [release notes](https://github.com/youyu-youth/KnowRealm-AI/releases) for the features and limitations of each version.

## Features

| Feature              | What you can do                                                                                                                                                                                                         |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Capture              | Record classes, import audio and documents, paste text, take quick notes, and clip web pages                                                                                                                            |
| Content organization | Transcribe or extract source text, generate summaries, and confirm content to create knowledge points, exercises, to-dos, and review materials                                                                          |
| Knowledge spaces     | Organize records by course and learning context, and explore course concept graphs and relationships                                                                                                                    |
| Library and search   | Browse source materials, learning records, and confirmed assets; filter, categorize, and search local content                                                                                                           |
| AI chat              | Ask questions within a selected set of materials, follow answer citations back to their sources, and optionally enable web search                                                                                       |
| AI assistant actions | Ask the general assistant to find or create courses, add text records, and create or adjust learning plans under your chosen authorization mode; the knowledge assistant provides read-only answers from your materials |
| Practice and review  | Generate exercises, take mock tests, prepare review materials, and track learning evidence and concept mastery                                                                                                          |
| Desktop experience   | Light and dark themes, Chinese and English interfaces, global search, quick-note shortcuts, and system tray support                                                                                                     |

Start by capturing materials, then transcribe or extract their text, review summaries, and confirm what to keep. The resulting learning content is editable and traceable to its sources, ready for search, questions, practice, and review.

## Screenshots

### Knowledge spaces (dark theme)

Organize courses around career skills, academic study, and personal interests, with track, list, and card views.

![KnowRealm knowledge spaces in the dark theme](docs/img/desktop/PixPin_2026-10-30_15-00-47.png)

### Library (light theme)

Browse documents, audio, learning records, and learning assets in one workspace, with filters for course and type.

![KnowRealm library in the light theme](docs/img/desktop/PixPin_2026-10-30_15-01-41.png)

> [!NOTE]
> Some statistics, learning progress indicators, and audio waveforms in the screenshots are illustrative and are labeled accordingly in the app.

## Installation and Quick Start

### 1. Install the desktop app

Open [GitHub Releases](https://github.com/youyu-youth/KnowRealm-AI/releases), download the Windows x64 `.msi` installer, and run it. The installer includes the local backend and FFmpeg, so you do not need Python, Node.js, or development tools. The desktop interface requires WebView2 Runtime.

On first launch, follow the setup wizard to choose a data folder and complete setup. Use the attached `SHA256SUMS.txt` to verify the integrity of the installer.

> [!IMPORTANT]
> The v0.1.0 installer is not code-signed, so Windows may show an unknown publisher warning. Use a new data folder for this version; do not open data created by a newer development build. See the [v0.1.0 release notes](https://github.com/youyu-youth/KnowRealm-AI/releases/tag/v0.1.0) for compatibility limits.

### 2. Configure the AI services you need

Enter your own service credentials in Settings:

| Service                          | Configuration                                      | Used for                                                                             |
| -------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Large language model             | OpenAI-compatible API URL, model name, and API key | AI chat and generation of summaries, knowledge points, exercises, and learning plans |
| Tencent Cloud speech recognition | SecretId, SecretKey, and related credentials       | Transcribing recordings and imported audio                                           |
| Tavily (optional)                | API key                                            | Web search in AI chat                                                                |

> [!IMPORTANT]
> Local-first means your learning data is stored on your computer. When you use online AI, speech recognition, or web search, the relevant content is sent to your configured provider and may incur charges. Review and confirm external processing when prompted by the app.

### 3. Start learning

1. Import a document or paste some text.
2. Configure a language model, generate a summary, and review and confirm the content you want to keep.
3. Ask questions about your materials and follow citations, or continue organizing knowledge points, practicing, and creating learning plans.

### Supported import formats

| Type      | Formats                        | Requirements and limits                                                                                   |
| --------- | ------------------------------ | --------------------------------------------------------------------------------------------------------- |
| Text      | `.txt`, `.md`                  | UTF-8 encoding                                                                                            |
| Documents | `.pdf`, `.docx`                | PDFs must contain extractable text and must not require a password; OCR for scanned PDFs is not supported |
| Audio     | `.mp3`, `.aac`, `.wav`, `.m4a` | Up to 5 hours per file; transcription requires Tencent Cloud speech recognition credentials               |

## Data Storage

The default data folder is `%USERPROFILE%\KnowRealm`. You can open or move it from Settings, or use the data export and restore features.

```text
KnowRealm/
├── knowrealm.db     Learning records, assets, and task data
├── files/           Source materials and application files
├── config/          App settings and service provider configuration
├── cache/           Processing cache
├── exports/         Exported files
└── backups/         Backup files
```

## FAQ

### Can I use the app without configuring AI services?

Yes. You can import and read documents, save text, organize courses, and search existing content without an AI API key. AI summaries and chat require a configured language model; audio transcription uses Tencent Cloud speech recognition. Web clipping and web search require internet access.

### How do I back up my data or move to another computer?

Export your data from Settings, then use the data restore feature in the app on the destination computer. To change the storage location on the same computer, use data folder migration in Settings. Check version compatibility before restoring data into a different app version.

## Architecture and Tech Stack

KnowRealm-AI consists of a desktop interface and a local backend that starts with the app. Tauri manages windows, the system tray, shortcuts, and the backend process. The React interface accesses application features through a local API. UI actions and AI assistants share business services and controlled action entry points. SQLite stores application data and task state, while source materials remain in local folders.

| Area               | Technologies                                                         |
| ------------------ | -------------------------------------------------------------------- |
| Desktop interface  | Tauri 2, React 19, TypeScript, Vite, Tailwind CSS 4, shadcn/ui       |
| Local backend      | Python, FastAPI, SQLAlchemy, SQLite                                  |
| AI and tasks       | LangChain, LangGraph, Deep Agents, and a local persistent task queue |
| Search and parsing | SQLite FTS5, jieba, PyMuPDF, python-docx, FFmpeg                     |

```text
KnowRealm-AI/
├── apps/desktop/       React interface and native Tauri features
├── backend/            Local API, business services, AI, and background tasks
├── packages/api-types/ Shared API types for the frontend and backend
├── scripts/            Repository checks and validation scripts
└── docs/img/desktop/   Desktop app screenshots
```

## Development

The following instructions cover running from source and building an installer on Windows x64. The frontend uses a pnpm workspace; the backend uses uv. There is no root-level `package.json`.

### Prerequisites

| Tool                         | Requirement                                                                                                           |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Git and PowerShell           | Use PowerShell 7 for repository check scripts                                                                         |
| Node.js and pnpm             | Node.js 24 and pnpm 11.2.2 are recommended to match the current CI configuration                                      |
| Python and uv                | Python 3.12 or later; 3.13 is recommended. Use uv to manage backend dependencies                                      |
| Rust and Windows build tools | Stable Rust with the MSVC toolchain, Visual Studio Build Tools with Desktop development with C++, and the Windows SDK |
| WebView2 Runtime             | Required for the Tauri desktop interface                                                                              |

### Install dependencies and run

Run in PowerShell:

```powershell
git clone https://github.com/youyu-youth/KnowRealm-AI.git
cd KnowRealm-AI

pnpm install --frozen-lockfile
uv sync --frozen --directory backend

pnpm --filter @knowrealm/desktop tauri dev
```

The first development launch automatically downloads and verifies FFmpeg, which requires internet access. The command starts the desktop window, frontend, and local backend together; you do not need to start the backend separately.

### Make changes and run checks

UI code lives in `apps/desktop/src/`, native desktop features in `apps/desktop/src-tauri/`, and backend business modules in `backend/app/modules/`. After changing backend APIs, regenerate the shared types in `packages/api-types/`. Update both Chinese and English translations when changing UI text.

Run these commands from the repository root:

```powershell
# Check code style and types for the current changes
pwsh -NoProfile -File scripts/check-changed.ps1

# Check and build the frontend without creating a desktop installer
pnpm --filter @knowrealm/desktop build

# Run the full frontend and backend test suites sequentially
uv run --frozen --directory backend python -m scripts.run_tests all

# Regenerate shared types after backend API changes
pnpm --filter @knowrealm/api-types generate

# Check that API types match the backend
pnpm --filter @knowrealm/api-types check
```

### Build a Windows installer

After preparing the environment and installing dependencies above, run from the repository root:

```powershell
pnpm --filter @knowrealm/desktop release:msi
```

This command prepares FFmpeg, packages the local backend, builds the frontend, and generates an MSI installer. The default output folder is `apps/desktop/src-tauri/target/release/bundle/msi/`. Development builds and releases may use different data schemas. Export a backup and use separate data folders when switching versions.

## Feedback and Contributions

Use [Issues](https://github.com/youyu-youth/KnowRealm-AI/issues) to report problems or suggest improvements. For bug reports, include the app version, Windows version, steps to reproduce, and relevant logs. Remove API keys and other sensitive information before submitting.

When submitting a pull request, describe the problem, the main changes, and how you verified them.
