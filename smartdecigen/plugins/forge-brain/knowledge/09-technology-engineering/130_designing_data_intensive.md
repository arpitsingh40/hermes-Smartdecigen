# V130 · DESIGNING DATA-INTENSIVE APPLICATIONS — Martin Kleppmann
Tier 3 · Technology · Tree Memory

## ROOT
Every application built today is data-intensive — storage, retrieval, processing, and serving. Kleppmann provides the definitive guide to the foundational technologies: databases (relational, document, graph), storage engines, encoding formats, replication, partitioning, transactions, distributed consensus, batch and stream processing. The guiding principle: choose the right tool for the right job based on fundamental trade-offs (consistency vs availability, latency vs throughput, read-optimized vs write-optimized).

## TRUNK
Three pillars: (1) Foundations of Data Systems — reliability (fault-tolerant), scalability (handles growth), maintainability (operable, simple, evolvable). (2) Distributed Data — replication (leaders/followers, multi-leader, leaderless), partitioning (key-range, hash), transactions (ACID, snapshot isolation, serializability), consensus (Paxos, Raft), consistency models (linearizability, causal, eventual). (3) Derived Data — batch processing (MapReduce, dataflow), stream processing (message brokers, event sourcing, CQRS), the unification of batch and stream in modern architectures. The CAP theorem: in a network partition, choose consistency or availability — but the real world is about trade-offs at different levels of the stack.

## BRANCHES
- Data models: relational (structured, joins, ACID), document (schema-flexible, nested), graph (relationship-heavy queries). Most applications need multiple models for different use cases.
- Storage: B-trees (read-optimized, in-place updates) vs LSM-trees (write-optimized, append-only, compacted). Choice depends on workload — write-heavy needs LSM; read-heavy needs B-tree.
- Replication: single-leader (simplest, one writer), multi-leader (multi-datacenter, conflict-prone), leaderless (Dynamo-style, quorum reads/writes). Each handles failure differently.
- Partitioning: key-range (range queries efficient, hotspots possible), hash (uniform distribution, no range queries). Secondary indexes on partitioned data are hard.
- Consistency: the strongest guarantee you can afford while meeting latency/availability requirements. Eventual consistency is the default; stronger models need coordination (cost).
- Stream processing: turn events into insights in real-time. Uses: fraud detection, real-time dashboards, recommendation updates, monitoring.

## FRUIT
- WHEN choosing a database → APPLY data model + workload analysis: what kind of data (structured, document, graph)? What access patterns (reads vs writes, single-record vs analytics)?
- WHEN scaling problems arise → APPLY replication/partitioning diagnosis: is the bottleneck reads (add replicas), writes (rethink partitioning), or both (rethink architecture)?
- WHEN data is out of sync → APPLY consistency model check: is eventual consistency acceptable here, or does this operation need strong consistency?
- WHEN building a new service → APPLY the three pillars: is it reliable (handles faults)? Scalable (can grow 10x without rewrite)? Maintainable (can a new hire understand it)?

## SEEDS
- "Choose the data model that fits your queries, not the one you already know."
- "Replication solves read scale. Partitioning solves write scale. Both together solve everything — at a complexity cost."
- "Every distributed system faces a consistency/availability/latency trade-off. Know which you're trading."
- "Batch for correctness. Stream for freshness. The best architectures do both."
- "The best database decision is the one that's easy to change later."

## GRAFTS
- → Accelerate: the loosely coupled architecture that continuous delivery requires.
- → Building Microservices: the application architecture built on these data foundations.
