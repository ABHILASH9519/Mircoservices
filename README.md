# Microservices & Distributed Systems

A collection of independent projects for backend engineering, cloud-native architecture, service development and distributed computing.

| Project directory | Architecture | What it contains |
|---|---|---|
| [CloudSentinels](CloudSentinels) | Multi-service | Multi-service observability and incident automation (Go, Floci, n8n, Kubernetes). |
| [Distributed-MapReduce-Framework](Distributed-MapReduce-Framework) | Distributed system | Independent Go RPC coordinator and worker processes. |
| [RAGForge](RAGForge) | Modular single-service | Go corrective RAG API, UI and CLI. |
| [Echo-Assist](Echo-Assist) | Service-oriented app | Node API, MCP task tools, persistence and optional LLM integration. |
| [Cloud-Access-SaaS-Platform](Cloud-Access-SaaS-Platform) | API service | Express authentication API with PostgreSQL/Prisma. |
| [Nexus-Research-Engine](Nexus-Research-Engine) | Service-oriented workspace | Research frontend/backend workspace. |
| [LunarReg-Workbench](LunarReg-Workbench) | Service-oriented app | Go image registration API and Python tooling. |
| [Sahaara](Sahaara) | Service-backed app | Go API and independent Android and iOS clients. |

## Repository structure

Each directory is a Git submodule pinned to its source repository's main-branch commit. This preserves every project's own source files, documentation, dependencies, configuration, and Git history. Projects do not share a root runtime, package manager or deployment pipeline.

```sh
git clone --recurse-submodules https://github.com/ABHILASH9519/Mircoservices.git
cd Mircoservices
```

After cloning normally, fetch the project directories with `git submodule update --init --recursive`. Open a project's own README for its setup instructions. To update an individual project snapshot, record its new submodule commit in the collection.

## Portfolio scope

The collection includes independently deployable service-oriented apps alongside distributed and multi-service systems. Each project retains its own architectural classification in the table. No services are launched by cloning or updating this collection.
