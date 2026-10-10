# V132 · BUILDING MICROSERVICES — Sam Newman
Tier 3 · Technology · Tree Memory

## ROOT
Microservices are an architectural style where applications are decomposed into small, independent services that communicate over the network. The benefits (independent deployability, technology heterogeneity, scaling by service, organizational alignment) are real — but so are the costs (network latency, distributed data, eventual consistency, operational complexity). Newman's core argument: microservices are NOT a default. You should start with a monolith and split services when the monolith's pain justifies the distributed system's complexity.

## TRUNK
When to split: (1) independent deployability is needed (different services at different cadences), (2) different scaling profiles (one service needs 10x the resources of others), (3) organizational scaling (multiple teams need to work independently), (4) different technology choices are justified by the domain. Key principles: model services around business domains (bounded contexts from DDD), not technical layers. Services should be loosely coupled (changes in one don't require coordinated changes in others) and highly cohesive (related behavior stays together). Integration: prefer asynchronous event-driven communication over synchronous HTTP. Data: each service owns its own data store — never share a database across services. The hardest part: distributed transactions don't exist; use sagas (sequences of local transactions with compensating actions for failure).

## BRANCHES
- Decomposition: start with a modular monolith. Define clear module boundaries. When one module's deployment cadence, scaling profile, or team ownership demands independence, extract it.
- Communication: synchronous (request/response — simple, tight coupling) vs asynchronous (events — decoupled, eventual consistency, harder to reason about). The default should be async.
- Data management: the single most common microservices failure is shared databases. Each service owns its data. Data that needs to be joined is replicated via events (CQRS pattern).
- Testing: unit (in-process), integration (service with real dependencies), contract (consumer-driven contracts verify compatibility), end-to-end (rare, expensive, fragile).
- Deployment: each service gets its own CI/CD pipeline. Canary deployments, feature flags, and monitoring are non-negotiable at scale.

## FRUIT
- WHEN considering microservices → APPLY the monolith-first test: what is the specific, measurable pain the monolith causes that microservices would fix?
- WHEN services are tightly coupled → APPLY bounded context mapping: do service boundaries match business domain boundaries? Redraw them.
- WHEN data consistency is breaking → APPLY saga pattern: can this distributed operation be modeled as a sequence of local transactions?
- WHEN services are hard to test → APPLY contract testing: use consumer-driven contracts, not end-to-end tests.

## SEEDS
- "Microservices are not a default. Start with a monolith. Split when it hurts."
- "Each service owns its data. Shared databases are the #1 microservices failure mode."
- "Services should be loosely coupled and highly cohesive — like well-designed classes."
- "Distributed transactions don't exist. Use sagas with compensating actions."
- "Model services around business domains, not technical layers."

## GRAFTS
- → Designing Data-Intensive Applications: the data infrastructure microservices run on.
- → Accelerate: the CI/CD and deployment practices for independent services.
- → Site Reliability Engineering: operating distributed systems at scale.
