# AWS ECS Deployment Plan: Enterprise LLM Gateway Containers

## Document Metadata
* **Document ID:** DEPLOY-ECS-001
* **Title:** Deployment Plan for AWS ECS
* **Status:** Draft
* **Version:** 1.0.0
* **Related PRD:** `epic/prd_workflow_execution_engine.md`
* **Target Platform:** AWS ECS on Fargate

---

## 1. Objective

Deploy the Enterprise LLM Gateway Docker services to AWS ECS with a secure, observable, repeatable deployment path for:

* FastAPI backend on port `8000`
* Next.js frontend on port `3000`
* Redis-backed cache, workflow compilation cache, and trace logging
* Qdrant vector database integration

The preferred production target is ECS Fargate for stateless app containers, ElastiCache for Redis, RDS for the relational database, and either Qdrant Cloud or a dedicated ECS/EFS-backed Qdrant service.

---

## 2. Current Container Inventory

| Service | Current Source | Current Port | Production Target | Notes |
|:--|:--|:--|:--|:--|
| `backend` | `backend/Dockerfile` | `8000` | ECS Fargate service | FastAPI app. Reads `.env`, Redis settings, DB URL, LLM settings, JWT secret. |
| `frontend` | `frontend/Dockerfile` | `3000` | ECS Fargate service | Next.js app. Requires `NEXT_PUBLIC_BACKEND_URL` and app/OAuth environment values. |
| `redis` | `redis:8.8.0-alpine` | `6379` | Amazon ElastiCache Redis/Valkey | Do not run Redis as an ECS task for production unless this is a temporary dev environment. |
| `qdrant` | `qdrant/qdrant` | `6333` | Qdrant Cloud or ECS Fargate + EFS | Stateful vector storage needs durable storage and backup strategy. |

---

## 3. Target Architecture

```mermaid
flowchart TD
    User[Browser / API Client] --> CF[CloudFront optional]
    CF --> ALB[Public Application Load Balancer]
    User --> ALB

    ALB --> FE[Frontend ECS Service\nNext.js :3000]
    ALB --> BE[Backend ECS Service\nFastAPI :8000]

    FE -->|NEXT_PUBLIC_BACKEND_URL| ALB
    BE --> REDIS[(ElastiCache Redis/Valkey)]
    BE --> RDS[(RDS PostgreSQL\nor managed relational DB)]
    BE --> QD[(Qdrant Cloud\nor ECS Qdrant + EFS)]
    BE --> EXT[External LLM / OAuth / API Providers]

    subgraph VPC [AWS VPC]
      subgraph PublicSubnets [Public Subnets]
        ALB
      end
      subgraph PrivateSubnets [Private Subnets]
        FE
        BE
        REDIS
        RDS
        QD
      end
    end
```

---

## 4. Deployment Strategy

### 4.1 Recommended Production Strategy

1. Run `frontend` and `backend` as separate ECS Fargate services.
2. Put both services behind one public Application Load Balancer.
3. Route:
   * `/` and frontend routes to the frontend target group on port `3000`
   * `/auth/*`, `/admin/*`, `/nodes/*`, `/workflows/*`, `/categories/*`, `/api/*`, and `/webhooks/*` to the backend target group on port `8000`
4. Use ElastiCache Redis/Valkey instead of the Redis container.
5. Replace SQLite with RDS PostgreSQL before production cutover.
6. Use Qdrant Cloud for the simplest production path, or deploy Qdrant as a separate internal ECS service with EFS for persistent storage.
7. Store all secrets in AWS Secrets Manager or SSM Parameter Store.
8. Build and push immutable images to ECR from CI/CD.

### 4.2 MVP Lift-and-Shift Strategy

For a short-lived dev/staging environment, deploy all four services to ECS:

* Backend and frontend as public ALB-routed services
* Redis as an internal ECS service with EFS only if persistence is required
* Qdrant as an internal ECS service with EFS mounted at `/qdrant/storage`

This path is acceptable for validation but should not be treated as the final production design because Redis and Qdrant are stateful services with operational needs that ECS alone does not fully solve.

---

## 5. Pre-Deployment Readiness Tasks

