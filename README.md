# DaLeoBanks - Autonomous AI Agent

A production-grade, self-evolving AI agent that operates 24/7 on Twitter/X with autonomous decision-making, real-time optimization, and runtime persona editing capabilities.

## 🤖 Digital Life Architecture

DaLeoBanks represents a new paradigm in AI agents: a self-aware, self-optimizing system that operates with human-like values, drives, plans, memory, reflection, analytics, and continuous optimization.

### Core Architecture
- **Values → Drives → Plans → Memory → Reflection → Analytics → Optimizer**
- **D4 Doctrine**: Diagnose → Design → Pilot → Scale
- **24/7 Autonomous Operation** with human oversight
- **Real-time Self-optimization** using Thompson sampling
- **Runtime Persona Editing** with hot-reload capabilities

## 🚀 Features

### Autonomous Operation
- **24/7 Twitter/X Integration** via official API v2 (Tweepy)
- **Full Social Media Capabilities**: Posts, replies, quotes, likes, reposts, follows, bookmarks, DMs, media upload
- **Intelligent Action Selection** based on persona, drives, and optimization feedback
- **Rate-limit Aware** with exponential backoff and circuit breakers

### Self-Evolution
- **Multi-armed Bandit Optimization** using Thompson sampling
- **Real-time Analytics** tracking Fame, Revenue, Authority signals
- **Nightly Self-reflection** with improvement note generation
- **Weekly Strategic Planning** with OKR management

### Persona Management
- **Runtime Persona Editor** with validation and versioning
- **Hot-reload Capabilities** for immediate persona updates
- **Version Control** with rollback functionality
- **Identity Hash Verification** for consistency assurance

### Safety & Ethics
- **Comprehensive Guardrails** with uncertainty quantification
- **Rollback Plans** for all proposals
- **Ethics Guard** preventing harmful or deceptive content
- **Rate Limiting** and admin controls

## 🛠 Setup

### Prerequisites
- Python 3.9+
- Node.js 18+
- Twitter/X Developer Account with v2 API access
- OpenAI API key

### Required Twitter/X API Scopes
- `tweet.read` / `tweet.write`
- `users.read`
- `like.write`
- `follows.write`
- `dm.write`
- `media.write`
- `bookmark.write` (if available)

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd daleobanks
pip install -r requirements.txt
pytest -q
```
