# UniVoice 🎙️

UniVoice is a scalable, microservices-based polling platform designed for university environments. Deployed using **Docker Swarm**, it features a robust architecture with single sign-on (SSO) authentication, role-based access control (RBAC), and distributed caching.

## 🚀 Tech Stack & Architecture

*   **Backend Services:** Python (Flask/FastAPI), SQLAlchemy (ORM)
*   **Infrastructure & Orchestration:** Docker, Docker Swarm
*   **Identity & Access Management:** Keycloak (OIDC)
*   **Database:** PostgreSQL
*   **Caching & Rate Limiting:** Redis
*   **Testing:** Pytest

## ✨ Key Features

*   **Microservices Architecture:** Composed of specialized, independent services (`poll_manager`, `poll_promoter`, `profile_service`, `db_backup`).
*   **SSO & Role-Based Access:** Integrated Keycloak for secure authentication. UI and endpoints adapt based on user roles (e.g., Student vs. Professor).
*   **Distributed Systems Implementation:**
    *   **Rate Limiting:** Global rate limiting across all replicas using Redis to prevent API abuse.
    *   **Distributed Caching:** Shared Redis cache between replicas to optimize database queries for profile statistics and poll results.
*   **Secure Networking:** Strict Docker network segmentation (`app-net`, `db-net`, `idp-net`) ensuring services only communicate on a need-to-know basis via Docker DNS.
*   **High Availability:** Ready for deployment with multiple replicas, load-balancing, and persistent data storage.

---

## 🛠️ Quick Start (Local / WSL)

The stack can be deployed seamlessly using the provided scripts and Docker Swarm.

### 1. Initialize Docker Swarm
If Swarm is not active on your machine, initialize it:
```bash
docker swarm init