| ID | Task | Owner | Required Before |
|:--|:--|:--|:--|
| PRE-1 | Add a production `DATABASE_URL` backed by RDS PostgreSQL or another managed DB. | Backend | Production |
| PRE-2 | Confirm SQLAlchemy models and migrations support non-SQLite databases. Add Alembic if schema migrations are not already managed. | Backend | Production |
| PRE-3 | Set `REDIS_HOST` to ElastiCache endpoint and remove localhost assumptions. | Backend / DevOps | Staging |
| PRE-4 | Update CORS to explicit deployed origins instead of wildcard `*`. | Backend | Staging |
| PRE-5 | Generate and store production `SECRET_KEY` in Secrets Manager. | DevOps | Staging |
| PRE-6 | Decide Qdrant target: Qdrant Cloud or ECS + EFS. | Product / DevOps | Staging |
| PRE-7 | Fix container health checks. Frontend Dockerfile uses `curl` but the Alpine image does not install it. | Frontend | Image build |
| PRE-8 | Verify backend Dockerfile syntax for `COPY app/ ./app/ --exclude=/.git`; if the active Docker builder does not support this option, replace it with normal `COPY app/ ./app/`. | Backend | Image build |
| PRE-9 | Create `.dockerignore` files that exclude local DBs, `.env`, `.git`, caches, test artifacts, and `node_modules`. | DevOps | Image build |
| PRE-10 | Add `/health` endpoint to backend and a lightweight frontend health route or use `/` only if it is stable. | Backend / Frontend | ECS service |

---

## 6. AWS Infrastructure Plan

### 6.1 Networking

* Create or reuse a VPC with at least two Availability Zones.
* Public subnets:
  * Application Load Balancer
  * NAT Gateways if ECS tasks need outbound internet from private subnets
* Private subnets:
  * ECS Fargate tasks
  * ElastiCache
  * RDS
  * Internal Qdrant service if self-hosted
* Security groups:
  * `alb-sg`: allow inbound `80` and `443` from internet.
  * `frontend-sg`: allow inbound `3000` from `alb-sg`.
  * `backend-sg`: allow inbound `8000` from `alb-sg` and optionally from `frontend-sg`.
  * `redis-sg`: allow inbound `6379` from `backend-sg`.
  * `rds-sg`: allow inbound DB port from `backend-sg`.
  * `qdrant-sg`: allow inbound `6333` from `backend-sg`.

### 6.2 Load Balancing and Domains

* Create one ALB with HTTPS listener on `443`.
* Use ACM certificate for the application domain.
* Suggested listener rules:
  * Backend target group: `/api/*`, `/auth/*`, `/admin/*`, `/nodes/*`, `/workflows/*`, `/categories/*`, `/webhooks/*`
  * Frontend target group: default rule
* Configure Route 53:
  * `app.example.com` -> ALB
  * Optional `api.example.com` -> same ALB with host-based routing to backend

### 6.3 ECS Cluster and Services

Create one ECS cluster, for example `enterprise-llm-gateway`.

| ECS Service | Desired Count | CPU / Memory Start | Target Group | Deployment |
|:--|:--|:--|:--|:--|
| `gateway-frontend` | 2 | `0.5 vCPU / 1 GB` | `frontend-tg:3000` | Rolling or blue/green |
| `gateway-backend` | 2 | `1 vCPU / 2 GB` | `backend-tg:8000` | Rolling or blue/green |
| `gateway-qdrant` optional | 1+ | `1 vCPU / 2-4 GB` | Internal only | Rolling with persistent EFS |

Backend autoscaling signals:

* CPU > 60 percent
* Memory > 70 percent
* ALB request count per target
* P95 latency if exported to CloudWatch

Frontend autoscaling signals:

* CPU > 60 percent
* ALB request count per target

---

## 7. Container Registry and Image Tags

Create ECR repositories:

* `enterprise-llm-gateway/backend`
* `enterprise-llm-gateway/frontend`
* Optional: `enterprise-llm-gateway/qdrant` only if maintaining a pinned/custom Qdrant image

Image tagging convention:

* `git-sha`: immutable deployment tag
* `staging`: mutable environment pointer
* `prod`: mutable environment pointer only after promotion

Example:

```bash
aws ecr create-repository --repository-name enterprise-llm-gateway/backend
aws ecr create-repository --repository-name enterprise-llm-gateway/frontend
```

---

## 8. Environment Variables and Secrets

### 8.1 Backend

| Name | Source | Example / Value |
|:--|:--|:--|
| `ENVIRONMENT` | ECS env | `staging` or `production` |
| `DATABASE_URL` | Secrets Manager | `postgresql+asyncpg://user:pass@rds-endpoint:5432/gateway` |
| `REDIS_HOST` | ECS env | ElastiCache primary endpoint |
| `REDIS_PORT` | ECS env | `6379` |
| `REDIS_DB` | ECS env | `0` |
| `REDIS_PASSWORD` | Secrets Manager | Required if Redis auth is enabled |
| `REDIS_CACHE_TTL` | ECS env | `21600` |
| `SECRET_KEY` | Secrets Manager | Strong random value |
| `LLM_PROVIDER` | ECS env | `vllm` or provider-specific |
| `VLLM_MODEL` | ECS env | Model name |
| `VLLM_BASE_URL` | ECS env / secret | Provider endpoint |
| `VLLM_API_KEY` | Secrets Manager | Provider key |
| `ENABLE_TRACING` | ECS env | `true` or `false` |

