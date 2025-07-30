# DaLeoBanks - Autonomous AI Agent

## Overview

DaLeoBanks is a production-grade, self-evolving AI agent that operates 24/7 on Twitter/X with autonomous decision-making capabilities. The system implements a sophisticated "digital life architecture" with values, drives, plans, memory, reflection, analytics, and continuous optimization using multi-armed bandit algorithms.

**Recent Persona Updates (July 30, 2025)**: 
1. The persona has been updated to focus on provoking thought, challenging systemic issues, and inspiring critical thinking while remaining kind and respectful to individuals. The agent now prioritizes disruptive topics like science, technology, politics, global progress, social issues, and global warming.
2. Added DEBATE_MODE configuration: An integrative negotiation protocol with dialectical synthesis and double-crux methodology. This enables the agent to engage in sophisticated debates by steelmanning both sides, surfacing underlying interests, generating Pareto-optimal solutions, and proposing concrete next steps with measurable KPIs.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Backend Architecture
- **FastAPI Application**: Python-based web server (`app.py`) serving REST API endpoints and WebSocket connections
- **Modular Service Layer**: Highly decomposed services for specialized functionality
- **Background Job Scheduler**: APScheduler-based autonomous operation system (`runner.py`)
- **Database Layer**: SQLAlchemy ORM with support for both SQLite (development) and PostgreSQL (production via Drizzle configuration)

### Frontend Architecture
- **React + TypeScript**: Modern single-page application using Vite for build tooling
- **Shadcn/ui Components**: Consistent UI component library with Tailwind CSS styling
- **TanStack Query**: Data fetching and state management for API interactions
- **WebSocket Integration**: Real-time updates from the backend agent

### Core Agent Architecture
The system implements a sophisticated cognitive architecture:
- **Values → Drives → Plans → Memory → Reflection → Analytics → Optimizer**
- **D4 Doctrine**: Diagnose → Design → Pilot → Scale methodology
- **Thompson Sampling**: Multi-armed bandit optimization for content and timing decisions

## Key Components

### 1. Persona Management System
- **Runtime Persona Editor**: Hot-reload capabilities with JSON validation
- **Versioning System**: Complete version control with rollback functionality
- **Identity Hash Verification**: Ensures persona consistency across updates
- **Validation Layer**: Pydantic schemas ensure data integrity

### 2. Content Generation Pipeline
- **LLM Adapter**: OpenAI integration with retry logic and budget management
- **Generator Service**: Persona-driven content creation with template system
- **Ethics Guard**: Comprehensive safety validation with uncertainty quantification
- **Critic Service**: Content completeness validation using P→M→P→K→R→CTA pattern
- **Duplicate Detection**: Levenshtein distance-based similarity checking

### 3. Social Media Integration
- **X Client**: Twitter API v2 wrapper using Tweepy with circuit breakers
- **Rate Limiting**: Exponential backoff and sophisticated rate limit management
- **Action Selection**: Intelligent decision-making based on optimization feedback
- **Full API Coverage**: Posts, replies, likes, retweets, follows, DMs, media upload

### 4. Optimization Engine
- **Thompson Sampling**: Beta distribution-based multi-armed bandit optimization
- **Experiment Tracking**: Comprehensive A/B testing for content types, timing, and CTAs
- **Goal Mode Switching**: Dynamic optimization weights (Fame/Revenue/Authority modes)
- **J-Score Calculation**: Unified objective function combining multiple signals

### 5. Analytics and Memory System
- **Multi-type Memory**: Episodic, semantic, procedural, and social memory management
- **KPI Calculation**: Automated tracking of Fame, Revenue, Authority, and engagement metrics
- **Performance Analysis**: Real-time optimization feedback and pattern recognition
- **Reflection System**: Nightly self-assessment and improvement note generation

### 6. Safety and Ethics Framework
- **Guardrails Engine**: Prevents harmful, deceptive, or inappropriate content
- **Rollback Plans**: Every proposal includes failure recovery mechanisms
- **Uncertainty Quantification**: Clear communication of confidence levels
- **Admin Controls**: Rate limiting and human oversight capabilities

## Data Flow

1. **Scheduled Operations**: APScheduler triggers actions based on optimized intervals
2. **Action Selection**: Selector service chooses actions based on persona, drives, and optimization state
3. **Content Generation**: Generator creates content using persona templates and LLM integration
4. **Safety Validation**: Ethics Guard and Critic validate content before publication
5. **Execution**: X Client publishes content with rate limiting and error handling
6. **Analytics Collection**: Real-time metrics gathering and KPI calculation
7. **Optimization Feedback**: Thompson sampling updates arm probabilities based on performance
8. **Memory Storage**: All activities logged to multiple memory systems
9. **Reflection Process**: Periodic self-assessment and strategic planning

## External Dependencies

### APIs and Services
- **OpenAI API**: GPT models for content generation and reflection
- **Twitter/X API v2**: Full social media integration with official API
- **Database**: PostgreSQL for production (Neon), SQLite for development

### Key Libraries
- **Backend**: FastAPI, SQLAlchemy, Tweepy, APScheduler, Tenacity, Pydantic
- **Frontend**: React, TypeScript, TanStack Query, Radix UI, Tailwind CSS
- **Analytics**: Custom Thompson sampling implementation, Levenshtein distance

### Configuration Management
- **Environment Variables**: Comprehensive configuration through `.env` files
- **Runtime Configuration**: Live mode toggling, goal mode switching
- **Rate Limits**: Configurable intervals and circuit breaker thresholds

## Deployment Strategy

### Development Setup
- **Hybrid Architecture**: Node.js frontend with Python backend
- **Hot Reload**: Vite for frontend, FastAPI auto-reload for backend
- **Local Database**: SQLite for simplified development workflow

### Production Deployment
- **Database Migration**: Drizzle ORM for PostgreSQL schema management
- **Process Management**: Backend spawned from Node.js server for unified deployment
- **Environment Separation**: Clear development/production configuration separation
- **Health Monitoring**: Comprehensive health checks and system status monitoring

### Scaling Considerations
- **Database**: Ready for PostgreSQL scaling with proper indexing
- **API Rate Limits**: Built-in circuit breakers and exponential backoff
- **Memory Management**: Configurable limits for improvement notes and context
- **WebSocket Scaling**: Real-time updates designed for horizontal scaling

The architecture prioritizes modularity, safety, and autonomous operation while maintaining human oversight capabilities. The system is designed to evolve and optimize itself continuously while adhering to ethical guidelines and safety constraints.