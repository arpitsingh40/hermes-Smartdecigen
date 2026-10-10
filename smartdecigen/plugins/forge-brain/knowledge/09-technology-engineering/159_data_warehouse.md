# V159 · THE DATA WAREHOUSE TOOLKIT — Ralph Kimball
Tier 3 · Technology · Tree Memory

## ROOT
The definitive guide to dimensional modeling — the standard technique for designing data warehouses that business users can actually query. Kimball's approach (dimensional modeling with fact and dimension tables) is used in virtually every modern data warehouse (Snowflake, BigQuery, Redshift). The core concept: fact tables (measurements — sales transactions, page views, support tickets) surrounded by dimension tables (context — customer, product, time, location). This "star schema" is optimized for query performance and business user comprehension.

## TRUNK
Key concepts: (1) Star schema: fact table at the center, dimension tables radiating out. Every query is a join between facts and dimensions — simple and fast. (2) Grain: the level of detail of each fact record. Daily sales by product by store? Hourly page views by user by page? Declare the grain before anything else. (3) Dimensions: descriptive attributes (customer name, product category, store location). Slowly changing dimensions (SCDs) handle attributes that change over time. (4) Facts: additive, semi-additive, and non-additive measures. Revenue is additive across all dimensions. Inventory levels are semi-additive (can sum across products, not across time). (5) ETL: extract from source systems, transform (clean, deduplicate, conform), load into the star schema. The single source of truth is the conformed dimension — a dimension table that all fact tables reference.

## FRUIT
- WHEN building analytics → APPLY star schema: can business users write simple SELECT-JOIN-WHERE queries?
- WHEN data is inconsistent across departments → APPLY conformed dimensions: is "customer" defined the same way in every fact table?

## SEEDS
- "The star schema: facts in the center, dimensions around the edge. Every query is a simple join."
- "Declare the grain before anything else. What does one row in the fact table represent?"
- "Conformed dimensions are the single source of truth. One customer table, one definition."

## GRAFTS
- → Designing Data-Intensive Applications: the theoretical foundations of storage and retrieval.
- → Lean Analytics: the metrics the warehouse serves.