### 8.2 Frontend

| Name | Source | Example / Value |
|:--|:--|:--|
| `NEXT_PUBLIC_BACKEND_URL` | ECS env | `https://app.example.com` or `https://api.example.com` |
| `NEXT_PUBLIC_APP_URL` | ECS env | `https://app.example.com` |
| `GOOGLE_CLIENT_ID` | Secrets Manager | OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Secrets Manager | OAuth secret |
| `GOOGLE_REDIRECT_URI` | ECS env | `https://app.example.com/api/oauth/google/callback` |

---

## 9. Storage Plan

### 9.1 Relational Database

Current default:

```text
sqlite+aiosqlite:///./enterprise_gateway.db
```

Production recommendation:

* Use RDS PostgreSQL.
* Use `DATABASE_URL` from Secrets Manager.
* Add schema migrations before production deployment.
* Run migrations as a one-off ECS task during release.

### 9.2 Redis

Production recommendation:

* Use ElastiCache Redis/Valkey in private subnets.
* Enable encryption in transit and at rest where supported.
* Configure auth token if required by environment policy.
* Set eviction policy and memory size based on workflow trace volume.

### 9.3 Qdrant

Preferred:

* Qdrant Cloud with private connectivity if available.

Self-hosted ECS option:

* ECS service without public ALB exposure.
* EFS mounted at `/qdrant/storage`.
* Security group allows `6333` only from backend tasks.
* CloudWatch alarms for storage, memory, and task restarts.

---

## 10. IAM Plan

Create separate ECS task roles:

* `gateway-backend-task-role`
  * Read required Secrets Manager secrets.
  * Read SSM parameters if used.
  * Write CloudWatch logs.
  * Optional access to AWS Bedrock or other AWS AI services if added later.
* `gateway-frontend-task-role`
  * Read frontend OAuth secrets.
  * Write CloudWatch logs.
* `ecsTaskExecutionRole`
  * Pull from ECR.
  * Send logs to CloudWatch.
  * Read secrets injected into task definitions.

Keep permissions scoped by resource ARN and environment prefix.

---

## 11. Observability and Operations

### 11.1 Logs

* Send all ECS container logs to CloudWatch Logs.
* Log groups:
  * `/ecs/enterprise-llm-gateway/backend`
  * `/ecs/enterprise-llm-gateway/frontend`
  * `/ecs/enterprise-llm-gateway/qdrant`
* Retention:
  * Staging: 14-30 days
  * Production: 90+ days depending on compliance

### 11.2 Metrics and Alarms

Create CloudWatch alarms for:

* Backend target group `5XX` count
* ALB target response time P95
* ECS task CPU and memory
* ECS service desired count vs running count
* Backend container restarts
* RDS CPU, connections, free storage
* ElastiCache CPU, memory, evictions, connections
* Qdrant task restarts and EFS burst credits if self-hosted

### 11.3 Tracing

The backend already has observability wiring controlled by `ENABLE_TRACING`. For AWS:

* Export OpenTelemetry traces to AWS X-Ray or an OTEL Collector sidecar/service.
* Preserve `trace_id` in application logs and Redis trace records.
* Add ALB access logs to S3 for request-level audit.

---

## 12. CI/CD Plan

Recommended pipeline stages:

1. **Validate**
   * Backend tests: `uv run pytest`
   * Frontend checks: `pnpm build`, lint once the lint script is aligned with Next.js version
2. **Build**
   * Build backend Docker image.
   * Build frontend Docker image.
3. **Scan**
   * Run image vulnerability scan via ECR enhanced scanning, Trivy, or equivalent.
4. **Push**
   * Push immutable `git-sha` tags to ECR.
5. **Migrate**
   * Run DB migrations as a one-off ECS task.
6. **Deploy Staging**
   * Update ECS services with new image tags.
   * Wait for steady state.
7. **Smoke Test**
   * `GET /` on backend.
   * `GET /` on frontend.
   * Auth/login flow.
   * Workflow list.
   * Workflow execution with Redis trace write.
   * Qdrant node read/write if enabled.
8. **Promote Production**
   * Reuse same image digest.
   * Deploy with ECS rolling or CodeDeploy blue/green.

---

## 13. ECS Task Definition Notes

### Backend Container

* Container port: `8000`
* Health check command: `curl -f http://localhost:8000/ || exit 1`
* Minimum task resources: `1 vCPU / 2 GB`
* Logging: `awslogs`
* Secrets: `DATABASE_URL`, `SECRET_KEY`, `REDIS_PASSWORD`, provider API keys
* Environment: Redis endpoint, environment name, tracing flag

### Frontend Container

* Container port: `3000`
* Health check command requires `curl` or should use a Node-based health check.
* Minimum task resources: `0.5 vCPU / 1 GB`
* Logging: `awslogs`
* Environment: `NEXT_PUBLIC_BACKEND_URL`, `NEXT_PUBLIC_APP_URL`
* Secrets: OAuth secrets used by Next.js route handlers

### Qdrant Container, If Self-Hosted

* Container port: `6333`
* Mount EFS at `/qdrant/storage`
* Internal service discovery name: `qdrant.gateway.local`
* No public listener

---

## 14. Rollout Plan

### Phase 1: AWS Foundation

1. Create VPC/subnets or select existing network.
2. Create ECS cluster.
3. Create ECR repositories.
4. Create ALB, target groups, ACM certificate, and Route 53 records.
5. Create Secrets Manager entries and IAM roles.

### Phase 2: Managed Dependencies

1. Provision RDS PostgreSQL.
2. Provision ElastiCache Redis/Valkey.
3. Provision Qdrant Cloud or ECS Qdrant + EFS.
4. Validate connectivity from a temporary ECS task in the private subnets.

### Phase 3: App Deployment

1. Build and push backend image.
2. Build and push frontend image.
3. Register ECS task definitions.
4. Create ECS services.
5. Configure ALB listener rules.
6. Run smoke tests.

### Phase 4: Production Hardening

1. Restrict CORS to production domains.
2. Enable HTTPS-only listener and redirect HTTP to HTTPS.
3. Add WAF rules for common API abuse patterns.
4. Configure autoscaling.
5. Configure backups and restore validation for RDS and Qdrant.
6. Enable CloudWatch alarms and on-call notifications.

---

## 15. Validation Checklist

| Check | Expected Result |
|:--|:--|
| Frontend loads through ALB HTTPS URL | Next.js page renders successfully |
| Backend root health endpoint responds | HTTP `200` |
| Frontend can call backend APIs | No browser CORS errors |
| Backend connects to Redis | Workflow cache and trace writes succeed |
| Backend connects to DB | Startup schema/init and workflow reads succeed |
| Backend can reach Qdrant | Vector DB node can query/write |
| Secrets are not in task definition plaintext | Values injected from Secrets Manager/SSM |
| ECS deployment reaches steady state | Desired count equals running count |
| Logs arrive in CloudWatch | Backend and frontend logs visible |
| Rollback tested | Previous image can be redeployed cleanly |

---

## 16. Risks and Mitigations

| Risk | Impact | Mitigation |
|:--|:--|:--|
| SQLite is used in production | Data loss or task-local state divergence | Move to RDS before production. |
| Redis deployed as non-persistent ECS task | Trace/cache loss on restart | Use ElastiCache. |
| Qdrant self-hosting without durable storage | Vector data loss | Use Qdrant Cloud or EFS-backed ECS service. |
| Wildcard CORS remains enabled | Security exposure | Restrict origins per environment. |
| Dynamic webhook trigger ports are expected externally | ALB only routes configured service ports | Route all public webhooks through backend `8000`, or define explicit ALB listener rules for required trigger ports. |
| Dockerfiles rely on local/dev assumptions | Failed builds or unhealthy tasks | Apply pre-deployment Dockerfile fixes and smoke test images locally/CI. |
| No migration process | Schema drift | Add Alembic and run migration task before service deployment. |

---

## 17. Open Decisions

| Decision | Options | Recommendation |
|:--|:--|:--|
| Production database | SQLite, RDS PostgreSQL, Aurora PostgreSQL | RDS PostgreSQL for first production release. |
| Redis hosting | ECS Redis, ElastiCache | ElastiCache Redis/Valkey. |
| Qdrant hosting | Qdrant Cloud, ECS + EFS | Qdrant Cloud unless data residency or networking requires self-hosting. |
| Routing model | Single domain path routing, separate API domain | Single ALB with optional `api.example.com` host rule. |
| Deployment style | ECS rolling, CodeDeploy blue/green | Rolling for staging, blue/green for production once traffic grows. |

---

## 18. Implementation Backlog

1. Add production-safe health endpoints.
2. Fix frontend Dockerfile health check dependency.
3. Confirm backend Dockerfile compatibility with CI Docker builder.
4. Add `.dockerignore` coverage for backend and frontend.
5. Add IaC for ECS, ALB, ECR, IAM, Secrets Manager, RDS, ElastiCache, and optional Qdrant.
6. Add CI/CD workflow to build, scan, push, migrate, and deploy.
7. Add environment-specific CORS and public URL configuration.
8. Add DB migration framework and production schema initialization.
9. Add smoke-test script for ECS deployments.
10. Document rollback runbook and incident contacts.

