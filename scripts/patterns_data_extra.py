"""Full entries for the four non-GoF pattern families.

Companion to patterns_data.py, which holds the 23 Gang of Four patterns. The
other four families lived in gen_pattern_catalogue.py as name+description
tuples, so they rendered as one-liners. This module gives them the same depth.

Each entry:
    what      one-line definition
    where     a real system that ships it, so the pattern is not hypothetical
    how       the mechanism, concretely
    why       the problem it exists for
    adv       what you gain
    dis       what you lose -- specific, not "adds complexity"
    tradeoff  the single sentence to remember, as "X bought with Y"
    top1      what an experienced engineer does that a competent one does not
    case      a real, named case study with its public source where one exists.
              Where no named case is public, it says so rather than inventing one.
    diagram   a Mermaid body -- no fences -- showing what the prose cannot.
              Constrained by scripts/check_mermaid.py: quoted labels, no
              ampersands, semicolons, hashes or parentheses inside labels.
"""


def P(what, where, how, why, adv, dis, tradeoff, top1, case, diagram):
    return dict(what=what, where=where, how=how, why=why, adv=adv, dis=dis,
                tradeoff=tradeoff, top1=top1, case=case, diagram=diagram)


EIP = {
"Message Channel": P(
    "A named, addressable conduit that decouples a producer from a consumer in time and in space.",
    "Kafka topics, RabbitMQ queues and exchanges, SQS queues, NATS subjects, Redis Streams.",
    "The producer writes to a name rather than to an address. The broker owns the buffer, the "
    "retention rule and the delivery semantics, and neither endpoint holds a reference to the "
    "other.",
    "A direct call requires both parties to be up at the same instant and to know where the other "
    "lives. A channel removes both requirements — and gives you somewhere to put messages while "
    "the consumer is being redeployed.",
    "Producer and consumer scale, deploy and fail independently. The buffer absorbs bursts. New "
    "consumers attach without touching the producer.",
    "The channel is now a component with its own capacity, retention window and failure modes — "
    "and it is routinely the least redundant thing in the diagram. No stack trace crosses it. The "
    "worst failure is silent: a consumer whose lag exceeds the retention window loses data with no "
    "error raised anywhere, because from the broker's point of view nothing went wrong.",
    "Temporal decoupling bought with an intermediary you must now operate.",
    "They treat the channel name and its payload schema as a **published API with more owners than "
    "any REST endpoint** — a topic with nine consumers has nine contracts, and none of them are in "
    "your repository. So the schema is registered and versioned from the first message, and one "
    "channel never carries two message types, because the second type is how you discover that "
    "three consumers were doing a type check you did not know about. They also alarm on consumer "
    "lag *as a fraction of the retention window* rather than as a message count, because that is "
    "the only number that tells you how long you have before loss. The tell of an amateur channel: "
    "a topic called `events`.",
    "LinkedIn built Kafka because their point-to-point pipelines had become an N by M mesh of "
    "bespoke feeds, each of which had to be rebuilt when a new consumer wanted the same data — "
    "described in Kreps, Narkhede and Rao, *Kafka: a Distributed Messaging System for Log "
    "Processing* at NetDB 2011. The named topic replaced the mesh. The schema registry that grew "
    "up beside it at LinkedIn, later Confluent Schema Registry, exists because a named channel "
    "with an unversioned payload only postpones the coupling.",
    """flowchart LR
    P["Producer"] -->|"append"| CH["Topic orders.v1<br/>retention 7 days"]
    CH --> C1["Consumer A<br/>lag 400 messages"]
    CH --> C2["Consumer B<br/>lag 6 days of data"]
    C2 -.->|"falls past retention"| L["Silent data loss<br/>no error on either side"]
    style L fill:#2b1c17,stroke:#e0705a,color:#e4ecea"""),

"Point-to-Point Channel": P(
    "A channel where each message is delivered to exactly one receiver, however many are listening.",
    "SQS standard and FIFO queues, RabbitMQ work queues, Azure Service Bus queues, Kafka within a "
    "single consumer group.",
    "The broker hands a message to one consumer and hides it from the others for a visibility "
    "timeout. The consumer acknowledges and the broker deletes it. No acknowledgement inside the "
    "window, and it reappears for someone else.",
    "Work should be done once. Broadcasting a job to every worker means doing it N times, and "
    "having workers coordinate among themselves to claim work is a distributed lock you did not "
    "want to write.",
    "Trivial horizontal scaling — add a worker. The broker does distribution, retry and crash "
    "detection for free. A dead worker's message is automatically reassigned.",
    "'Exactly one receiver' is not 'exactly once'. A consumer that finishes the work and dies "
    "before acknowledging causes redelivery, so every handler must be idempotent. A visibility "
    "timeout shorter than the real processing time produces duplicate processing that shows up as "
    "a data anomaly rather than as an error — nothing logs it.",
    "Guaranteed single delivery bought with at-least-once semantics the handler must absorb.",
    "They set the visibility timeout from the observed p99.9 of the handler, not its mean, and "
    "then extend the lease from inside long handlers rather than raising the global timeout — "
    "because a timeout sized for the slowest job makes every genuine crash take that long to "
    "recover, which is the hidden cost of the obvious fix. They also know that ordering is not "
    "part of this pattern and never was: SQS standard queues are documented as best-effort "
    "ordering, and reaching for FIFO to get it back costs orders of magnitude of throughput and "
    "introduces a message group id which then becomes the real concurrency limit — a FIFO queue "
    "with one group is a single-threaded system with extra steps.",
    "Amazon SQS is the reference implementation and its own documentation is unusually honest "
    "about the trade: standard queues promise at-least-once delivery and best-effort ordering, "
    "while FIFO queues promise exactly-once processing within a deduplication window and order "
    "within a message group, at a base quota of 300 API calls per second per action without "
    "high-throughput mode. Teams routinely discover the second number after they have already "
    "committed to FIFO to fix an ordering bug they should have fixed by partitioning.",
    """sequenceDiagram
    participant Q as Queue
    participant W1 as Worker1
    participant W2 as Worker2
    Q->>W1: deliver msg 42, hidden for 30s
    Note over W1: handler actually takes 45s
    Q->>W2: 30s elapsed, redeliver msg 42
    W2->>Q: ack, work done
    W1->>Q: ack arrives too late
    Note over Q,W2: msg 42 processed twice and nothing logged it"""),

"Publish-Subscribe": P(
    "A channel where every subscriber receives its own copy of every message.",
    "SNS topics, Kafka topics read by multiple consumer groups, Google Cloud Pub/Sub, MQTT, "
    "webhooks.",
    "The broker keeps a subscription list and delivers each message once per subscriber, tracking "
    "delivery position independently for each. A subscriber's failure to keep up affects only its "
    "own position.",
    "The publisher should not need to know who cares. Adding the fifth consumer of an order event "
    "should not require a change, a review or a deploy in the order service.",
    "Consumers are added without touching the producer. Each consumer fails, lags and retries "
    "independently. One event can drive analytics, search indexing, email and audit without the "
    "producer knowing any of them exist.",
    "The publisher cannot enumerate its own dependants, which makes any change to the payload an "
    "unbounded-risk change. Fan-out cost is linear in subscriber count, so a topic with 200 "
    "subscribers is 200 deliveries. Ordering across subscribers is meaningless, and a slow "
    "subscriber that is also a webhook endpoint will exert no backpressure — it will just quietly "
    "fall behind or be dropped by the broker's retry policy.",
    "Unlimited extensibility bought with the loss of any knowledge of your own blast radius.",
    "They decide, explicitly, between *event notification* and *event-carried state transfer* — "
    "Fowler's 2017 taxonomy in *What do you mean by Event-Driven* — because that one choice "
    "determines whether pub/sub actually decoupled anything. Publishing a thin `OrderPlaced` with "
    "just an id forces every subscriber to call back for the detail, turning one publish into N "
    "synchronous reads against you and re-coupling all of them to your API and your uptime; you "
    "have added a broker and kept the coupling. Publishing the state avoids that at the cost of "
    "fatter messages and a payload that is now genuinely a contract. The second thing they do is "
    "make subscription a registered, audited act rather than a self-service one, so that the "
    "publisher can at least *find* its dependants even though the protocol does not require it.",
    "AWS's canonical fan-out guidance is to subscribe SQS queues to an SNS topic rather than "
    "subscribing endpoints directly, and the reason is instructive: SNS's retry policy for HTTP "
    "subscribers is fixed and finite, so a subscriber that is down longer than the retry schedule "
    "loses the message permanently and cannot replay it. Putting a queue in front of each "
    "subscriber gives every consumer its own durable buffer and its own DLQ. Kafka reaches the "
    "same place differently: one topic is pub/sub across consumer groups and point-to-point within "
    "one, which is why it can replace both patterns with a single primitive.",
    """flowchart TD
    E["OrderPlaced"] --> T{"What is in the payload"}
    T -->|"notification, just an id"| N["4 subscribers<br/>each calls back for detail"]
    N --> B["Order service takes 4x read load<br/>and is still coupled to all of them"]
    T -->|"state transfer, full order"| S["4 subscribers<br/>no callback needed"]
    S --> G["Order service never hears from them<br/>payload is now a hard contract"]
    style B fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style G fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),

"Message Router": P(
    "A component that consumes from one channel and forwards each message to one of several "
    "others, without changing the message.",
    "Kafka's producer partitioner, RabbitMQ exchange bindings, Azure Service Bus subscriptions, "
    "Envoy route tables.",
    "A routing function maps some attribute of the message — a key, a header, a topic name — to a "
    "destination. The classic is a hash of a partition key modulo the partition count.",
    "Consumers need work divided so it can be parallelised, and some of that division has to "
    "preserve a property, usually per-key ordering. Doing it in the consumers requires them to "
    "coordinate.",
    "Parallelism without coordination. Per-key ordering is preserved for free if the key routes "
    "deterministically. The routing rule is one place to change.",
    "The routing key is a data-modelling decision disguised as a configuration value: it fixes "
    "your maximum parallelism and your hot spots for the life of the topic. A stateful router is a "
    "bottleneck and a single point of failure. And the arithmetic is fragile — Kafka's default "
    "partitioner is a murmur2 hash of the key modulo the partition count, so **changing the "
    "partition count re-maps every key**, and messages for a key start landing in a different "
    "partition from the ones already queued for it. Per-key ordering silently breaks at that "
    "moment, and no error is emitted.",
    "Ordered parallelism bought with a partition count you can never comfortably change.",
    "They choose the routing key for its *cardinality distribution*, not for its semantic "
    "convenience. Routing by `tenant_id` reads well and gives you one partition doing 90 percent "
    "of the work the moment you land an enterprise customer, and no amount of adding partitions "
    "fixes it because a single key cannot be split. So they pick a key with high cardinality and "
    "flat distribution, or they compose one — `tenant_id` plus a bucket — and accept ordering per "
    "composite key instead. Second: they over-provision partitions at creation time, because "
    "Kafka's own documentation notes you cannot decrease the count and increasing it breaks "
    "key-to-partition affinity, which makes partition count effectively immutable in production.",
    "Kafka's default partitioner is the widely deployed instance of this pattern and the widely "
    "hit bug. The documented behaviour is that adding partitions to a topic does not move existing "
    "data and does change the destination of future messages for the same key, which is why the "
    "official guidance is to size partitions generously up front. Kafka 2.4 also changed the "
    "*keyless* path, replacing round-robin with a sticky partitioner that batches to one partition "
    "at a time — a throughput win that surprises anyone who assumed keyless meant evenly spread.",
    """flowchart TD
    K["Key acct-7 hashes to partition 1"] --> BEFORE["6 partitions<br/>all acct-7 messages in P1, ordered"]
    BEFORE --> ADD["Operator adds 6 partitions"]
    ADD --> AFTER["12 partitions<br/>acct-7 now hashes to P9"]
    AFTER --> BROKEN["Old acct-7 messages sit in P1<br/>new ones go to P9<br/>two consumers, no order between them"]
    style BROKEN fill:#2b1c17,stroke:#e0705a,color:#e4ecea"""),

"Content-Based Router": P(
    "A router whose decision depends on the contents of the message rather than on its channel or "
    "its key.",
    "AWS EventBridge rules, SNS filter policies, Apache Camel's `choice`, NServiceBus routing, "
    "enterprise service buses generally.",
    "The router inspects fields — an event type, an amount, a region — evaluates a rule set, and "
    "forwards to the matching destination or destinations.",
    "Different messages on one stream need different handling, and encoding that as a separate "
    "channel per case gives you a channel explosion and a producer that has to know the taxonomy.",
    "Producers publish one stream and stay ignorant of downstream topology. Routing changes are "
    "configuration, not code, and can be made without redeploying either end.",
    "The router must parse the payload, which means it is coupled to every producer's schema — a "
    "field rename in one producer breaks a component owned by neither team. Rules accumulate: the "
    "bus becomes a distributed if-statement with hundreds of branches and no owner, no tests and "
    "no way to answer 'what happens to this message'. Overlapping rules deliver twice, gaps in "
    "rules deliver nowhere, and the no-match case is usually invisible.",
    "Topological flexibility bought with a component that is coupled to everyone's schema and "
    "owned by nobody.",
    "They route on the **envelope, not the body**. Putting the discriminator in metadata — a "
    "header, a subject, a CloudEvents `type` and `source` — means the router never deserialises "
    "the payload, so producers can evolve their schemas freely and the router does not need "
    "redeploying when they do. CloudEvents exists largely for this reason: the spec deliberately "
    "keeps `type`, `source` and `subject` outside the data so intermediaries can route without "
    "understanding the domain. When content routing is genuinely unavoidable they cap it hard — "
    "route to a *few* coarse destinations and let the consumer do fine-grained dispatch, because "
    "the consumer is owned by someone who can be paged. And they always define the no-match "
    "destination, since a message that matches no rule is otherwise deleted in silence.",
    "AWS EventBridge implements full content-based routing over the event payload, and its own "
    "documentation quietly reveals the failure mode: events that match no rule are simply not "
    "delivered and are not retained anywhere, so a typo in a rule pattern is indistinguishable "
    "from no traffic. The CNCF CloudEvents specification takes the opposite design position, "
    "standardising a small set of envelope attributes precisely so brokers and routers can operate "
    "without opening the `data` field.",
    """flowchart LR
    M["Message"] --> R{"Router reads what"}
    R -->|"envelope type and source"| A["Router never parses body<br/>producers evolve freely"]
    R -->|"payload fields"| B["Router owns every producer schema<br/>redeployed on any field rename"]
    B --> C["No-match rule deletes silently"]
    style A fill:#1c6853,stroke:#4fc3a1,color:#e4ecea
    style C fill:#2b1c17,stroke:#e0705a,color:#e4ecea"""),

"Message Translator": P(
    "A component that converts a message from one format or model into another.",
    "Schema registries and their converters, Apache Camel type converters, API gateway request "
    "and response mapping, anti-corruption layers at a bounded-context boundary.",
    "Read the source representation, map fields onto the target representation, emit. In practice "
    "the mapping is a mixture of renames, type coercions, unit conversions and defaults.",
    "Systems that must talk were designed independently, and neither is going to change its model "
    "for the other. Without a translator the foreign model spreads through your code.",
    "Integration without either side changing. The foreign vocabulary is confined to one component "
    "you own. Version skew becomes something you can absorb rather than coordinate.",
    "Translation is lossy in one direction almost always, and the loss is invisible at the "
    "boundary. **The genuinely dangerous translator is the one that supplies a default for a field "
    "the source did not send**, because it manufactures a fact: 'unknown' becomes `false`, missing "
    "becomes `0`, and no downstream consumer can tell the difference between a value that was "
    "asserted and one that was invented. Chains of translators compound this, and each hop adds "
    "latency and a deserialise-reserialise cost that is easy to underestimate at volume.",
    "Interoperability bought with a silent loss of the distinction between absent and default.",
    "They preserve **presence** separately from value, and they treat any default injected during "
    "translation as a decision that needs an owner. This is not theoretical: proto3 originally "
    "removed field presence for scalars, so a `bool` that was never set and a `bool` explicitly "
    "set to `false` were byte-identical on the wire and indistinguishable in the API — Google had "
    "to reintroduce explicit presence with the `optional` keyword in protobuf 3.15 because the "
    "conflation caused real bugs at real scale. The second discipline is placement: translation "
    "belongs at the *edge* of a bounded context, owned by the side that benefits, never as a free-"
    "standing hop in the middle of a pipeline where it becomes a component with two owners and no "
    "tests. Third, they make the translator's compatibility rule explicit rather than emergent — "
    "Confluent Schema Registry's default `BACKWARD` mode permits adding optional fields and "
    "deleting fields but not adding required ones, and knowing which mode you are in tells you "
    "exactly which change will page you.",
    "Protocol Buffers is the clearest public case. proto3 dropped `has` methods for scalar fields "
    "in the name of simplicity, which made an unset field and a default-valued field the same "
    "thing; the change was reversed by adding explicit `optional` presence in release 3.15, and "
    "the design documents are in the protobuf repository. Confluent's Schema Registry encodes the "
    "same lesson operationally by refusing to register a schema that breaks the configured "
    "compatibility mode, turning a runtime translation failure into a publish-time rejection.",
    """flowchart TD
    S["Source message<br/>marketing_opt_in field absent"] --> T["Translator"]
    T --> D["Emits marketing_opt_in false"]
    D --> C["Consumer cannot distinguish<br/>never asked from said no"]
    T --> K["Better: emit presence explicitly<br/>or refuse to translate"]
    style C fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style K fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),

"Message Filter": P(
    "A component that forwards only the messages matching a criterion and discards the rest.",
    "SNS filter policies, Azure Service Bus subscription rules, MQTT topic wildcards, "
    "consumer-side predicates in Kafka Streams.",
    "A predicate is evaluated per message. Matching messages continue, non-matching messages are "
    "dropped — usually with no record that they existed.",
    "A consumer that cares about 2 percent of a stream should not pay to receive, deserialise and "
    "reject the other 98 percent, and should not have to be sized for the full volume.",
    "Bandwidth, CPU and cost drop in proportion to selectivity. The consumer's code contains no "
    "dispatch logic. Broker-side filtering means the messages never cross the network at all.",
    "**A filter drops in silence.** There is no dead letter, no lag, no error metric, and a "
    "consumer receiving nothing looks exactly like a consumer whose upstream has gone quiet. A "
    "filter that is wrong in the exclusive direction is therefore the hardest kind of bug to "
    "notice: it produces missing data with a green dashboard. Broker-side filters are also "
    "configuration that lives outside your repository and outside your tests, and their expression "
    "languages are limited enough that people push the hard cases back to the consumer, ending up "
    "with the logic split across two places.",
    "Cost reduction bought with a failure mode that produces no signal at all.",
    "They instrument the *discard*, not just the pass. A counter of filtered-out messages by "
    "reason turns an invisible failure into an anomaly you can alarm on, and the alarm that "
    "matters is the one on the ratio changing rather than on the absolute count. Second, they "
    "prefer a *not-routed* channel to a true discard wherever the broker allows it, so that a "
    "wrong predicate is recoverable rather than fatal — the messages are somewhere, and a fixed "
    "filter can replay them. Third, they know filtering interacts badly with ordering and with "
    "aggregation: a filter that removes some messages from a partitioned stream leaves gaps in any "
    "sequence-number scheme downstream, so a resequencer or a completeness check that was correct "
    "before the filter is quietly broken after it.",
    "Amazon SNS message filtering is the mainstream example. It began as attribute-only filtering "
    "in 2018 and gained payload-based filtering in 2022, and the AWS documentation is explicit "
    "that messages failing a subscription's filter policy are simply not delivered to that "
    "subscription and are not retained — there is no dead letter path for a filtered message, "
    "because from the broker's point of view nothing failed. Kafka takes the other position and "
    "offers no broker-side filtering at all, on the reasoning that the broker should not parse "
    "payloads.",
    """flowchart LR
    P["Producer<br/>10,000 msg/min"] --> F["Filter<br/>region equals EU"]
    F -->|"matched 200"| C["Consumer"]
    F -.->|"discarded 9,800"| X["Gone<br/>no DLQ, no lag, no metric"]
    X -.-> Q["A wrong predicate looks<br/>identical to a quiet upstream"]
    style X fill:#2b1c17,stroke:#e0705a,color:#e4ecea"""),

"Splitter": P(
    "Break one message containing multiple elements into a separate message per element.",
    "Order to order-lines fan-out, batch file ingestion, Apache Camel's `split`, S3 manifest "
    "processing, bulk API endpoints that enqueue per-item work.",
    "Parse the composite, emit one message per child, and stamp each child with a correlation id "
    "back to the parent plus its index and the total count.",
    "The elements can be processed independently and in parallel, and a single large message is a "
    "single unit of retry — one bad line forces the whole batch to be reprocessed.",
    "Parallelism proportional to element count. Per-element retry, so one poison element does not "
    "block the other 999. Each child is small enough to fit comfortably inside broker size limits.",
    "**The split destroys the parent's atomicity and nothing restores it.** If seven of ten "
    "children succeed and three fail, the business has a half-processed order and there is no "
    "transaction to roll back. Ordering between children is lost immediately. And the parent's "
    "completion becomes unknowable without extra machinery, because a consumer that has seen seven "
    "children cannot distinguish 'three still in flight' from 'three lost'.",
    "Per-element parallelism and retry bought with the loss of the parent as a unit of correctness.",
    "They stamp the **total count** onto every child at split time, not just a correlation id. "
    "Without it no downstream component can ever decide that a group is complete, and every "
    "aggregator degenerates into a timeout — which is exactly the design Hohpe prescribes in the "
    "original catalogue and exactly the field people leave out because it seems redundant when the "
    "parent is right there. Second, they make the children idempotent and keyed on parent id plus "
    "index, so a redelivered child is a no-op and partial reprocessing of a batch is safe; without "
    "that, retrying a failed split means either duplicating the seven that worked or writing "
    "bespoke skip logic. Third, they think about the fan-out ratio before deploying: a splitter is "
    "an amplifier, and one 50,000-line file becomes 50,000 messages that will arrive at a "
    "downstream service sized for the un-split rate.",
    "Apache Camel's Splitter is the most directly inspectable implementation — it splits an "
    "exchange and requires an explicit `AggregationStrategy` if you want to rejoin, which forces "
    "the designer to confront the completeness question rather than discover it later. The "
    "original Hohpe and Woolf catalogue specifies that a splitter should attach a correlation "
    "identifier, a sequence number and the total size to each child precisely so that a "
    "Resequencer or Aggregator downstream has something to work with. Most hand-rolled splitters "
    "carry the correlation id and omit the other two.",
    """flowchart TD
    O["Order with 10 lines"] --> S["Splitter"]
    S --> C1["line 1 of 10<br/>corr abc"]
    S --> C2["line 2 of 10<br/>corr abc"]
    S --> CN["line 10 of 10<br/>corr abc"]
    C1 --> OK["7 succeed"]
    CN --> BAD["3 fail"]
    BAD --> H["Half-processed order<br/>no transaction to roll back"]
    style H fill:#2b1c17,stroke:#e0705a,color:#e4ecea"""),

"Aggregator": P(
    "Collect related messages and emit a single combined message once the group is considered "
    "complete.",
    "Windowed aggregation in Flink and Kafka Streams, Spark structured streaming, order-line "
    "rejoining after a splitter, batch-and-flush metric pipelines.",
    "Buffer messages keyed by a correlation id or a time window. A completeness condition — a "
    "count, a watermark, a timer, or an explicit end marker — decides when to emit.",
    "Downstream wants a total, a decision or a document, not a stream of fragments, and computing "
    "that per message means either N writes or N reads.",
    "Turns a high-volume stream into a low-volume one. Makes cross-message logic — totals, joins, "
    "sessionisation — possible at all. Amortises downstream cost.",
    "The aggregator is stateful, which makes it the hardest component in the pipeline to scale, "
    "restart or rebalance. Its buffer is unbounded unless you bound it, and bounding it means "
    "choosing what to drop. **Completeness is never actually knowable** — you cannot distinguish a "
    "message that will arrive in one second from one that will never arrive, so every aggregator "
    "is really an aggregator plus a guess. And a late message after emission forces a choice "
    "between discarding real data and issuing a correction that every downstream consumer must "
    "know how to apply.",
    "A usable summary bought with state, and with a completeness decision that is always a guess.",
    "They stop trying to answer 'is it complete' and instead answer the three questions Google's "
    "Dataflow paper separates: *what* is being computed, *when* results are emitted, and *how* "
    "later refinements relate to earlier ones. That third question is the one almost everyone "
    "skips, and it is the one that decides whether a late-arriving record produces a corrected "
    "total, a discarded record or a silently wrong number for the rest of time. Concretely: they "
    "emit early and often with a trigger, mark the emission as speculative or final, and carry an "
    "explicit accumulation mode so a downstream consumer knows whether to add the update to the "
    "previous one or replace it. Second, they route late data to a side output rather than "
    "dropping it, because 'how much data are we losing to lateness' should be a graph, not an "
    "assumption.",
    "Akidau et al., *The Dataflow Model* (VLDB 2015), is the paper that reframed this from a "
    "buffering problem into a three-way trade between completeness, latency and cost, based on "
    "Google's experience running MillWheel and FlumeJava. Apache Flink implements the same model "
    "directly — watermarks estimate event-time progress, allowed lateness extends the window past "
    "the watermark, and anything later still goes to a side output rather than vanishing. The "
    "practical lesson from both is that the watermark is a heuristic, and any system that treats "
    "it as a guarantee will lose data at exactly the moment its input gets slow.",
    """flowchart TD
    IN["Events, some late"] --> B["Buffer keyed by window"]
    B --> W{"Watermark passed"}
    W -->|"yes"| E1["Emit result, marked final"]
    W -->|"still open"| E0["Emit speculative result"]
    E1 --> LATE["Event arrives after emission"]
    LATE --> D{"How do refinements relate"}
    D -->|"discard"| L1["Silently wrong total"]
    D -->|"accumulate or retract"| L2["Correction downstream must apply"]
    style L1 fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style L2 fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),
"Resequencer": P(
    "Restore a defined order to messages that arrived out of order.",
    "TCP's receive buffer, protocol gateways in front of order-sensitive legacy systems, market "
    "data feed handlers, Camel's `resequence`.",
    "Buffer incoming messages keyed by a sequence number, emit them in order as the gaps fill, and "
    "apply a timeout so that a permanently missing message does not stall the stream forever.",
    "Parallel delivery paths reorder messages, and some consumers genuinely cannot tolerate it — "
    "applying a cancellation before the creation it cancels is not a recoverable state.",
    "The consumer stays simple and order-blind. One component absorbs a problem that would "
    "otherwise be replicated in every downstream handler.",
    "It is a stateful, memory-bound buffer sitting on the critical path, and it converts a "
    "throughput problem into a latency problem: **one missing message blocks every message behind "
    "it**, which is head-of-line blocking by construction. The timeout is the entire design and "
    "there is no good value for it — too short and you emit out of order anyway, too long and one "
    "lost message stalls the pipeline for that duration. A resequencer also cannot be scaled "
    "horizontally without partitioning by the same key the sequence is defined over, at which "
    "point you have re-derived partitioned ordering and could have skipped the component.",
    "Guaranteed order bought with head-of-line blocking and a timeout that is always wrong.",
    "They ask whether *global* order is actually required, and it almost never is — what is "
    "required is order per entity, which a partitioned channel gives you for free with no buffer, "
    "no timeout and no head-of-line blocking. The best resequencer is the one deleted by choosing "
    "a better partition key. Where order genuinely cannot be partitioned away, they make the "
    "consumer order-tolerant instead: a message carrying a version or a timestamp lets the "
    "consumer apply last-writer-wins or reject stale updates, which is strictly cheaper than "
    "buffering because it needs no state beyond the current version. The industry has already run "
    "this experiment at scale — HTTP/2 multiplexed streams over a single TCP connection and "
    "inherited TCP's in-order delivery, so one lost packet stalled every concurrent stream, and "
    "the fix in HTTP/3 was not a better resequencer but QUIC's per-stream ordering, which removed "
    "the shared sequence entirely.",
    "TCP is the resequencer everyone already depends on, and HTTP/3 is the public record of its "
    "cost. HTTP/2 solved application-layer head-of-line blocking by multiplexing streams, then hit "
    "transport-layer head-of-line blocking because TCP delivers a single ordered byte stream and "
    "one lost segment holds back all of it. QUIC, specified in RFC 9000 and carrying HTTP/3, gives "
    "each stream its own sequence space so a loss on one stream does not block the others — the "
    "same conclusion as partitioning a message channel by key.",
    """sequenceDiagram
    participant U as Upstream
    participant R as Resequencer
    participant C as Consumer
    U->>R: msg 1
    R->>C: msg 1
    U->>R: msg 3
    U->>R: msg 4
    Note over R: msg 2 is missing, 3 and 4 held
    U->>R: msg 5
    Note over R: buffer growing, consumer idle
    Note over R,C: timeout fires, emit 3 4 5 out of order anyway"""),

"Scatter-Gather": P(
    "Broadcast a request to several recipients and combine their replies into one response.",
    "Elasticsearch querying every shard, federated search, price comparison, Google web search "
    "across index shards, GraphQL resolvers fanning out to services.",
    "Send the request to N participants in parallel, collect replies against a correlation id, and "
    "combine when all have answered or a deadline expires.",
    "The answer lives in pieces across several systems and no single one can produce it. Querying "
    "them sequentially costs the sum of their latencies.",
    "Parallel latency instead of serial. Participants stay independent and unaware of each other. "
    "Adding a participant does not change the caller's code.",
    "**The response time is the maximum of the branches, not the mean**, so the tail dominates "
    "completely: a fan-out of 100 turns your p99 branch into your typical request. Load is "
    "multiplied — one inbound request becomes N outbound. Partial failure is the normal case, so "
    "every gatherer needs a policy for it, and 'wait for all' means your availability is the "
    "product of theirs, which for 50 participants at 99.9 percent each is about 95 percent.",
    "Parallel breadth bought with a latency and availability profile set by your worst participant.",
    "They compute the arithmetic before designing the fan-out. Dean and Barroso's number in *The "
    "Tail at Scale* is the one to memorise: if a single server exceeds one second on 1 request in "
    "100, a request that touches 100 servers exceeds one second **63 percent of the time** — the "
    "rare case becomes the common case purely through fan-out. That figure kills the naive design "
    "and forces the real one: return partial results with an explicit completeness signal rather "
    "than blocking on the slowest branch, and treat a missing branch as a degraded answer rather "
    "than an error. Elasticsearch models this properly, returning `timed_out` and a per-shard "
    "success and failure count in every response, so a caller can decide whether a result computed "
    "from 18 of 20 shards is acceptable. Second, they cap the fan-out itself — hierarchical "
    "gathering, or a routing layer that narrows the candidate set — because reducing N is the only "
    "intervention that improves both latency and load.",
    "Dean and Barroso, *The Tail at Scale* (CACM, February 2013), is the source and its central "
    "example is exactly this pattern in Google's search serving path. Elasticsearch's "
    "query-then-fetch execution is the most inspectable open implementation: the coordinating node "
    "scatters to every shard, gathers, merges and returns partial-result metadata rather than "
    "failing the whole query when a shard is slow or down.",
    """flowchart TD
    Q["One request"] --> S["Scatter to 100 shards"]
    S --> B1["99 shards reply in 20ms"]
    S --> B2["1 shard replies in 1,100ms"]
    B1 --> G["Gatherer"]
    B2 --> G
    G --> R["Response takes 1,100ms<br/>63 percent of requests hit this<br/>when each shard is slow 1 time in 100"]
    style R fill:#2b1c17,stroke:#e0705a,color:#e4ecea"""),

"Dead Letter Channel": P(
    "A separate channel that receives messages the system could not process, so the main channel "
    "keeps moving.",
    "SQS redrive policies, RabbitMQ dead letter exchanges, Kafka Connect error topics, Azure "
    "Service Bus dead letter queues.",
    "After a configured number of failed delivery or processing attempts, the broker moves the "
    "message to another queue instead of redelivering it. It stays there until a human or a job "
    "deals with it.",
    "A single unprocessable message on a strictly ordered or single-consumer channel will be "
    "retried forever, blocking everything behind it. One malformed payload should not stop the "
    "business.",
    "Poison messages are isolated instead of blocking. The main channel's throughput is unaffected "
    "by a permanently failing message. The failed messages are preserved for diagnosis and replay "
    "rather than dropped.",
    "**A DLQ is a queue with no consumer**, and the overwhelmingly common outcome is that nobody "
    "looks at it until an incident makes them. It inherits the source queue's retention, so on SQS "
    "the messages silently delete after 14 days — the DLQ that was meant to prevent data loss "
    "becomes a slower way to lose data. A bare redrive replays the same message against the same "
    "unfixed bug and it comes straight back. And the DLQ conflates two completely different "
    "populations: messages that failed because they are malformed and will always fail, and good "
    "messages that failed because a downstream was briefly down.",
    "Throughput protection bought with a backlog that nobody owns by default.",
    "They page on DLQ depth rather than graphing it — a message in a dead letter queue is a lost "
    "business event, and if it is not worth waking someone for, it was not worth queueing. Second, "
    "and this is the discipline that separates a working DLQ from a decorative one, they capture "
    "**the failure reason alongside the message**, in a header or a companion record, because "
    "redriving without knowing why the message failed is a loop rather than a fix. Third, they "
    "separate transient from terminal failure *before* the DLQ: retrying a schema-violating "
    "payload five times is pure cost, while dead-lettering a message that failed because a "
    "dependency was down for 30 seconds throws away a perfectly good event. The rule of thumb is "
    "that a 4xx-shaped failure should dead letter immediately and a 5xx-shaped one should retry "
    "with backoff, and mixing them is why DLQs fill with messages that would have worked fine.",
    "Amazon SQS makes both halves of this visible. Its redrive policy moves a message after "
    "`maxReceiveCount` attempts, and AWS's own guidance is to put a CloudWatch alarm on the DLQ's "
    "`ApproximateNumberOfMessagesVisible` — advice that exists because the default state of a DLQ "
    "is unmonitored. The 14-day maximum message retention applies to the dead letter queue exactly "
    "as it does to the source, and the retention clock is the *original* enqueue time, so a "
    "message that spent 13 days failing has one day left in the DLQ, not fourteen.",
    """flowchart TD
    Q["Main queue"] --> W["Worker"]
    W -->|"fails 5 times"| DLQ["Dead letter queue"]
    DLQ --> A{"Is anyone alarmed on depth"}
    A -->|"no"| X["Retention expires<br/>events lost, slower"]
    A -->|"yes, with failure reason captured"| F["Fix the bug, then redrive"]
    DLQ -.->|"bare redrive"| Q
    style X fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style F fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),

"Idempotent Receiver": P(
    "A receiver that produces the same outcome whether it processes a message once or many times.",
    "Stripe's `Idempotency-Key` header, payment and ledger APIs generally, Kafka consumers writing "
    "with a deduplication table, webhook receivers.",
    "The sender attaches a unique key. The receiver records the key and the outcome atomically "
    "with the effect, and on a repeat key returns the stored outcome instead of re-executing.",
    "Every at-least-once channel will redeliver, and so will every retrying client. Without "
    "idempotency a network timeout on a payment request is unresolvable: the client cannot tell "
    "whether the charge happened, and both retrying and not retrying are wrong.",
    "Retries become safe, which is what makes at-least-once delivery usable at all. Clients can "
    "retry aggressively. Duplicate deliveries stop being a correctness problem and become a cost "
    "problem.",
    "The dedupe store is a new stateful dependency on the write path, and its retention window "
    "defines exactly how long you are protected — a retry after expiry re-executes. Deciding key "
    "scope is genuinely hard: too broad and legitimate distinct requests are rejected, too narrow "
    "and duplicates slip through. And a receiver that is idempotent in its own database but calls "
    "a non-idempotent third party has not achieved idempotency, only relocated the problem.",
    "Safe retries bought with a stateful dedupe layer and a finite protection window.",
    "**Store the result with the key, not just the key.** A receiver that records 'seen' and "
    "returns a bare 200 leaves the retrying client with no way to learn the outcome — it knows the "
    "charge did not happen twice, and it still does not know the charge id. Stripe stores the "
    "status code and the response body against the key and replays that exact response, which is "
    "what makes the retry genuinely transparent. Second: **the key record must be written in the "
    "same transaction as the effect.** Writing the row and then recording the key is the dual-"
    "write problem re-created inside the mechanism meant to defend against it, and the gap is "
    "reachable. Third, they bind the key to the request payload: Stripe returns an error if the "
    "same idempotency key arrives with different parameters, which catches the very common client "
    "bug of reusing one key across two different charges — a receiver that ignores the payload "
    "would silently return the first charge's response for the second charge.",
    "Stripe's implementation is the reference and is documented publicly in their API reference "
    "and in Brandur Leach's 2017 engineering post *Designing robust and predictable APIs with "
    "idempotency*. Keys are supplied by the client, the response is saved and replayed for "
    "subsequent requests with the same key, results are retained for 24 hours, and reusing a key "
    "with a different request body returns an error rather than the cached response. The 24-hour "
    "window is the part worth internalising: idempotency is not permanent, and a client that "
    "retries a week later will charge the customer again.",
    """sequenceDiagram
    participant C as Client
    participant S as Service
    participant D as Store
    C->>S: POST charge, key k1
    S->>D: begin, insert charge plus key k1 plus response, commit
    S--)C: 200 charge ch_9, response lost in transit
    C->>S: POST charge, key k1, retry
    S->>D: key k1 already present
    S--)C: 200 charge ch_9, the stored response replayed
    Note over S,D: storing only the key would return 200 with no charge id"""),

"Competing Consumers": P(
    "Several consumers read from one channel, each message going to whichever is free.",
    "Kafka consumer groups, SQS with an autoscaling worker fleet, Celery and Sidekiq workers, "
    "RabbitMQ work queues.",
    "The broker distributes messages across the pool — by handing each message to one consumer, or "
    "by assigning whole partitions to consumers and rebalancing when membership changes.",
    "Throughput needs to scale with load, and load is not constant. One consumer is a fixed "
    "ceiling and a single point of failure.",
    "Throughput scales by adding processes, with no code change and no coordination. A crashed "
    "consumer's work is reassigned automatically. The pool can autoscale on queue depth.",
    "**Ordering is lost the moment you start the second consumer** — two workers processing "
    "messages for the same entity in parallel will finish in an order unrelated to the order they "
    "were sent. Rebalancing is disruptive: Kafka's classic protocol stops the whole group while "
    "partitions are reassigned, so a rolling deploy of ten consumers triggers ten stop-the-world "
    "pauses. Consumers beyond the partition count sit completely idle, so scaling out past that "
    "number does nothing at all while still costing money. And duplicate processing during "
    "rebalance is normal, because a consumer can be processing a message it no longer owns.",
    "Elastic throughput bought with the total loss of ordering across the pool.",
    "They accept that global order is gone and restore only the order that matters, by "
    "partitioning on the key whose sequence is meaningful — then immediately confront the two "
    "consequences everyone discovers late. First, per-key ordering caps parallelism at the number "
    "of partitions, not the number of consumers, and Kafka's own model makes this stark: a topic "
    "with 6 partitions and 10 consumers in a group leaves 4 consumers idle, permanently. Second, "
    "any key hot enough to matter becomes a hot partition, and the pattern offers no remedy — you "
    "cannot split one key across two consumers and keep its order. The other thing they configure "
    "deliberately is the rebalance protocol: cooperative incremental rebalancing, added in Kafka "
    "2.4 under KIP-429, revokes only the partitions that actually move rather than everything, "
    "which turns a rolling restart from a series of full-group outages into a series of local "
    "ones. Most teams are still on the default they inherited.",
    "Kafka consumer groups are the canonical implementation and the documented behaviour is the "
    "lesson: the partition is simultaneously the unit of parallelism and the unit of ordering, so "
    "the two are the same knob and cannot be tuned independently. The idle-consumer property "
    "follows directly and is stated in Kafka's own documentation. Sidekiq and Celery sit at the "
    "other extreme — no partitioning, so no ordering at all, which is honest and is why both "
    "recommend making jobs idempotent and order-independent rather than offering an ordering mode.",
    """flowchart TD
    T["Topic, 4 partitions"] --> P1["P0"] --> C1["Consumer 1"]
    T --> P2["P1"] --> C2["Consumer 2"]
    T --> P3["P2"] --> C3["Consumer 3"]
    T --> P4["P3"] --> C4["Consumer 4"]
    T -.-> C5["Consumer 5, idle"]
    T -.-> C6["Consumer 6, idle"]
    style C5 fill:#2a2317,stroke:#d9a441,color:#e4ecea
    style C6 fill:#2a2317,stroke:#d9a441,color:#e4ecea"""),

"Claim Check": P(
    "Store the large payload elsewhere and send only a reference through the channel.",
    "The Amazon SQS Extended Client Library writing to S3, video and document pipelines, Azure's "
    "documented Claim-Check pattern, any Kafka topic carrying media.",
    "The producer writes the body to object storage, puts the location and enough metadata to "
    "route on into the message, and the consumer fetches the body only if it needs it.",
    "Brokers have hard message size limits — SQS caps a message at 256 KB, Kafka's default "
    "`max.message.bytes` is about 1 MB — and even below the limit, large messages destroy broker "
    "throughput because the broker is optimised for many small records, not few large ones.",
    "Messages stay small, so broker throughput, replication and retention costs stay predictable. "
    "Consumers that only need the metadata never pay to transfer the body. Object storage is "
    "cheaper per byte than a broker's replicated log by a wide margin.",
    "The message and the payload now have **independent lifecycles**, and getting that wrong is "
    "the defining failure: a 7-day S3 lifecycle rule under a 14-day queue retention produces valid "
    "messages pointing at deleted objects, which surfaces as a burst of 404s during a replay and "
    "not before. You have added a second system to the critical path, so the message's "
    "availability is now the product of the broker's and the store's. Deletion becomes a genuine "
    "distributed problem — whoever deletes the blob breaks replay for everyone else. And an "
    "at-least-once channel plus a mutable object store means a redelivered message can fetch "
    "*different* content than the first delivery did.",
    "Broker throughput bought with a second storage system and a lifecycle you must keep in sync.",
    "They put enough in the message to **route, filter and diagnose without dereferencing** — "
    "type, size, checksum, tenant, timestamp — so the consumers that only need to decide 'is this "
    "mine' never touch the store, and the claim check is legible in a log. Second, they make the "
    "reference immutable: a content-addressed key, or a versioned object id, so the same claim "
    "check always resolves to the same bytes and a redelivery is genuinely a duplicate rather than "
    "a fresh read. Third, they set the blob's retention to strictly exceed the queue's retention "
    "plus the DLQ's retention plus any replay window they intend to support, and they write that "
    "arithmetic down somewhere, because it is the one constraint no monitoring will catch until it "
    "is violated. Fourth, deletion is the producer's job or a lifecycle rule's job, never the "
    "consumer's — a consumer that deletes on success is a consumer that has silently made the "
    "system single-subscriber.",
    "The Amazon SQS Extended Client Library for Java is the pattern shipped as a library: it "
    "transparently writes payloads over the size threshold to S3 and puts a pointer in the "
    "message, and the consumer-side library resolves it. Microsoft documents the same pattern in "
    "the Azure Architecture Center under the name Claim-Check. The size limits that force it are "
    "public and worth knowing by heart — 256 KB for SQS, roughly 1 MB for a default Kafka record "
    "— because they are the numbers that decide whether a design needs this at all.",
    """flowchart LR
    P["Producer"] -->|"1. put object"| S3["Object store<br/>lifecycle 7 days"]
    P -->|"2. small message with key<br/>plus type, size, checksum"| Q["Queue<br/>retention 14 days"]
    Q --> C["Consumer"]
    C -->|"3. get object"| S3
    S3 -.->|"day 8 to 14"| E["404 on replay<br/>message valid, payload gone"]
    style E fill:#2b1c17,stroke:#e0705a,color:#e4ecea"""),

"Guaranteed Delivery": P(
    "The channel persists the message so it survives a crash of the broker, the sender or the "
    "receiver.",
    "Kafka's replicated log, RabbitMQ persistent messages with publisher confirms, SQS's "
    "redundant storage, any write-ahead log.",
    "The broker writes the message to durable storage — usually replicated to several machines — "
    "and only acknowledges the producer once the configured durability condition is met. On "
    "restart the log is replayed.",
    "An in-memory queue loses everything on a process restart, and 'we lost 40 seconds of orders "
    "during a deploy' is not an acceptable sentence.",
    "Messages survive broker restart, host failure and, with cross-zone replication, the loss of a "
    "data centre. The producer gets a definite answer about whether its message was accepted.",
    "Durability costs latency on every publish, and the cost is a round trip to the slowest "
    "replica in the acknowledgement set. Disk and replication multiply storage cost by the "
    "replication factor. Worst of all, **'guaranteed' is only ever relative to a failure model "
    "that is written down somewhere, and the defaults almost never match the model people "
    "assume** — the guarantee sounds absolute and is not.",
    "Durability bought with publish latency, storage multiplied by the replication factor, and a "
    "guarantee that is narrower than its name.",
    "They read the configuration as a *pair*, because each half is meaningless alone. Kafka's "
    "`acks=all` is widely believed to mean 'all replicas', and it means 'all replicas currently in "
    "the in-sync set' — so `acks=all` with `min.insync.replicas=1` acknowledges after a single "
    "copy exists and reads exactly like a durability guarantee while providing none. The "
    "combination that means what people think is replication factor 3, `min.insync.replicas=2`, "
    "`acks=all`, and the trade is that the topic stops accepting writes when two brokers are down "
    "— which is the correct behaviour and surprises people during their first incident. The second "
    "thing they know is the shape of the guarantee: Kafka deliberately does not fsync each message "
    "to disk, relying on replication across machines instead of on the durability of one disk, so "
    "a correlated power loss across a rack is *outside the model*. That is a defensible design and "
    "it is the design, and if your risk register includes correlated power loss you need "
    "cross-rack or cross-zone placement, not a stronger ack setting.",
    "Apache Kafka's own design documentation states the position plainly: durability comes from "
    "replicating to multiple brokers rather than from flushing every write to disk, because a "
    "correctly configured replicated log survives machine failure while fsync-per-message would "
    "cost more than it returns. The `min.insync.replicas` interaction with `acks=all` is likewise "
    "documented and is the single most common Kafka misconfiguration in production. RabbitMQ "
    "encodes the same lesson differently: a persistent message published without publisher "
    "confirms can be lost, because persistence describes what the broker does after it accepts and "
    "confirms describe when it has.",
    """flowchart TD
    A["acks=all"] --> B{"min.insync.replicas"}
    B -->|"1"| C["Acknowledged after one copy<br/>reads like a guarantee, is not"]
    B -->|"2 with RF 3"| D["Two copies before ack<br/>topic rejects writes if 2 brokers down"]
    D --> E["Model excludes correlated power loss<br/>Kafka replicates, it does not fsync per message"]
    style C fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style D fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),

"Transactional Outbox": P(
    "Write the message to a table in the same database transaction as the state change, and "
    "publish it from there afterwards.",
    "Debezium's Outbox Event Router, most mature event-driven microservice codebases, ledger and "
    "order services that must never publish a fact they did not commit.",
    "The business write and an insert into an `outbox` table happen in one local ACID "
    "transaction. A separate relay — polling the table or tailing the database's replication log "
    "— reads committed outbox rows and publishes them to the broker, marking or deleting them "
    "after.",
    "Writing to the database and publishing to a broker are two systems and one operation. There "
    "is no transaction spanning both, so a crash between them leaves the state changed with no "
    "event, or an event announcing a change that was rolled back.",
    "The event is published if and only if the state change committed. No distributed transaction, "
    "no two-phase commit, no coordinator. It works with any database that has local transactions, "
    "which is all of them.",
    "You now operate a relay, and it is a piece of infrastructure with its own lag, its own "
    "failure modes and its own monitoring. The outbox table is high-churn — insert, read, delete — "
    "which on PostgreSQL means dead tuples and autovacuum pressure on one of your hottest tables, "
    "and on any engine means index bloat if it is never pruned. Publishing is now asynchronous, so "
    "consumers see the event after the commit rather than at it, and the lag is visible to users "
    "in any read-your-own-writes flow that crosses services.",
    "Atomic publish bought with a relay to operate and a permanently asynchronous event.",
    "**The mistake this pattern exists to prevent is believing the dual write can be fixed by "
    "ordering it carefully.** Commit the row then publish, and the process can die in between — "
    "state changed, no event. Publish then commit, and the transaction can roll back — event sent, "
    "nothing happened. Wrap the publish in a `try` and roll back on failure, and the failure case "
    "you cannot handle is the publish that succeeded and returned a timeout. There is no ordering "
    "of two non-transactional systems that makes them one, and every hour spent looking for one is "
    "wasted; the outbox works precisely because the second write is not a second system, it is "
    "another row in the *same* transaction. The design question that actually remains is the "
    "relay. Polling is trivially simple, adds latency equal to the poll interval and puts constant "
    "read load on the database. Log tailing has near-zero latency and no query load and couples "
    "you to the database's replication log as an interface — and on PostgreSQL it means a "
    "replication slot, which retains WAL until it is consumed, so a stalled relay fills the disk "
    "and takes the primary down with it.",
    "Debezium ships this as a first-class feature: the Outbox Event Router single-message transform "
    "reads outbox rows from the database's change stream and republishes them onto topics derived "
    "from the row's aggregate type, so the relay is configuration rather than code. Gunnar "
    "Morling's 2019 post *Reliable Microservices Data Exchange With the Outbox Pattern* on the "
    "Debezium blog is the write-up that made the pattern mainstream and is still the clearest "
    "statement of why the dual write has no safe ordering.",
    """flowchart TD
    T{"Two writes, one operation"} -->|"commit row, then publish"| A["Crash in the gap<br/>state changed, no event"]
    T -->|"publish, then commit"| B["Rollback after publish<br/>event for a fact that never happened"]
    T -->|"one transaction<br/>row plus outbox row"| C["Relay publishes committed rows only"]
    C --> D["At-least-once to the broker<br/>receiver must still be idempotent"]
    style A fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style C fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),
}

DISTRIBUTED = {
"Saga": P(
    "A long-lived business transaction expressed as a sequence of local transactions, each with a "
    "compensating action for undoing its effect.",
    "Order fulfilment across payment, inventory and shipping. Travel booking. Temporal and AWS "
    "Step Functions workflows. Uber's Cadence.",
    "Each step commits locally and publishes its outcome. On failure, the already-committed steps "
    "are compensated in reverse order — either by an orchestrator that owns the sequence, or by "
    "choreography in which each service reacts to the previous one's events.",
    "A business operation spans services that do not share a database, and the alternative — a "
    "distributed transaction holding locks across all of them for the duration — blocks, does not "
    "scale, and is unavailable exactly when a participant is.",
    "No distributed locks and no coordinator holding resources. Each service keeps full autonomy "
    "over its own data and its own availability. The operation survives participants being "
    "temporarily down, because each step retries independently.",
    "**There is no isolation.** Another transaction can observe the half-completed state — the "
    "money taken but the seat not yet reserved — and the countermeasures for that are all "
    "application-level work: semantic locks, commutative updates, pessimistic views, re-reading "
    "values, version files. Compensation can itself fail, and then you need a human and a runbook. "
    "Debugging a partially compensated saga across seven services means correlating seven logs. "
    "And the number of failure paths is roughly the square of the number of steps, so a six-step "
    "saga has more compensation code than business code.",
    "Cross-service atomicity bought with the complete loss of isolation and a second, larger body "
    "of compensation logic.",
    "**Compensation is not rollback, and treating it as rollback is the error the whole pattern "
    "punishes.** A rollback erases; a compensating action is a *new business fact*. You do not "
    "un-charge a card, you issue a refund — the customer saw the charge, it appears on the "
    "statement, the money moved twice, the accounting shows both legs, and support will get a "
    "call. Some actions have no compensation at all: an email has been read, a physical item has "
    "shipped, a third party has been told something true. So the design decision that matters, and "
    "the one nearly every tutorial omits, is **ordering the steps around a pivot**. Classify every "
    "step as compensatable, pivot, or retriable: everything before the pivot must be undoable, the "
    "pivot is the point of no return, and everything after it must be guaranteed to eventually "
    "succeed under retry. Put the irreversible step as late as possible and the saga becomes "
    "tractable; put it in the middle and you have written a system with a state you cannot leave. "
    "The corollary they also apply: compensations must be idempotent and commutative under retry, "
    "because the compensation will itself be redelivered.",
    "Garcia-Molina and Salem introduced sagas in *Sagas* (SIGMOD 1987), for long-lived database "
    "transactions whose lock duration was unacceptable — the distributed-systems use came later "
    "but the compensation semantics are the paper's. The compensatable, pivot and retriable "
    "classification is Chris Richardson's, set out in *Microservices Patterns*, and it is the part "
    "that turns the pattern from a slogan into a design method. Uber built Cadence, open-sourced "
    "in 2017 and now continued as Temporal, specifically because hand-rolled sagas with ad-hoc "
    "compensation state proved unmaintainable at their step count.",
    """flowchart LR
    S1["Reserve seat<br/>compensatable"] --> S2["Authorise card<br/>compensatable"]
    S2 --> P["Charge card<br/>PIVOT, no way back"]
    P --> S4["Issue ticket<br/>retriable until it succeeds"]
    S4 --> S5["Send confirmation<br/>retriable, uncompensatable"]
    S2 -.->|"failure before pivot"| C["Release seat, void auth"]
    style P fill:#2a2317,stroke:#d9a441,color:#e4ecea
    style C fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),

"CQRS": P(
    "Separate the model used to change state from the model used to read it.",
    "Order systems with a normalised write side and a denormalised read view, e-commerce catalogue "
    "search, any service backing a dashboard whose query shape has nothing to do with its write "
    "shape.",
    "Commands go through a model built for invariants — normalised, validated, transactional. "
    "Queries hit one or more read models shaped for the screens that use them, kept up to date by "
    "events, a projection job, or a materialised view.",
    "The shape that enforces business rules on write and the shape that answers questions on read "
    "are genuinely different. Serving both from one model means either joining eleven tables on "
    "every page load or denormalising until writes cannot be validated.",
    "Each side scales, is optimised and is cached independently. Read models can be rebuilt, "
    "reshaped and added without touching the write side. Complex queries stop distorting the "
    "domain model.",
    "**Read-your-own-writes breaks**, and it breaks in the demo: the user submits a form, is "
    "redirected to the list, and their change is not there. Every feature now touches two models "
    "and possibly two teams. The projection is a piece of infrastructure with lag to monitor and a "
    "rebuild time that grows with your history — and 'we will just rebuild the projection' stops "
    "being a two-minute operation surprisingly early. Debugging means asking whether the write "
    "model is wrong or the projection is behind, which are indistinguishable from the UI.",
    "Independently optimised reads bought with eventual consistency the user can see.",
    "**It is two models, not two databases**, and conflating those is why the pattern is so often "
    "over-built. A read model can be a view, a materialised view, a denormalised table in the same "
    "schema, or just a different set of classes over the same tables — you get most of the benefit "
    "with none of the eventual consistency. The separate datastore is an optimisation you add when "
    "you have measured that you need it, not the definition of the pattern. The second thing they "
    "know is that **it is usually adopted far too early**, at the start of a project, on the "
    "reasoning that reads might need to scale later — which buys a permanent, user-visible "
    "consistency bug today in exchange for a problem you do not have. Udi Dahan, who helped "
    "popularise the pattern, published *When to avoid CQRS* in 2011 saying plainly that most "
    "people using it should not have. So they apply it per aggregate, in the one bounded context "
    "where the read and write shapes have genuinely diverged, and they leave the other forty "
    "entities alone. Where they do apply it, they solve read-your-writes explicitly rather than "
    "hoping — return the new version token from the command and have the read side wait for it, or "
    "read that one entity from the write model.",
    "Greg Young coined the term, separating it from Bertrand Meyer's older command-query "
    "separation, and has repeatedly said it is a pattern for a bounded context rather than a "
    "top-level architecture. Udi Dahan's 2011 post *When to avoid CQRS* is the more useful "
    "citation because it is a warning from an advocate: his position is that CQRS should be "
    "applied only where collaborative, high-contention domains make the two models genuinely "
    "different, and that applying it everywhere is a widespread and expensive mistake.",
    """sequenceDiagram
    participant U as User
    participant W as WriteModel
    participant PJ as Projection
    participant R as ReadModel
    U->>W: update address
    W--)PJ: event
    U->>R: GET profile, immediately
    R--)U: the old address
    Note over U,R: read-your-own-writes broken, and it shows in the demo
    PJ->>R: apply, 400ms later"""),

"Event Sourcing": P(
    "Persist state as an append-only sequence of events, and derive current state by folding over "
    "them.",
    "Ledgers and accounting systems, git, source control generally, Kafka-backed domain services, "
    "EventStoreDB, most trading and settlement systems.",
    "Every change appends an immutable event to a per-entity stream. Current state is a left fold "
    "over the stream, cached as a snapshot beyond some length. Read models are projections built "
    "by replaying.",
    "Some domains need the *why* and not just the *what*: an auditor asks how the balance reached "
    "this number, and a row that has been updated in place cannot answer. Storing only current "
    "state discards every fact that produced it.",
    "A complete, immutable audit log that is the source of truth rather than a side effect. Any "
    "past state can be reconstructed. New projections can be built retroactively over history you "
    "did not know you would need. Temporal queries — what did we believe on the 4th — become "
    "trivial.",
    "You cannot query it. Every question needs a projection, so you always own a second system and "
    "its lag. Snapshotting stops being optional beyond a few thousand events per stream. **GDPR "
    "erasure against an immutable log is a genuine architectural problem**, not a policy question "
    "— crypto-shredding, where the personal data is encrypted per subject and the key is destroyed, "
    "is the usual answer and it is a commitment made on day one or not at all. And debugging "
    "requires reasoning about a temporal sequence rather than reading a row, which is a different "
    "and less common skill.",
    "Perfect history bought with a permanent versioning obligation and no ability to query directly.",
    "**The events are a permanent public API, and versioning them is the real cost of the "
    "pattern** — harder than any REST contract, because you cannot deprecate the past. A v1 event "
    "written three years ago must still be readable by today's code, forever, and it will be "
    "re-read every time a projection is rebuilt. Greg Young wrote an entire book, *Versioning in "
    "an Event Sourced System*, on this single problem, which is the clearest available signal of "
    "where the cost actually lands. The practical rules that follow: no field's meaning is ever "
    "changed, only added; old versions are translated on read by upcasters rather than migrated in "
    "place; and a weak schema — one where an unknown field is ignored rather than fatal — is "
    "chosen deliberately at the start. The second discipline is naming. Events record **what "
    "happened in the domain**, never the shape of the current data model: an event called "
    "`UserUpdated` carrying a diff of changed columns is a database trigger wearing a costume, it "
    "encodes today's schema into a permanent record, and it will not survive its first refactor. "
    "`AddressCorrected` and `CustomerMoved` are different events with different downstream "
    "meanings, and a row diff cannot tell them apart.",
    "Martin Fowler's 2005 bliki entry is the canonical description, and accounting is the "
    "thousand-year-old precedent — a ledger is append-only and a correction is a new entry, never "
    "an erasure. Greg Young's *Versioning in an Event Sourced System* is the practitioner text and "
    "exists because versioning is where teams fail rather than where they start. Crypto-shredding "
    "as the GDPR answer is established practice across event-sourced systems: encrypt each data "
    "subject's personal fields under a per-subject key held outside the log, and erasure becomes "
    "deleting one key while the event stream stays immutable.",
    """flowchart LR
    E1["v1 AccountOpened<br/>written 2021"] --> UP["Upcaster<br/>v1 to v3 on read"]
    E2["v2 event<br/>written 2023"] --> UP
    E3["v3 event<br/>today"] --> UP
    UP --> F["Fold to current state"]
    UP --> PR["Rebuild any projection<br/>replays every version, forever"]
    style UP fill:#2a2317,stroke:#d9a441,color:#e4ecea"""),

"Transactional Outbox": P(
    "Make publishing an event part of the same local transaction as the state change it describes.",
    "Any service that owns data and also emits events about it — order services, ledgers, user "
    "directories. Debezium's outbox router, and hand-rolled relays in most mature event-driven "
    "estates.",
    "Insert the event into an outbox table inside the business transaction, then let a relay read "
    "committed rows and publish them. The relay either polls the table or tails the database's "
    "replication log.",
    "The dual-write problem: two systems, one operation, no shared transaction. Any crash in "
    "between produces either a state change nobody heard about or an announcement of something "
    "that did not happen.",
    "Atomicity without a distributed transaction, a coordinator, or XA. Works on any database with "
    "local transactions. Preserves per-aggregate ordering for free, because the outbox rows commit "
    "in transaction order.",
    "The relay is infrastructure you now own — its lag, its restarts, its at-least-once "
    "duplicates. The outbox table is one of the highest-churn tables in the database; on "
    "PostgreSQL a never-pruned outbox generates dead tuples faster than autovacuum reclaims them "
    "and becomes the slowest table you have. Events are published after the commit, so there is "
    "always a window in which the state is visible and the event is not. And log-tailing relays "
    "couple you to the database's replication mechanism as a public interface.",
    "Atomic publish bought with a relay, a hot table and a permanently asynchronous event.",
    "**The outbox buys at-least-once, never exactly-once, and the half most write-ups omit is the "
    "other end.** It guarantees the event is *published* if and only if the transaction committed. "
    "It guarantees nothing about the event being *processed* once: the relay can crash after "
    "publishing and before marking the row, the broker can redeliver, the consumer can fail after "
    "the side effect. Pat Helland made the pairing explicit in *Life beyond Distributed "
    "Transactions* (CIDR 2007) — once you give up distributed transactions, at-least-once messaging "
    "is only usable in combination with idempotent receivers, and the two patterns are one design, "
    "not two options. An outbox without an idempotency key at the far end has relocated the bug, "
    "not removed it. The operational discipline that goes with it: the outbox table is deleted "
    "from or partitioned aggressively, ideally with the relay marking and a separate job dropping "
    "whole partitions rather than issuing row deletes, because the row-delete pattern is what "
    "produces the bloat. And the relay's lag is a first-class alert, because the failure mode of a "
    "stopped relay is a database that looks perfectly healthy while the rest of the estate "
    "silently drifts out of date.",
    "Pat Helland's *Life beyond Distributed Transactions: an Apostate's Opinion* (CIDR 2007) is "
    "the theoretical parent: it argues that scalable systems must abandon distributed transactions "
    "and that what replaces them is local transactions plus at-least-once messaging plus "
    "idempotent receivers. The outbox is the mechanism for the first two. On the operational side, "
    "the PostgreSQL replication-slot hazard is well documented and repeatedly rediscovered: a "
    "logical slot retains write-ahead log until its consumer advances, so a relay that stops "
    "consuming will fill the primary's disk and take the database down — the outbox's own "
    "reliability mechanism becoming the outage.",
    """flowchart TD
    TX["One local transaction"] --> R1["business row"]
    TX --> R2["outbox row"]
    R2 --> REL["Relay"]
    REL -->|"publish, then mark<br/>crash in between"| DUP["Duplicate publish"]
    DUP --> C["Consumer"]
    C --> ID["Idempotent receiver<br/>required, not optional"]
    style ID fill:#1c6853,stroke:#4fc3a1,color:#e4ecea
    style DUP fill:#2a2317,stroke:#d9a441,color:#e4ecea"""),

"Change Data Capture": P(
    "Turn a database's own replication log into a stream of change events for other systems.",
    "Debezium over MySQL binlog and PostgreSQL logical decoding, Netflix's DBLog, Airbnb's "
    "SpinalTap, Kafka Connect source connectors, every modern data warehouse ingestion path.",
    "A connector reads the write-ahead log or binary log the database already writes for its own "
    "replicas, decodes each committed row change, and publishes it — usually with before and after "
    "images and a transaction id.",
    "Downstream systems — search indexes, caches, warehouses, other services — need to know when "
    "data changes, and the alternatives are worse: polling with an `updated_at` column misses "
    "deletes and hard-to-order updates, and triggers put your integration logic inside the "
    "database's transaction path.",
    "No application change at all, which is why it is the only viable option for legacy systems. "
    "It cannot miss a change, because it reads the same log the database's own replicas trust. "
    "Ordering is exactly the commit order. Deletes are captured, which polling cannot do.",
    "You are coupled to a private interface of the database, and the connector breaks on engine "
    "upgrades. **A PostgreSQL logical replication slot retains WAL until its consumer advances, so "
    "a stopped CDC consumer fills the primary's disk and takes the database down** — the ingestion "
    "pipeline becoming the outage. There is no domain context in a row change: you can see "
    "`status` moved from 3 to 4, not that the customer cancelled, and reconstructing intent "
    "downstream is guesswork. Schema changes flow through mid-stream and every consumer must cope. "
    "And the initial snapshot is a genuinely hard problem, not a footnote.",
    "Zero-touch change events bought with permanent coupling to your schema and to the database's "
    "internals.",
    "**CDC publishes your schema, not your domain, and that is the defect hiding inside its "
    "greatest selling point.** Because no application change is needed, no application team is "
    "involved, and within a year six consumers depend on your column names, your nullability and "
    "your enum integers — you have accidentally published your physical data model as an API to "
    "teams who never told you they were reading it, and you cannot rename a column without an "
    "incident. Teams that survive CDC put a transformation at the source so that what is published "
    "is an *event* with a stable contract, which in practice converges on the outbox pattern: CDC "
    "the outbox table, not the business tables. The second thing they get right is the initial "
    "snapshot. Loading a large table consistently with the ongoing log without locking it for "
    "hours is the part that defeats naive implementations, and Netflix published DBLog precisely "
    "for it — chunked selects interleaved with the live change log, delimited by watermark events "
    "written into the log itself so the framework can tell which chunk rows are stale, with no "
    "locks and a resumable, pausable snapshot.",
    "Debezium is the dominant open implementation and the Netflix DBLog paper by Andreakis and "
    "Papapanagiotou is the best public account of the snapshot problem — its contribution is "
    "watermark-based chunked snapshotting that runs concurrently with log consumption instead of "
    "requiring a lock or a stop-the-world initial load. Airbnb's SpinalTap solves the same problem "
    "over MySQL binlogs. The PostgreSQL replication-slot disk-fill failure is not hypothetical; it "
    "is a recurring production incident across the industry and the reason `max_slot_wal_keep_size` "
    "exists.",
    """flowchart LR
    DB["Primary database"] -->|"WAL or binlog"| CDC["CDC connector"]
    CDC -->|"row changes"| K["Stream"]
    K --> C1["Search index"]
    K --> C2["Warehouse"]
    K --> C3["Another service"]
    C1 -.->|"depends on column names"| DB
    CDC -.->|"consumer stalls"| W["WAL retained<br/>primary disk fills<br/>database goes down"]
    style W fill:#2b1c17,stroke:#e0705a,color:#e4ecea"""),

"Leader Election": P(
    "Choose exactly one node to perform a role that must not be performed by two.",
    "Kubernetes controller managers, Kafka's controller, ZooKeeper and etcd-backed applications, "
    "database primary selection, any cron job that must run once across a fleet.",
    "Nodes contend for a lease in a consensus-backed store. The winner holds it for a bounded term "
    "and must renew before expiry; if it fails to renew, the lease expires and another node can "
    "acquire it.",
    "Some work must be done by exactly one actor — advancing a schema migration, assigning "
    "partitions, sending an invoice — and doing it twice is worse than doing it late.",
    "Turns a coordination problem into a single-writer problem, which is enormously simpler. "
    "Failover is automatic. It composes: the leader can then use ordinary single-node reasoning "
    "for the work it owns.",
    "Election takes time, and during it there is no leader — your availability floor is failure "
    "detection plus election duration, and tightening detection to shorten it directly increases "
    "false positives and needless failovers. The leader is a single-writer bottleneck by "
    "construction, so it caps throughput. And it introduces a hard dependency on the consensus "
    "store, which is now in the critical path of a component that may not otherwise need one.",
    "Single-writer simplicity bought with an availability gap on every failover and a hard "
    "dependency on consensus.",
    "**An election result is a claim about the past, not a fact about the present.** By the time a "
    "node reads 'I am the leader' and acts on it, the lease may already have expired — a stop-the-"
    "world GC pause, a hypervisor stall or a network partition is enough, and none of them are "
    "rare. The node has no way to detect that time passed, because from inside the pause no time "
    "did. So the leader flag alone is never sufficient: every write the leader makes must carry a "
    "**monotonically increasing fencing token**, and the storage layer must reject any token lower "
    "than the highest it has already accepted. That is the only construction where a paused old "
    "leader waking up cannot overwrite the new one, and it requires the *resource* to participate "
    "— which is why the fix cannot live entirely in the lock service. The second thing they do is "
    "make the leader's work idempotent and resumable anyway, on the assumption that two nodes will "
    "at some point both believe they lead, because the alternative is a system whose correctness "
    "depends on a timing assumption the network does not honour.",
    "Google's Chubby paper (Burrows, OSDI 2006) is the foundational account, and it includes the "
    "fencing mechanism as *sequencers* — an opaque token a lock holder passes to any service it "
    "acts against, so that service can reject stale holders. The paper also reports a genuine "
    "surprise from operating it: Chubby's dominant use turned out to be as a name service rather "
    "than as a lock service, because developers wanted a consistent place to put small "
    "configuration far more often than they wanted mutual exclusion.",
    """sequenceDiagram
    participant N1 as NodeA
    participant L as LeaseStore
    participant S as Storage
    N1->>L: acquire lease, token 33
    Note over N1: 40s GC pause, lease expires
    L->>L: NodeB acquires, token 34
    N1->>S: write with token 33
    S--)N1: rejected, 33 is lower than 34
    Note over N1,S: without the token this write silently wins"""),

"Consensus (Raft/Paxos)": P(
    "Get a set of nodes to agree on a single value, or on an ordered log of values, despite some "
    "of them failing.",
    "etcd behind Kubernetes, ZooKeeper, Consul, CockroachDB and Spanner's replication groups, "
    "Kafka's KRaft controller quorum.",
    "Elect a leader, have it append entries to a replicated log, and consider an entry committed "
    "once a majority of nodes have durably acknowledged it. A new leader is only electable if it "
    "holds every committed entry.",
    "Replication without agreement gives you divergence, and divergence in metadata — who owns "
    "which shard, which node is primary — is unrecoverable. Something has to be the arbiter of "
    "truth, and it cannot be a single machine.",
    "Linearisable writes with automatic failover, surviving the loss of a minority of nodes. The "
    "committed log is identical on every replica, so any of them can be promoted safely. It is one "
    "of the very few genuinely solved problems in distributed systems.",
    "Every committed write costs a majority round trip, so throughput is capped by one leader and "
    "latency is floored by the network distance to the median replica — a three-region cluster has "
    "a write latency floor set by the speed of light. It is CP by construction: the minority side "
    "of a partition is unavailable, deliberately. Cluster membership change is historically the "
    "buggiest part of every implementation. And only odd sizes make sense — a four-node cluster "
    "tolerates exactly one failure, the same as three, while costing more and being slower.",
    "Agreement bought with a majority round trip on every write and unavailability during "
    "partition.",
    "**They do not implement it.** The gap between the algorithm and a working system is the "
    "subject of Google's *Paxos Made Live* — the algorithm is a page of pseudocode and the "
    "production system was thousands of lines handling disk corruption, group membership change, "
    "master leases, and the discovery that the published algorithm underspecified most of what "
    "matters. That paper exists because the gap surprised the people who wrote it. So: etcd, "
    "ZooKeeper, or a library with a proven test suite, and if the answer is 'we wrote our own Raft "
    "because the libraries did not fit', that is the finding. The second thing they know is **what "
    "consensus is for**: it holds the small, critical state that decides where the large state "
    "lives. Nobody puts application data in etcd — Kubernetes puts object metadata there and the "
    "container images somewhere else, Spanner runs Paxos per shard rather than across the whole "
    "database. Consensus is a coordination primitive, and using it as a datastore is how teams "
    "discover the throughput ceiling the hard way. Third, they place replicas with the majority "
    "arithmetic in mind: three replicas across three availability zones survives an AZ loss, three "
    "replicas across two does not.",
    "Ongaro and Ousterhout's *In Search of an Understandable Consensus Algorithm* (USENIX ATC "
    "2014) is Raft, and its stated design goal was understandability precisely because Paxos had "
    "proven too hard to implement correctly. Chandra, Griesemer and Redstone's *Paxos Made Live* "
    "(PODC 2007) is Google's account of building Chubby's Paxos implementation and is the more "
    "useful read for a practitioner, because it is a catalogue of everything the algorithm does "
    "not tell you.",
    """sequenceDiagram
    participant C as Client
    participant L as Leader
    participant F1 as Follower1
    participant F2 as Follower2
    C->>L: write x equals 5
    L->>F1: append entry
    L->>F2: append entry
    F1--)L: ack
    Note over L: majority reached at 2 of 3, F2 not needed
    L--)C: committed
    Note over L,F2: every write pays one majority round trip, always"""),

"Quorum": P(
    "Require overlapping subsets of replicas for reads and writes so that a read is guaranteed to "
    "see a write.",
    "Cassandra and ScyllaDB's tunable consistency levels, DynamoDB, Riak, MongoDB's write and read "
    "concerns, any Dynamo-style store.",
    "With N replicas, a write must be acknowledged by W of them and a read must consult R of "
    "them. If `R + W > N` the two sets must share at least one replica, so the read set contains "
    "at least one copy of the latest write.",
    "Waiting for all replicas makes availability the product of theirs and latency the maximum of "
    "theirs. Waiting for one gives no consistency at all. Quorums let you pick a point between "
    "those and move it per query.",
    "Consistency becomes a per-operation dial rather than a system-wide architecture decision. The "
    "system tolerates the loss of a minority of replicas without becoming unavailable. Latency is "
    "the Wth fastest response, not the slowest, which cuts the tail meaningfully.",
    "`W` acknowledgements means `N - W` replicas are stale until repair catches them, so reads at "
    "`R = 1` see old data. Quorum writes are not atomic: a write acknowledged by 2 of 3 that "
    "partially failed leaves the value present on some replicas and absent on others with no "
    "rollback, so a subsequent read can see it or not depending on which replicas answer. And the "
    "arithmetic conveys much less than people assume.",
    "Tunable consistency bought with staleness on the replicas outside the quorum and no atomicity.",
    "**`R + W > N` guarantees the read set intersects the write set. It does not guarantee you "
    "read the latest value** — it guarantees that one of the values you read is the latest, and "
    "you still need a way to tell which one that is. Without per-value versioning, timestamps or "
    "vector clocks, the intersection property is useless, and 'we use quorums so we are "
    "consistent' is one of the most confidently wrong sentences in the field. The second thing, "
    "and the one that catches even careful people: **a sloppy quorum breaks the arithmetic "
    "entirely**. Dynamo-style systems, under failure, accept W acknowledgements from any W healthy "
    "nodes rather than from the N that own the key, which keeps writes available and means the "
    "read set and the write set may no longer overlap at all — precisely in the failure scenario "
    "you added quorums to survive. Cassandra's `LOCAL_QUORUM` has a related trap: it is a quorum "
    "within one data centre, so two data centres can each satisfy their local quorum with "
    "conflicting values. Third, they choose W and R from the read/write ratio rather than "
    "symmetrically — `W=N, R=1` is right for a read-heavy store that can tolerate write "
    "unavailability, and it is a strictly better choice than `W=2, R=2` for that workload.",
    "The Dynamo paper (DeCandia et al., SOSP 2007) introduced the N, R, W formulation and also "
    "introduced the sloppy quorum with hinted handoff, documenting both the availability benefit "
    "and the fact that the intersection guarantee is relaxed. Martin Kleppmann's *Designing "
    "Data-Intensive Applications* works through why quorum consistency is weaker than it looks, "
    "including concurrent writes, partial write failure and the sloppy-quorum case.",
    """flowchart TD
    A["N equals 3, W equals 2, R equals 2"] --> B["R plus W is 4, greater than 3"]
    B --> C["Read set and write set must share a replica"]
    C --> D["You read two values<br/>one of them is the latest<br/>versioning tells you which"]
    A --> E["Node down, sloppy quorum"]
    E --> F["W taken from any 2 healthy nodes<br/>not the 2 that own the key"]
    F --> G["No overlap guarantee<br/>in exactly the failure it was for"]
    style D fill:#1c6853,stroke:#4fc3a1,color:#e4ecea
    style G fill:#2b1c17,stroke:#e0705a,color:#e4ecea"""),

"Consistent Hashing": P(
    "Map keys and nodes onto the same ring so that adding or removing a node moves only a small "
    "fraction of keys.",
    "Dynamo, Cassandra, Riak, memcached client libraries, CDN request routing, Envoy's ring hash "
    "load balancer.",
    "Hash both keys and nodes into one circular space. A key belongs to the first node clockwise "
    "from it. Removing a node hands its arc to its successor and leaves every other key untouched.",
    "With `hash(key) mod N`, changing N remaps almost every key. For a cache that means a near "
    "total miss storm at the exact moment you were adding capacity because you were under load; "
    "for a store it means moving the entire dataset.",
    "Only about `1/N` of keys move when a node joins or leaves. Scaling and failure become "
    "incremental rather than global. Clients can compute placement locally with no lookup service "
    "and no coordination.",
    "**Without virtual nodes the distribution is badly uneven.** Hashing N nodes to N random points "
    "does not divide the ring into N equal arcs — the largest arc is on the order of `log N` times "
    "the average, and with ten nodes it is entirely normal to see one holding three times its "
    "share of the keyspace. Removing a node dumps its entire range onto the single successor, so a "
    "failure doubles one survivor's load at the worst possible moment. And a heterogeneous fleet "
    "cannot be expressed at all: a machine with twice the memory still gets one arc.",
    "Incremental rebalancing bought with an uneven distribution that must be corrected by virtual "
    "nodes.",
    "They never deploy the plain ring. Each physical node claims **many** points on the ring — "
    "Dynamo used on the order of 100 to 200 tokens per node — and the variance averages away, "
    "distribution flattens to within a few percent, a departing node's load spreads across many "
    "survivors instead of landing on one, and capacity-weighted placement falls out for free by "
    "giving a bigger machine more tokens. The number of virtual nodes is a real trade: more tokens "
    "means flatter distribution and a larger ring to gossip, store and search. The second thing "
    "they know, and it is the one that ends arguments: **consistent hashing balances keys, not "
    "load.** One hot key defeats it completely and no number of virtual nodes helps, because a "
    "single key cannot be split — the answer there is replication of that key or a different "
    "partitioning scheme, not more tokens. Third, they know the alternatives exist and are "
    "sometimes better: rendezvous hashing gives comparable properties without a ring, and Google's "
    "jump consistent hash is faster and uses no memory but cannot handle arbitrary node removal, "
    "which makes it right for a fixed-size shard set and wrong for an elastic fleet.",
    "Karger et al. introduced consistent hashing in 1997 for distributed web caching, which became "
    "the basis of Akamai's request routing. Amazon's Dynamo paper (SOSP 2007) is the source for "
    "virtual nodes and is explicit about why: the basic algorithm produced non-uniform data and "
    "load distribution, and made no allowance for heterogeneous hardware. Lamping and Veach's *A "
    "Fast, Minimal Memory, Consistent Hash Algorithm* (Google, 2014) is the jump-hash alternative.",
    """flowchart TD
    K["3 nodes, 1 ring point each"] --> A1["Node A holds 52 percent"]
    K --> B1["Node B holds 31 percent"]
    K --> C1["Node C holds 17 percent"]
    V["Same 3 nodes, 150 points each"] --> A2["Node A holds 34 percent"]
    V --> B2["Node B holds 33 percent"]
    V --> C2["Node C holds 33 percent"]
    style A1 fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style A2 fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),

"Vector Clocks": P(
    "Track causality between events by giving each writer its own counter, so concurrent updates "
    "can be distinguished from sequential ones.",
    "Dynamo and its descendants, Riak, Voldemort, collaborative editors, Amazon's original "
    "shopping cart.",
    "Every object carries a map of writer identity to counter. A writer increments its own entry "
    "on write. Version X dominates Y if every counter in X is at least Y's and one is greater; if "
    "neither dominates, the versions are concurrent and in conflict.",
    "Wall-clock timestamps cannot order events across machines — clocks skew, NTP steps, and "
    "last-writer-wins on a skewed clock silently discards the write that actually came second. "
    "Causality needs a logical clock, not a physical one.",
    "Concurrent updates are *detected* rather than silently lost, which is the difference between "
    "a conflict you can resolve and data that vanished. No clock synchronisation required. "
    "Causally ordered updates are correctly recognised as ordered, so only genuine conflicts "
    "surface.",
    "**The clock grows with the number of writers**, and in a client-facing system the writers are "
    "clients, so the metadata can approach or exceed the size of the value. Truncating it — which "
    "is the only practical remedy — reintroduces false concurrency: two causally ordered versions "
    "get reported as conflicting. And the resolution burden lands on the application, which most "
    "applications have no sensible answer for.",
    "Correct causality detection bought with unbounded metadata and a conflict you must now resolve "
    "yourself.",
    "**A vector clock only detects a conflict. It never resolves one** — and the resolution is the "
    "hard part, which is why Dynamo pushed it to the application and why the shopping cart is the "
    "example in every retelling. The cart is famous because merging carts by union is one of the "
    "very few domains where the merge is obviously correct, and even there Amazon accepted the "
    "documented consequence that a deleted item can reappear. If your domain does not have an "
    "obviously correct merge, vector clocks hand you a conflict at read time and no way to answer "
    "it. The second thing practitioners know is the sizing problem and its history: Dynamo capped "
    "the clock at ten entries and truncated the oldest, an accepted, documented incorrectness, and "
    "Riak eventually replaced plain version vectors with **dotted version vectors** because "
    "concurrent client writes caused sibling explosion. The lesson is that the writer identity "
    "should be the *server* coordinating the write, not the client, which bounds the vector by "
    "replica count instead of by user count.",
    "The Dynamo paper (SOSP 2007) is the reference deployment and includes both the ten-entry "
    "truncation and a striking measurement: over a 24-hour production period, 99.94 percent of "
    "requests saw exactly one version, meaning conflicts are rare but not rare enough to ignore. "
    "Preguiça et al.'s dotted version vectors, adopted by Riak, are the correction for the "
    "client-as-writer problem.",
    """flowchart TD
    S["Cart at A:1"] --> W1["Client X adds book<br/>A:2"]
    S --> W2["Client Y adds pen<br/>B:1 with A:1"]
    W1 --> M{"Neither dominates"}
    W2 --> M
    M --> C["Concurrent, both kept as siblings"]
    C --> R["Application merges by union<br/>cart is correct"]
    C --> D["A previously removed item<br/>can reappear"]
    style R fill:#1c6853,stroke:#4fc3a1,color:#e4ecea
    style D fill:#2a2317,stroke:#d9a441,color:#e4ecea"""),

"CRDT": P(
    "A data type whose replicas can be updated independently and merged deterministically, with no "
    "coordination and no conflicts.",
    "Redis Enterprise active-active databases, Riak 2.0 data types, Automerge and Yjs in "
    "collaborative editors, Apple's Notes syncing, Azure Cosmos DB's conflict resolution.",
    "Operations are designed so that merge is commutative, associative and idempotent. State-based "
    "CRDTs ship the whole state and merge by a least-upper-bound function; operation-based CRDTs "
    "ship operations that commute. Either way, replicas that have seen the same set of updates are "
    "identical regardless of order.",
    "Offline and multi-region writes need to converge without a coordinator. Last-writer-wins "
    "silently discards data, and locking across regions gives up the availability you went "
    "multi-region for.",
    "Strong eventual consistency with no coordination whatsoever, so writes are always available "
    "and always local. Partitions cause no conflicts to resolve later. Offline clients merge "
    "cleanly when they reconnect.",
    "Metadata dominates. Removal is the recurring problem: a grow-only set cannot remove, a "
    "two-phase set can never re-add a removed element, and an observed-remove set works but "
    "accumulates tombstones that must eventually be collected — and tombstone garbage collection "
    "is itself a distributed agreement problem, which is the thing you were avoiding. Not every "
    "domain has a commutative merge, and inventory is the standard counterexample: two replicas "
    "each selling the last unit merge into a consistent, converged, oversold state.",
    "Coordination-free convergence bought with metadata growth and a merge rule you must decide in "
    "advance for every case.",
    "The hard part is never writing the merge function — it is that **the merge is forced to be "
    "commutative, which means you must decide the resolution rule at design time for every "
    "concurrent pair, in advance, with no context.** A CRDT does not remove the conflict; it makes "
    "you pre-answer it, and the answer is baked into the type. That reframing is what separates "
    "people who have shipped one from people who have read about them. The second thing "
    "experienced teams do is ask whether they need one at all, because a CRDT's entire value is "
    "operating without a central authority — and most systems have one. **Figma published exactly "
    "this reasoning**: they took inspiration from CRDTs for multiplayer editing but deliberately "
    "did not use the general machinery, because with a server that can order operations, most of "
    "what CRDTs buy is unnecessary and the metadata cost is real. Third, where CRDTs are genuinely "
    "warranted they keep the types small and boring — counters, registers, observed-remove sets, "
    "maps of those — and resist the sequence CRDTs needed for rich text, which are where the "
    "complexity and the interleaving anomalies live.",
    "Shapiro, Preguiça, Baquero and Zawirski's *A Comprehensive Study of Convergent and Commutative "
    "Replicated Data Types* (INRIA, 2011) is the founding taxonomy. Riak 2.0 shipped CRDT data "
    "types as a first-class feature, and Redis Enterprise's active-active geo-distributed databases "
    "are built on them. Evan Wallace's *How Figma's multiplayer technology works* (2019) is the "
    "most useful counter-case in the literature: a real-time collaborative product explaining, in "
    "public, why it chose not to use general CRDTs.",
    """flowchart TD
    R1["Replica 1<br/>add x, remove y"] --> M["Merge<br/>commutative and idempotent"]
    R2["Replica 2<br/>add z, remove y"] --> M
    M --> C["Both replicas converge<br/>no coordination, no conflict"]
    M --> T["Tombstone for y must be kept<br/>or a stale add resurrects it"]
    T --> G["Collecting tombstones needs agreement<br/>the thing CRDTs avoid"]
    style C fill:#1c6853,stroke:#4fc3a1,color:#e4ecea
    style G fill:#2a2317,stroke:#d9a441,color:#e4ecea"""),

"Two-Phase Commit": P(
    "An atomic commit protocol in which a coordinator asks every participant to prepare, then "
    "tells all of them to commit or all to abort.",
    "XA transactions across databases and message brokers, distributed SQL engines, Spanner and "
    "Percolator across their shard groups, classic enterprise transaction monitors.",
    "Phase one: the coordinator sends prepare, each participant durably logs everything needed to "
    "commit, takes its locks and answers yes or no, thereby surrendering its right to decide "
    "unilaterally. Phase two: if all said yes the coordinator logs commit and tells everyone, "
    "otherwise it tells everyone to abort.",
    "One logical operation spans several independently transactional systems, and partial success "
    "is not acceptable — the money must leave one ledger if and only if it arrives in the other.",
    "Genuine atomicity across heterogeneous resource managers, with real isolation, and no "
    "compensation logic to write. It is the only pattern here that gives you the semantics people "
    "actually want.",
    "Locks are held for the entire protocol, across the network, so throughput collapses under "
    "contention. Latency is at least two round trips plus a durable log write at every "
    "participant. XA recovery across heterogeneous vendors is famously patchy, and 'heuristic "
    "outcomes' — where a DBA manually resolves an in-doubt transaction and may resolve it "
    "inconsistently with the others — are a documented, expected part of the standard.",
    "True atomicity bought with held locks and a protocol that blocks when the coordinator fails.",
    "**Two-phase commit blocks, and it is not a tuning problem — it is the protocol.** Between "
    "prepare and commit a participant has voted yes: it holds its locks and has given up the right "
    "to decide alone, because the coordinator may already have gathered every vote and logged a "
    "commit decision. If the coordinator dies in that window, the participant cannot proceed and "
    "cannot release. No timeout is safe — aborting unilaterally risks contradicting a commit that "
    "was already decided and possibly already applied elsewhere — so it waits for a coordinator "
    "that may never return, holding locks that block everyone else. This is a theorem rather than "
    "an implementation defect: Skeen showed there is no non-blocking atomic commit protocol in an "
    "asynchronous system where the coordinator can fail, and three-phase commit escapes it only by "
    "assuming synchrony and bounded message delay, which real networks do not provide. So the top "
    "1 percent do one of two things. Either they make the coordinator itself fault-tolerant, which "
    "is exactly Spanner's construction — every participant *and* the coordinator is a Paxos group, "
    "so 'the coordinator died' becomes 'the coordinator failed over' and the blocking window "
    "closes — or they decline the distributed transaction entirely and use a saga, accepting the "
    "loss of isolation as the price of not blocking.",
    "Google's Spanner paper (OSDI 2012) is the most instructive case, because it uses 2PC and is "
    "fast: the trick is that it runs 2PC *over* Paxos groups, so no single machine failure can "
    "leave the protocol stuck, and the usual objection to 2PC no longer applies. Pat Helland's "
    "*Life beyond Distributed Transactions: an Apostate's Opinion* (CIDR 2007) is the argument for "
    "the other path, from someone who built transaction systems and concluded that scalable "
    "applications should stop using them.",
    """sequenceDiagram
    participant C as Coordinator
    participant P1 as ParticipantA
    participant P2 as ParticipantB
    C->>P1: prepare
    C->>P2: prepare
    P1--)C: yes, locks held
    P2--)C: yes, locks held
    Note over C: coordinator crashes here
    Note over P1,P2: both hold locks, cannot abort, cannot commit
    Note over P1,P2: no safe timeout exists, this is the protocol"""),

"Gossip": P(
    "Spread information by having each node periodically tell a few random peers what it knows.",
    "Cassandra and ScyllaDB cluster membership, Consul and Serf, HashiCorp Nomad, Redis Cluster's "
    "bus, Bitcoin and Ethereum peer discovery.",
    "On a fixed interval each node picks a small random subset of peers and exchanges state "
    "digests, merging whatever is newer. No node has a complete view of who it must tell, and no "
    "node is required for the protocol to work.",
    "Broadcasting from a central point does not scale and creates a single point of failure. "
    "Maintaining a consistent membership list through consensus is expensive for information that "
    "is inherently approximate anyway.",
    "Converges in O(log N) rounds while each node does constant work per round, so it scales to "
    "very large clusters. It is extraordinarily robust — there is no coordinator, no fixed "
    "topology, and it routes around partitions and node loss automatically.",
    "The guarantee is probabilistic and eventual, with a tail nobody can bound: most nodes know "
    "quickly, and *some* node may not know for a long time. Every node's view is a slightly "
    "different, slightly stale picture, so 'the cluster state' does not exist as a single object. "
    "Bandwidth is constant and never zero, which at thousands of nodes becomes real. And gossip "
    "spreads a wrong belief exactly as efficiently as a right one.",
    "Scalable, robust dissemination bought with an eventual and unbounded convergence tail.",
    "They use it for membership and failure suspicion and **never for a decision**, because "
    "'eventually most nodes agree' is not a basis for choosing a leader or committing a write — "
    "gossip is the input to consensus, not a substitute for it. The subtler thing they design for "
    "is that gossip amplifies mistakes: a node under GC pressure gets marked down, then up, then "
    "down, and every flap is broadcast to the entire cluster, so the failure detector's false "
    "positives become cluster-wide churn. Serious implementations therefore separate *suspicion* "
    "from *failure*. SWIM introduces a suspect state that is itself gossiped, giving the accused "
    "node a chance to refute the rumour before it is declared dead, which collapses the false-"
    "positive rate without slowing genuine detection. Cassandra takes the other route with the phi "
    "accrual failure detector, which emits a continuous suspicion level derived from the observed "
    "distribution of heartbeat intervals rather than a boolean, so the threshold becomes a tuning "
    "knob that adapts to the network instead of a fixed timeout that is wrong on every network but "
    "one.",
    "Demers et al., *Epidemic Algorithms for Replicated Database Maintenance* (PODC 1987), came "
    "out of Xerox PARC's Clearinghouse directory service and is the origin of the anti-entropy and "
    "rumour-mongering vocabulary. SWIM (Das, Gupta and Motivala, DSN 2002) contributed the "
    "suspicion mechanism and the indirect probe, and is what Consul and Serf implement. Cassandra "
    "combines gossip with the phi accrual failure detector of Hayashibara et al., which is also "
    "used by Akka.",
    """flowchart TD
    N1["Node 1 learns a fact"] --> R1["Round 1: tells 2 peers"]
    R1 --> R2["Round 2: 4 nodes know"]
    R2 --> R3["Round 3: 8 nodes know"]
    R3 --> R4["log N rounds: nearly all know"]
    R4 --> T["Tail is unbounded<br/>some node is always behind"]
    N1 -.->|"a wrong belief spreads<br/>just as fast"| F["Flapping node marked down<br/>cluster-wide churn"]
    style F fill:#2b1c17,stroke:#e0705a,color:#e4ecea"""),

"Lease / Fencing Token": P(
    "Grant ownership for a bounded time, and make every action taken under it carry a "
    "monotonically increasing number the resource can check.",
    "Chubby sequencers, ZooKeeper's zxid and ephemeral nodes, Kubernetes lease objects, GFS and "
    "HDFS chunk leases, etcd lease-backed locks.",
    "The lock service issues a lease with an expiry and an increasing token. The holder renews "
    "before expiry. Every write the holder makes to a protected resource includes the token, and "
    "the resource rejects any token lower than the highest it has already accepted.",
    "A lock held forever by a crashed process is a deadlock, so locks must expire — and the moment "
    "they expire, the previous holder might still be alive and about to act. Expiry solves "
    "liveness and creates a correctness hole.",
    "Ownership survives holder crashes without human intervention, because the lease simply "
    "expires. The fencing token closes the correctness hole that expiry opens. The resource needs "
    "no knowledge of the lock service, only a comparison.",
    "It requires the *resource* to participate, which is often the blocker: you cannot fence a "
    "third-party API, a filesystem, or a database that will not store and compare a token. Leases "
    "depend on clocks, and the holder's clock and the issuer's clock disagree. Renewal traffic is "
    "constant load on the lock service, and a lock service outage means every lease in the system "
    "expires at roughly the same moment.",
    "Crash-safe ownership bought with a clock dependency and a resource that must enforce the "
    "token.",
    "**A lock without a fencing token is not a lock, it is a suggestion.** The failure is not "
    "exotic and does not require a Byzantine network: the holder enters a stop-the-world GC pause "
    "or is descheduled by the hypervisor for longer than its lease, the lease expires, a second "
    "node legitimately acquires it, and then the first node resumes with no idea that any time has "
    "passed and writes. Nothing in the lock service can prevent this, because the lock service was "
    "not involved in the write — the damage happens at the storage layer, so the storage layer has "
    "to be the one to refuse it. Kleppmann's 2016 analysis of Redlock is the sharpest public "
    "statement of the argument, and the part people miss is that his conclusion is not about "
    "Redis: **any** lease-based lock needs the token, including a perfectly correct one built on "
    "consensus, because the vulnerable window is on the client, not in the service. The second "
    "discipline is asymmetric expiry — the holder should treat its lease as expiring earlier than "
    "the issuer does, by a margin covering worst-case clock drift and pause duration, so it stops "
    "acting before anyone else can start.",
    "Gray and Cheriton introduced leases in *Leases: An Efficient Fault-Tolerant Mechanism for "
    "Distributed File Cache Consistency* (SOSP 1989). Google's Chubby paper documents the "
    "production form as sequencers, opaque tokens a lock holder passes to any service it acts "
    "against so that service can validate the holder is current. Martin Kleppmann's *How to do "
    "distributed locking* (2016) is the essay that put fencing tokens into mainstream practice, "
    "written as a critique of Redlock but making a general argument.",
    """sequenceDiagram
    participant A as HolderA
    participant LS as LockService
    participant ST as Storage
    A->>LS: acquire, gets token 33
    Note over A: process pause exceeds lease
    LS->>LS: lease expires
    Note over LS: HolderB acquires, token 34
    A->>ST: write, token 33
    ST--)A: reject, highest seen is 34
    Note over ST: only the resource can enforce this"""),

"Read Repair": P(
    "Detect and fix replica divergence during a read, using the responses you already collected.",
    "Cassandra, ScyllaDB, DynamoDB, Riak, and Dynamo-style stores generally.",
    "The coordinator reads from several replicas, compares versions, returns the newest to the "
    "client, and writes it back to any replica that returned something older — either before "
    "responding, or asynchronously afterwards.",
    "Eventually consistent replication leaves replicas divergent after failures, hinted handoff "
    "windows and dropped writes. Something has to converge them, and a background repair scanning "
    "the entire keyspace is expensive.",
    "Repairs come free with a read you were doing anyway, no extra scan required. Hot data — which "
    "is exactly the data whose staleness is most visible — converges continuously. It costs "
    "nothing when replicas agree, which is the overwhelming majority of reads.",
    "**It only repairs what is read.** The cold portion of the keyspace is never touched, so read "
    "repair on its own guarantees nothing about the data most likely to have drifted. Blocking "
    "read repair adds a write to the read path, so a hot key with one divergent replica turns "
    "every read into a write. And it interacts dangerously with deletes: a tombstone that expires "
    "before all replicas have received it lets a surviving old value be 'repaired' back into "
    "existence, which is how deleted data returns.",
    "Continuous convergence bought with coverage limited to the data you happen to read.",
    "They treat it as a complement to scheduled anti-entropy repair and **never as a replacement**, "
    "because the failure mode is delayed and quiet: a team disables scheduled repairs on the "
    "reasoning that read repair handles it, tombstones then age past `gc_grace_seconds` on a "
    "replica that never received them, and deleted records reappear weeks later. That is a data "
    "correctness incident caused by an operational shortcut, and it is common. The second thing "
    "they know is that the industry has moved on the cost question: Cassandra 4.0 removed the "
    "probabilistic background read repair settings entirely, having concluded that repairing on a "
    "random fraction of reads cost more than it returned and gave a false sense of coverage. What "
    "survives is blocking read repair at quorum consistency levels — where it is not really an "
    "optimisation but part of how the consistency level is delivered — plus a genuine repair "
    "schedule.",
    "The Dynamo paper (SOSP 2007) introduced read repair alongside hinted handoff and Merkle-tree "
    "anti-entropy as three complementary mechanisms, and it is worth noting that the paper "
    "presents all three because none of them is sufficient alone. Cassandra's removal of "
    "`read_repair_chance` and `dclocal_read_repair_chance` in 4.0 is the clearest public verdict "
    "on the background variant. The zombie-data hazard from repairing past `gc_grace_seconds` is "
    "documented in Cassandra's own operations guidance and is the reason repair is scheduled "
    "rather than optional.",
    """sequenceDiagram
    participant C as Coordinator
    participant R1 as Replica1
    participant R2 as Replica2
    participant R3 as Replica3
    C->>R1: read k
    C->>R2: read k
    C->>R3: read k
    R1--)C: v7
    R2--)C: v7
    R3--)C: v4, stale
    C--)C: newest is v7
    C->>R3: write back v7
    Note over C,R3: only keys that are read get fixed, cold data drifts"""),

"Hinted Handoff": P(
    "When a replica is unavailable, store its writes on another node and deliver them when it "
    "returns.",
    "Cassandra, Dynamo, Riak, Voldemort.",
    "The coordinator, unable to reach a replica, writes the data to a healthy node along with a "
    "hint recording who it was really for. When the intended replica comes back, the holder "
    "replays the hints to it and deletes them.",
    "Rejecting a write because one of three replicas is being restarted turns a routine deploy "
    "into an availability incident, and losing that write means the returning node is permanently "
    "behind until a full repair.",
    "Writes stay available through node restarts, brief partitions and rolling upgrades. A "
    "returning node catches up in seconds rather than needing an expensive full repair. It "
    "massively reduces how often anti-entropy has to do real work.",
    "**The promise is bounded and the bound is the part people forget** — Cassandra stops "
    "collecting hints after `max_hint_window_in_ms`, three hours by default, so a node down for "
    "four hours has silently missed an hour of writes and now needs a full repair that nobody was "
    "told to run. Hints consume disk on the coordinators, which during a long outage is disk you "
    "did not plan for. And replay is a load spike aimed at the node least able to absorb it: a "
    "recovering node is cold, its caches are empty, and it receives a backlog of writes from every "
    "coordinator simultaneously.",
    "Write availability during brief failures bought with a hard time bound and a replay storm on "
    "recovery.",
    "They alarm on the hint window being *exceeded*, not on hints existing, because the transition "
    "from 'hints are accumulating' to 'we have stopped taking hints' is the moment the system "
    "silently changed its guarantee, and nothing else marks it. Second, they treat the replay as a "
    "load event to be throttled rather than a background detail — a recovering node that is "
    "knocked over by its own hint backlog will be marked down again, generating more hints, which "
    "is a genuine self-sustaining failure loop. Third, and the one that changes designs: **with a "
    "sloppy quorum, a write that succeeded only because of hints did not satisfy the quorum "
    "intersection you believe you have.** The acknowledgement came from nodes that do not own the "
    "key and are holding the data on someone else's behalf, so a subsequent quorum read of the "
    "owning replicas can legitimately miss it. That is not a bug; it is the documented trade of "
    "sloppy quorums, and it means hinted handoff quietly weakens consistency in exchange for the "
    "availability it provides.",
    "The Dynamo paper (SOSP 2007) introduced hinted handoff together with the sloppy quorum, and "
    "is explicit that the pair trades the strict quorum guarantee for write availability. "
    "Cassandra's implementation makes the bound concrete and configurable through "
    "`max_hint_window_in_ms`, defaulting to three hours, after which hints are simply not stored "
    "and full repair becomes mandatory — a threshold many operators discover only after an "
    "extended outage.",
    """flowchart TD
    W["Write for replica C"] --> D{"Is C reachable"}
    D -->|"yes"| OK["Normal write"]
    D -->|"no, within 3h window"| H["Hint stored on another node"]
    D -->|"no, past 3h window"| X["No hint stored<br/>full repair now required<br/>nobody is told"]
    H --> R["C returns, all coordinators<br/>replay hints at once"]
    R --> S["Cold node hit by a write storm<br/>can be marked down again"]
    style X fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style S fill:#2a2317,stroke:#d9a441,color:#e4ecea"""),

"Merkle Tree": P(
    "A tree of hashes over a dataset, so two replicas can find exactly where they differ by "
    "exchanging a logarithmic number of hashes instead of the data.",
    "Cassandra's `nodetool repair`, Dynamo's anti-entropy, Git's object model, ZFS and Btrfs, "
    "BitTorrent, Certificate Transparency logs, blockchains.",
    "Hash each leaf-level chunk of data, hash each pair of hashes up the tree, and compare roots. "
    "Equal roots means identical data; unequal roots means you descend only into the subtrees that "
    "differ.",
    "Comparing two replicas by shipping all their data is prohibitive, and comparing key by key is "
    "prohibitive in round trips. You need a way to spend effort proportional to the *difference* "
    "rather than to the dataset.",
    "Comparison cost is logarithmic in the data size when replicas are nearly identical, which is "
    "the normal case. It is a cryptographic proof, so the same structure also proves inclusion and "
    "tamper-evidence, not just difference. It requires no coordination beyond exchanging hashes.",
    "**Building the tree requires reading all the data, every time**, so the comparison is cheap "
    "and the preparation is not. The tree must be rebuilt whenever the data changes, which for a "
    "live dataset is constantly. Granularity is a hard trade-off: fine leaves mean an enormous "
    "tree, coarse leaves mean a single differing row marks a wide range as divergent and you "
    "stream far more than you needed to.",
    "Cheap difference detection bought with a full data scan to build the structure.",
    "They know that the expensive part is not the comparison, which is what the pattern advertises "
    "— it is the scan. When someone asks why a Cassandra repair is slow, the answer is almost "
    "never the network: it is that every node must read every partition in the range to compute "
    "its tree before a single hash is exchanged. The second thing, which explains a genuinely "
    "confusing symptom, is **over-streaming from limited tree depth**. Cassandra caps the tree's "
    "depth, so one leaf can cover a wide token range, and a single changed row causes the entire "
    "range under that leaf to be streamed — which is why a repair that reports almost no "
    "divergence can still move gigabytes across the network. The operational consequence is that "
    "experienced teams repair narrow token ranges on a rolling schedule rather than running "
    "whole-cluster repairs, keeping each tree's leaves fine-grained enough that the streamed "
    "volume approximates the actual divergence. Third, they notice the structure's other use: the "
    "same tree that finds differences also produces an O(log n) inclusion proof, which is why it "
    "underpins tamper-evident logs and not just replica repair.",
    "The Dynamo paper (SOSP 2007) is the reference use for anti-entropy between replicas, and "
    "Cassandra's `nodetool repair` is the widely operated implementation — with the scan cost and "
    "the over-streaming behaviour being the two properties operators consistently learn about the "
    "hard way. RFC 6962, Certificate Transparency, is the best example of the other half of the "
    "structure: it uses Merkle audit paths to prove that a specific certificate is included in an "
    "append-only log, and consistency proofs to show the log was never rewritten, both in "
    "logarithmic size.",
    """flowchart TD
    RT["Root hash differs"] --> L["Left subtree<br/>hashes match, skip entirely"]
    RT --> R["Right subtree<br/>hashes differ, descend"]
    R --> R1["Range A, matches"]
    R --> R2["Range B, differs"]
    R2 --> S["Stream all of range B<br/>even if one row changed"]
    RT -.->|"before any of this"| SC["Full scan of the data<br/>to build the tree at all"]
    style S fill:#2a2317,stroke:#d9a441,color:#e4ecea
    style SC fill:#2b1c17,stroke:#e0705a,color:#e4ecea"""),
}

RESILIENCE = {
"Retry with backoff + jitter": P(
    "Re-attempt a failed operation after a randomised, exponentially growing delay.",
    "Every AWS SDK, gRPC's retry policy, Envoy retry budgets, Polly, resilience4j, and essentially "
    "every HTTP client library's default configuration.",
    "On a retryable failure, wait `base × 2^attempt` — then replace that with a random value drawn "
    "from `[0, base × 2^attempt]`, which is the variant AWS calls full jitter. Cap the total "
    "attempts and the total elapsed time.",
    "Most distributed failures are transient: a packet dropped, a node restarting, a leader "
    "election in progress. Failing the user's request for a fault that would clear in 40 "
    "milliseconds is a self-inflicted outage.",
    "Transient faults become invisible. It is the cheapest availability improvement available and "
    "needs no cooperation from the dependency. Exponential growth means a genuinely dead "
    "dependency is not hammered.",
    "**Retries amplify load at exactly the moment there is least capacity to serve it.** Retrying "
    "a non-idempotent operation duplicates it, and a request that timed out on the client but "
    "succeeded on the server will be duplicated no matter how careful the retry logic is. A "
    "dependency that is failing because it is overloaded is pushed further under by the retries, "
    "which is the mechanism behind most cascading failures.",
    "Transient-fault tolerance bought with load amplification during the failures that matter most.",
    "**Jitter is not a refinement, it is the whole point.** Exponential backoff alone keeps every "
    "client perfectly synchronised: they all fail at once, all sleep one second, all retry at "
    "once, all sleep two seconds, and the recovering service is hit by the same thundering herd at "
    "exponentially spaced intervals — the backoff has changed the timing of the stampede and not "
    "its size. AWS measured the variants and full jitter won on both total work and completion "
    "time. The second thing, which matters more and is missed far more often: **retries must live "
    "at exactly one layer.** Three retries in the client library, three in the API gateway and "
    "three in the calling service is 27 attempts for one user action, so a service already "
    "struggling receives a 27-fold amplification generated entirely by its callers' resilience "
    "policies. The discipline is to retry at one chosen layer, fail fast everywhere else, and "
    "**budget** the retries — a token bucket that caps retries at a small percentage of live "
    "traffic, which is what gRPC's retry throttling and Envoy's retry budgets implement, so that "
    "retry volume cannot grow without bound precisely when success rates collapse. Third: only "
    "retry what is retryable. A 400 will be a 400 forever.",
    "Marc Brooker's *Exponential Backoff And Jitter* on the AWS Architecture Blog (2015) is the "
    "definitive treatment — it simulates plain exponential backoff against several jitter "
    "strategies and shows full jitter reducing both contention and total work. The retry-budget "
    "idea is shipped in gRPC as retry throttling and in Envoy as a configurable retry budget, both "
    "of which exist because per-call retry limits provably do not bound fleet-wide retry load.",
    """flowchart TD
    U["1 user request"] --> C["Client retries 3x"]
    C --> G["Gateway retries 3x"]
    G --> S["Service retries 3x"]
    S --> D["Dependency sees 27 attempts"]
    D --> F["Already overloaded<br/>now 27x overloaded"]
    B["Retry at one layer only<br/>plus a token-bucket budget"] --> OK["Retry volume bounded<br/>even as success rate collapses"]
    style F fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style OK fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),

"Circuit Breaker": P(
    "Stop calling a dependency that is already failing, and periodically test whether it has "
    "recovered.",
    "Netflix Hystrix historically, resilience4j, Envoy and Istio outlier detection, Polly, "
    "Finagle.",
    "Count failures over a rolling window. Past a threshold the breaker opens and calls fail "
    "immediately without touching the network. After a cool-down it half-opens, allows a limited "
    "probe, and closes on success or re-opens on failure.",
    "Calling a dead dependency still costs a connection, a thread and a full timeout. Under load "
    "that means every worker in your service is blocked waiting on something that will not answer, "
    "and your service dies of someone else's outage.",
    "The caller stays responsive and keeps its resources for work it can actually do. Fallbacks "
    "become possible because failure is immediate rather than after 30 seconds. The failing "
    "dependency gets breathing room to recover.",
    "An open breaker converts a partial outage into a total one for that path, which is only "
    "correct if the fallback is genuinely acceptable. A shared breaker in front of a "
    "multi-tenant dependency opens for everyone because of one tenant's bad requests. Every "
    "threshold is a guess that goes stale as traffic patterns change, and a breaker that is "
    "mistuned in the safe direction simply never fires.",
    "Caller protection bought with a threshold that is always a guess and a fallback you must "
    "have.",
    "The breaker exists to protect the **caller**, not the callee — its primary job is to stop you "
    "queueing threads against something already dead, and the relief it gives the dependency is a "
    "side benefit. Getting that backwards leads to breakers configured as if they were rate "
    "limits. The half-open state is where the real design lives: too many probes and you re-kill a "
    "service that was two seconds from recovering, too few and you stay open long after it healed, "
    "so probes are single-flight and closing requires several consecutive successes rather than "
    "one. **The tell of a badly configured breaker is one that has never opened**, and the usual "
    "cause is a threshold set on an absolute error count rather than an error rate over a rolling "
    "window with a minimum-volume gate — during a low-traffic outage the count never reaches the "
    "threshold, so the breaker sleeps through the incident. The last thing worth knowing is where "
    "the industry went: Netflix, who popularised the pattern with Hystrix, put Hystrix into "
    "maintenance in 2018 and moved to adaptive concurrency limits, on the reasoning that "
    "hand-tuned per-dependency thresholds are a configuration burden that silently goes stale, "
    "while a limit inferred from observed latency does not.",
    "Michael Nygard introduced the pattern in *Release It!* (2007), where it appears alongside the "
    "stability antipatterns it defends against. Netflix's Hystrix made it mainstream and its "
    "retirement is the more interesting data point: the project entered maintenance mode in 2018 "
    "with Netflix explicitly recommending adaptive alternatives, and their open-source "
    "`concurrency-limits` library implements limits derived from latency in the manner of TCP "
    "congestion control rather than from configured thresholds.",
    """stateDiagram-v2
    [*] --> Closed
    Closed --> Open : error rate over threshold
    Open --> HalfOpen : cool-down elapsed
    HalfOpen --> Closed : N consecutive successes
    HalfOpen --> Open : one probe fails
    note right of HalfOpen
        one probe at a time
        a burst of probes re-kills a recovering service
    end note
    note right of Closed
        thresholds on absolute counts never fire
        during a low-traffic outage
    end note"""),

"Bulkhead": P(
    "Partition resources so that exhaustion in one part cannot consume the whole.",
    "Separate thread pools or connection pools per dependency, Kubernetes resource limits per "
    "namespace, per-tenant shards, AWS shuffle sharding.",
    "Assign each workload, dependency or tenant its own bounded slice of the constrained resource "
    "— threads, connections, memory, queue slots — and refuse work when that slice is full rather "
    "than borrowing from another.",
    "One slow dependency will otherwise absorb every thread in a shared pool, and a service with "
    "no free threads cannot serve any of its endpoints, including the nine that had nothing to do "
    "with the failing one.",
    "A failure is contained to the partition it started in. The other endpoints keep working, so a "
    "dependency outage becomes a feature outage rather than a service outage. It also makes the "
    "resource limit explicit and visible instead of emergent.",
    "**Static partitioning wastes capacity by construction** — each bulkhead must be sized for its "
    "own peak, so the fleet is sized for the sum of the peaks rather than the peak of the sum, and "
    "the unused headroom in one partition cannot help a saturated neighbour. Too many partitions "
    "and each is too small to absorb any burst. Managing per-dependency pool sizes is real "
    "configuration that drifts as traffic changes.",
    "Fault containment bought with capacity that cannot be shared.",
    "**The resource that actually gets exhausted is usually not the one people partition.** "
    "Separate thread pools per dependency is the textbook answer and it does nothing if all pools "
    "share one HTTP connection pool, one event loop, one database connection pool or one file "
    "descriptor limit — so the first task is to find the *single* resource whose exhaustion is "
    "fatal, and in most services there is exactly one. Partitioning anything else is theatre. The "
    "advanced form is worth knowing because the arithmetic is startling: AWS's shuffle sharding "
    "assigns each tenant a random *combination* of shards rather than a single shard, so with "
    "eight shards and two per tenant there are 28 distinct combinations, and a tenant that "
    "poisons both of its shards affects only the small fraction of other tenants that happen to "
    "share both. You approach per-tenant isolation without paying per-tenant cost, and the whole "
    "mechanism is combinations. The last thing they do is decide what a full bulkhead means: "
    "rejecting immediately is almost always better than queueing, because a queue in front of a "
    "full bulkhead reintroduces the unbounded wait the bulkhead existed to prevent.",
    "Michael Nygard named the pattern in *Release It!*, after a ship's watertight compartments. "
    "Netflix's Hystrix implemented it literally, with a separate thread pool per dependency and a "
    "documented per-call overhead they judged worth paying. AWS's Builders' Library article on "
    "workload isolation using shuffle sharding, by Colm MacCárthaigh, is the best public treatment "
    "of the combinatorial version and includes the arithmetic for choosing shard counts.",
    """flowchart TD
    A["One shared pool of 100 threads"] --> B["Dependency X hangs"]
    B --> C["All 100 threads blocked<br/>every endpoint down"]
    D["Per-dependency pools"] --> E["X hangs, its 20 threads blocked"]
    E --> F["Other endpoints unaffected<br/>if they share nothing else"]
    F --> G["Check: same connection pool<br/>same event loop, same fd limit"]
    style C fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style G fill:#2a2317,stroke:#d9a441,color:#e4ecea"""),

"Timeout": P(
    "Give up on an operation after a bounded wait, converting 'slow' into 'failed'.",
    "Every HTTP and RPC client, database drivers, gRPC deadlines, Go's `context`, Envoy route "
    "timeouts.",
    "Set an upper bound on how long a call may take. On expiry, abandon it, release the resources "
    "it held, and return an error — ideally cancelling the work at the far end as well.",
    "'Slow' is not a failure mode any system can handle: it consumes a thread, a connection and a "
    "user's patience indefinitely. Only 'failed' can be retried, fallen back from, or reported. "
    "The timeout is what makes every other resilience pattern possible.",
    "Bounded resource consumption per request, which is what keeps a caller alive when a "
    "dependency stalls. Turns an unbounded unknown into a definite, handleable outcome. Makes "
    "latency SLOs enforceable rather than aspirational.",
    "Too short and you fail healthy-but-slow requests, then retry them, adding load and possibly "
    "duplicating work. Too long and you hold resources through the entire outage. A timeout can "
    "turn a success into a failure — the work completed at the far end and you did not wait to "
    "hear it — which combined with retries turns one operation into several. And a timeout without "
    "cancellation leaves the far end still burning CPU on a request nobody will read.",
    "Bounded resource use bought with the possibility of failing work that would have succeeded.",
    "**The default is very often infinity, and that is the actual bug.** Java's "
    "`HttpURLConnection`, Python's `requests`, and a long list of database drivers ship with no "
    "read timeout at all, so 'we have timeouts' is a claim that must be verified per library, per "
    "client and per pool rather than assumed — and the verification usually finds one that was "
    "missed. Second, the number: a timeout is only meaningful relative to the caller's, so the "
    "chain must be budgeted top-down. If the browser gives up at 10 seconds, an inner service with "
    "a 30-second timeout is holding a thread for work no one will ever read. gRPC gets this right "
    "with **deadline propagation** — the deadline travels with the call and each hop passes on the "
    "*remaining* time — whereas an ordinary per-hop timeout lets every layer restart the clock, so "
    "a four-hop chain of 10-second timeouts can legitimately take 40 seconds. Third, and the part "
    "that separates a real implementation: expiry must **cancel**, not merely stop waiting. Go's "
    "context and gRPC cancellation exist for this, and without them a service under load keeps "
    "spending its scarcest resource on requests whose callers are already gone — which is exactly "
    "how a latency problem becomes an outage.",
    "The AWS Builders' Library article on timeouts, retries and backoff with jitter is the "
    "practical reference, and its central point is that timeout values should be derived from "
    "measured latency distributions rather than chosen as round numbers. gRPC's deadline "
    "propagation is the clearest widely deployed implementation of budgeting across hops, and its "
    "documentation is explicit that a deadline is absolute and shared rather than per-hop — a "
    "design decision made because per-hop timeouts do not compose.",
    """flowchart LR
    B["Browser budget 10s"] -->|"remaining 9.5s"| G["Gateway"]
    G -->|"remaining 9.0s"| S1["Service A"]
    S1 -->|"remaining 8.2s"| S2["Service B"]
    S2 -->|"remaining 7.5s"| DB["Database"]
    X["Per-hop 10s timeouts instead"] --> Y["Each hop restarts the clock<br/>total can reach 40s<br/>caller left at 10s"]
    style Y fill:#2b1c17,stroke:#e0705a,color:#e4ecea"""),

"Rate Limiting": P(
    "Cap how much of a resource any one caller may consume in a given period.",
    "Stripe, GitHub and Twitter's public APIs, Cloudflare and other edge platforms, Envoy's rate "
    "limit service, Nginx's `limit_req`.",
    "Track usage per key — API key, user, IP, tenant — against an algorithm: token bucket for a "
    "sustained rate plus a burst allowance, sliding window for smoother accounting, GCRA for exact "
    "pacing. Over the limit, return 429 with a `Retry-After`.",
    "One caller's runaway loop should not degrade everyone else's service, and capacity is finite "
    "and shared. Without a cap, the least well-behaved client determines everyone's experience.",
    "Fair sharing of finite capacity. Protection against both accidental and deliberate abuse. It "
    "makes capacity planning tractable, because the worst case per caller is now a known number.",
    "A shared counter is a hot key and a new dependency on the request path, and its availability "
    "becomes yours. Limiting by API key punishes the wrong party when a customer's traffic arrives "
    "through a proxy or an aggregator. Returning 429 without `Retry-After` produces a retry storm "
    "you caused. And a rate limit does nothing about the case where every caller is individually "
    "well-behaved and the aggregate still exceeds capacity.",
    "Fair sharing bought with a stateful counter on the request path and a limit that is a "
    "published contract.",
    "A rate limit is a **product decision wearing infrastructure clothing** — the number is part of "
    "your API contract, so it must be documented, returned in response headers, and never lowered "
    "silently. Teams that treat it as a config value discover this when they break an integration "
    "partner. Mechanically, the choice of algorithm matters more than people expect: a fixed "
    "window lets a caller send two full windows' worth of traffic across a boundary — 100 requests "
    "at 11:59:59 and 100 more at 12:00:00 — so a limit of 100 per minute permits 200 in one "
    "second, which is exactly the burst you were protecting against. Token bucket avoids that and "
    "additionally expresses burst and sustained rate as two separate numbers, which is what "
    "callers actually need. The distributed version is where most implementations quietly break: "
    "dividing the global limit by the node count is wrong the moment the load balancer is uneven "
    "or a node is deployed, so the counter has to be shared — and then its latency and its "
    "availability are on every request, which is why serious implementations do approximate local "
    "accounting with periodic reconciliation rather than a synchronous read. Finally, they know "
    "what it does *not* do: it protects you from one caller, not from all of them, which is a "
    "different pattern.",
    "Stripe's engineering post *Scaling your API with rate limiters* (2017) is unusually candid: "
    "they describe running four distinct limiters simultaneously — a request rate limiter, a "
    "concurrent request limiter, and two load shedders — and the reason the article is worth "
    "reading is that it draws the line between limiting a caller and shedding load, which most "
    "treatments blur. Cloudflare has published on approximating sliding windows cheaply at edge "
    "scale, which is the standard answer to the shared-counter cost.",
    """flowchart TD
    A["Limit: 100 per minute, fixed window"] --> B["100 requests at 11:59:59"]
    A --> C["100 requests at 12:00:00"]
    B --> D["200 requests in one second<br/>limit technically respected"]
    E["Token bucket instead"] --> F["Sustained rate and burst<br/>are two separate numbers"]
    style D fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style F fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),

"Load Shedding": P(
    "When demand exceeds capacity, deliberately drop low-value work so that high-value work still "
    "succeeds.",
    "Google's RPC stack with per-request criticality, Netflix's prioritised shedding on the "
    "playback path, Envoy's overload manager, admission control in most large-scale serving "
    "systems.",
    "Measure a saturation signal — queue depth, concurrency, request latency against a target — "
    "and when it crosses a threshold, reject the lowest-priority requests immediately and cheaply, "
    "before they consume the resource under pressure.",
    "A system driven past capacity does not degrade gracefully on its own; it collapses. Queues "
    "grow, latency rises past every client's timeout, and eventually every request is worked on "
    "and then discarded by a caller who already gave up — the system does 100 percent of the work "
    "and delivers 0 percent of the value.",
    "Goodput is preserved at saturation instead of collapsing. The most important traffic — "
    "checkout, playback, health checks — keeps working while batch, prefetch and analytics do not. "
    "Recovery is possible, because the system is never driven into the collapsed regime it cannot "
    "climb out of.",
    "You are deliberately failing requests you could individually have served, and someone will "
    "ask why. Criticality labels are set by callers, and callers systematically over-declare their "
    "own importance, so the labels need policing or they inflate until everything is critical. A "
    "shedder tuned on CPU will not fire for memory or connection exhaustion. And shedding is "
    "invisible to the client except as an error, so it can be mistaken for an outage.",
    "Preserved goodput under overload bought with deliberate, visible failure of work you chose to "
    "sacrifice.",
    "**Load shedding is neither rate limiting nor backpressure, and conflating the three is the "
    "most common misunderstanding in this family.** Rate limiting caps a *caller* and is about "
    "fairness. Backpressure tells a *producer* to slow down and requires a producer that can be "
    "told. Shedding throws away low-value work to protect high-value work when total demand "
    "exceeds capacity — regardless of who sent it, and with nobody to push back on. You can need "
    "all three at once. The part that separates a real implementation from a CPU threshold and a "
    "prayer is that **the value judgement must exist before the incident**. Google's RPC "
    "infrastructure attaches a criticality to every request — CRITICAL_PLUS, CRITICAL, "
    "SHEDDABLE_PLUS, SHEDDABLE — set by the caller and propagated across every hop, so a server "
    "under pressure can drop a prefetch and a backfill while a checkout and a health check pass. "
    "Without those labels the only available policy is random shedding, which discards 10 percent "
    "of checkouts to save 10 percent of prefetches. Two further disciplines: shed at the **edge**, "
    "before the request has consumed the resource you are protecting — shedding after the database "
    "query has been issued protects nothing — and make shedding *cheaper than serving*, or the "
    "shedder becomes the bottleneck and you have built an expensive way to fail.",
    "Chapter 21 of Google's *Site Reliability Engineering* book, on handling overload, documents "
    "the criticality scheme and the reasoning behind propagating it across the call graph rather "
    "than deciding locally. Netflix has published on service-level prioritised load shedding, "
    "separating playback-critical requests from everything else so that the streaming path is the "
    "last thing to degrade. Stripe's rate limiter post makes the complementary point from the "
    "other side, describing their load shedders as distinct components from their rate limiters.",
    """flowchart TD
    O["Demand exceeds capacity"] --> D{"Criticality on the request"}
    D -->|"CRITICAL_PLUS, checkout"| S1["Served"]
    D -->|"CRITICAL, health check"| S2["Served"]
    D -->|"SHEDDABLE_PLUS, recommendations"| S3["Shed"]
    D -->|"SHEDDABLE, batch backfill"| S4["Shed first"]
    N["No criticality labels"] --> R["Random shedding<br/>drops checkouts to save prefetches"]
    style S1 fill:#1c6853,stroke:#4fc3a1,color:#e4ecea
    style R fill:#2b1c17,stroke:#e0705a,color:#e4ecea"""),

"Backpressure": P(
    "Signal a producer to slow down rather than buffering work it is generating faster than you "
    "can consume it.",
    "TCP's receive window, Reactive Streams and its implementations, Kafka consumer pause and "
    "resume, Akka Streams, Netflix's concurrency-limits library, gRPC flow control.",
    "The consumer advertises how much it can accept. The producer may not exceed it. Every buffer "
    "in the chain is bounded, and a full buffer propagates the signal upstream rather than growing.",
    "A producer faster than its consumer will exhaust memory, and inserting a queue only changes "
    "when. The mismatch has to be resolved somewhere, and resolving it at the source is the only "
    "place where the producer can do something useful about it.",
    "Memory use is bounded by design rather than by luck. Latency stays bounded, because the queue "
    "cannot grow without limit. The system degrades in throughput — which is recoverable — instead "
    "of falling over.",
    "The slowest consumer sets the pace for the entire pipeline, which is correct and also means "
    "one bad consumer throttles everyone. It cannot be expressed across a fire-and-forget "
    "boundary: you cannot push back on a UDP sender, an inbound webhook or a user's browser. And "
    "it relocates the problem rather than solving it — the producer now has work it cannot emit, "
    "and it may have nowhere to put it either.",
    "Bounded memory and latency bought with throughput limited by your slowest consumer.",
    "**Backpressure only works if the signal reaches the source.** A queue inserted to 'absorb the "
    "load' is the opposite of backpressure: it converts a fast, honest rejection into an unbounded "
    "latency increase, and by the time the consumer catches up every message in the buffer is "
    "stale, every caller has already timed out, and most have retried — so the work you carefully "
    "preserved is worthless and has been duplicated. The rule that follows is that every buffer is "
    "bounded and the full-buffer behaviour is chosen explicitly: block, drop oldest, drop newest, "
    "or reject. Defaulting to unbounded is a decision too, and it is the one that pages you. The "
    "second thing they do is derive the in-flight limit rather than configure it. **Little's Law "
    "gives it directly** — concurrency equals throughput multiplied by latency — which means the "
    "correct limit moves whenever latency moves, so any static thread-pool size is right at one "
    "traffic level and wrong at every other. Netflix's concurrency-limits infers the limit "
    "continuously by watching latency rise, borrowing the approach from TCP congestion control, "
    "which is why a system built on it adapts to a slow dependency instead of queueing against it.",
    "TCP's sliding receive window is the backpressure mechanism every system already depends on, "
    "and it is worth studying because it is end-to-end. The Reactive Streams specification, later "
    "absorbed into Java's `Flow` API, standardised demand-driven backpressure across JVM "
    "libraries. Netflix's *Performance Under Load* (2018) and the accompanying `concurrency-limits` "
    "library are the clearest public argument for adaptive rather than configured limits, "
    "explicitly modelled on TCP Vegas-style latency-gradient detection.",
    """flowchart LR
    P1["Producer"] -->|"no signal"| Q1["Unbounded queue"]
    Q1 --> C1["Slow consumer"]
    Q1 -.-> X["Latency grows without bound<br/>every item stale on arrival<br/>callers already timed out and retried"]
    P2["Producer"] -->|"demand signal"| Q2["Bounded buffer"]
    Q2 --> C2["Slow consumer"]
    Q2 -.->|"full"| P2
    style X fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style Q2 fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),

"Graceful Degradation": P(
    "Serve a reduced but useful version of the service when a dependency or capacity is missing.",
    "Netflix falling back to unpersonalised rows, search engines serving cached results, "
    "e-commerce sites hiding recommendations while keeping checkout, maps serving cached tiles "
    "offline.",
    "Identify which features are essential and which are enhancements. When an enhancement's "
    "dependency fails, omit it or substitute a static, cached or approximate version, and keep the "
    "core path serving.",
    "Total failure is almost never necessary. A homepage without personalised recommendations is "
    "worth enormously more than an error page, and the components that produce the recommendations "
    "are usually far less reliable than the ones that serve the page.",
    "The blast radius of any single dependency shrinks to the feature it powers. Availability of "
    "the core journey stops being the product of every dependency's availability. It buys time — "
    "an incident becomes degraded service rather than an outage, which changes the response clock "
    "entirely.",
    "You now maintain two behaviours for every degradable feature, and the second one has no users "
    "in normal times, so it rots quietly. Deciding what 'reduced' means is a product conversation "
    "engineering cannot have alone. And **silent degradation can be worse than failure** — a user "
    "shown stale prices or an incomplete list has no way to know, and will act on it.",
    "Partial availability bought with a second code path that is rarely exercised and easily wrong.",
    "**Degradation has to be a designed mode with its own capacity, not an improvised fallback**, "
    "and the test is simple: what does the degraded path call? The classic failure is a fallback "
    "that depends on something — a cache that misses through to the database, a personalised feed "
    "that falls back to a 'popular items' service — so at the exact moment the primary dependency "
    "fails, the fallback inherits the entire load it was supposed to protect against and dies too, "
    "converting a partial outage into a total one with extra steps. Amazon's framing for the "
    "correct version is **static stability**: the degraded mode uses only resources it already "
    "has, pre-provisioned, and does not depend on a control plane to acquire anything — because "
    "the control plane is probably also having a bad day, and a recovery that requires launching "
    "instances during a regional event will not complete. The corollary that almost nobody "
    "implements: the fallback path must be exercised **in normal traffic**, with a small percentage "
    "of requests routed through it every day, because a path that runs only during incidents has "
    "been tested only during incidents. The last discipline is honesty in the UI — mark degraded "
    "results as degraded, because silently serving stale data destroys more trust than an error "
    "does.",
    "The AWS Builders' Library article *Static stability using Availability Zones*, by Becky Weiss "
    "and Mike Furr, is the sharpest statement of the pre-provisioning principle, using the example "
    "of EC2's data plane continuing to work correctly while the control plane is impaired. "
    "Netflix's fallback design is the best-known consumer example: when the personalisation "
    "service is unavailable the homepage renders unpersonalised rows rather than an error, a "
    "behaviour built into their Hystrix command fallbacks from the start.",
    """flowchart TD
    P["Personalisation service fails"] --> F{"What does the fallback call"}
    F -->|"popular-items service"| A["Fallback takes the full load<br/>and fails too"]
    F -->|"pre-computed static list<br/>already in memory"| B["Degraded but stable"]
    B --> C["Route 1 percent of normal traffic here<br/>or it will be broken when needed"]
    style A fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style B fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),

"Hedged Request": P(
    "Send a duplicate request after a delay and use whichever answer comes back first.",
    "Google's BigTable read path, gRPC's hedging policy, distributed storage read paths, DNS "
    "resolvers querying multiple servers.",
    "Issue the request. If no response has arrived by the p95 of the normal latency distribution, "
    "send an identical request to a different replica. Take the first response and cancel the "
    "other.",
    "Tail latency in a large fleet is dominated by transient, uncorrelated slowness — a garbage "
    "collection pause, a background compaction, a noisy neighbour, a queue that happened to be "
    "deep. The same request to a different replica will usually not hit the same hiccup.",
    "Dramatic reduction in high-percentile latency for a small increase in load, because a hedge "
    "sent at p95 by definition applies to only 5 percent of requests. It needs no change to the "
    "server and no prediction of which replica will be slow.",
    "Extra load, always, and load applied disproportionately to a system that may already be "
    "struggling. It only works for idempotent operations, so it is a read pattern. It masks the "
    "underlying cause, so the real source of the tail never gets investigated. And a system that "
    "hedges while genuinely overloaded amplifies exactly the condition producing the slowness.",
    "Tail latency bought with a few percent of extra load and idempotency as a hard requirement.",
    "The discipline is entirely in the **timing**: hedge at the p95 of the observed distribution, "
    "not immediately. A hedge at t equals zero doubles your load for no tail benefit, whereas one "
    "sent after p95 costs at most 5 percent extra requests by construction — the delay *is* the "
    "cost control. The figure from *The Tail at Scale* is what makes the pattern worth the "
    "trouble: hedging BigTable reads after a 10 millisecond delay cut the 99.9th percentile from "
    "1,800 milliseconds to 74 milliseconds for roughly 2 percent additional requests. Three things "
    "most write-ups omit. Hedges must be **cancelled** when the first answer arrives, or you have "
    "simply added permanent extra load and the doubling shows up in the callee's own tail — a "
    "hedging client that does not cancel is a load generator. Hedging must be **disabled under "
    "load**, because amplifying requests during overload is the mechanism of a cascading failure, "
    "which is why gRPC pairs hedging with a throttle. And where the callee can cooperate, the "
    "better construction is a **tied request**: send both immediately, each carrying the identity "
    "of the other, and whichever server dequeues it first tells the other to drop — which gets the "
    "tail benefit without waiting for p95 at all.",
    "Dean and Barroso's *The Tail at Scale* (CACM, February 2013) is the source for both hedged "
    "and tied requests and reports the BigTable measurement above. gRPC implements hedging as a "
    "configurable retry policy with a hedging delay and a throttle, and its documentation is "
    "explicit that hedged requests must be safe to execute more than once — the idempotency "
    "requirement is part of the contract, not a caveat.",
    """sequenceDiagram
    participant C as Client
    participant R1 as Replica1
    participant R2 as Replica2
    C->>R1: read k
    Note over C: no answer by p95, 10ms
    C->>R2: hedge, same read
    R2--)C: response at 12ms
    C->>R1: cancel
    Note over C,R1: without the cancel this is permanent extra load
    Note over C,R2: 99.9th percentile 1800ms to 74ms for about 2 percent more requests"""),

"Health Check / Heartbeat": P(
    "Have each instance report whether it can serve, so unhealthy ones are removed before users "
    "find them.",
    "Load balancer target health checks, Kubernetes liveness, readiness and startup probes, "
    "Consul checks, gossip heartbeats in Cassandra.",
    "The instance exposes an endpoint, or emits a periodic heartbeat. A checker polls or listens, "
    "and after a configured number of consecutive failures the instance is removed from rotation "
    "or restarted.",
    "A process can be running and unable to serve — deadlocked, out of connections, stuck on a "
    "wedged thread pool — and TCP will still accept the connection. Without an explicit signal, "
    "the load balancer keeps sending it traffic and every one of those requests fails.",
    "Failed instances leave rotation automatically, usually before users notice. Autoscaling and "
    "orchestration have a signal to act on. Deploys can wait for readiness rather than sending "
    "traffic to a process that has not finished starting.",
    "A check that is too shallow keeps a broken process in rotation — a healthy HTTP thread "
    "answering 200 while the database connection pool is exhausted is the standard example. A "
    "check that is too deep is far worse. The interval and threshold together set both your "
    "detection time and your false-positive rate, and no setting optimises both. At scale the "
    "checks themselves are real traffic.",
    "Automatic failure removal bought with a check that is either too shallow to be useful or deep "
    "enough to be dangerous.",
    "**A deep health check is a fleet-wide outage waiting for a dependency blip.** If every "
    "instance's health endpoint verifies the database, then a database that slows down marks every "
    "instance unhealthy at the same moment, the load balancer removes all of them, and a degraded "
    "dependency becomes a total outage caused by the health check itself. The discipline is a "
    "shallow **liveness** check answering only 'is this process able to serve at all', a "
    "**readiness** check that may consider local resources, and a separate out-of-band deep check "
    "that **pages a human rather than removing capacity** — the deep check's output is a ticket, "
    "not a routing decision. AWS's answer to the residual risk is instructive: load balancers "
    "**fail open**, routing to all targets when every target is unhealthy, on the reasoning that a "
    "fleet reporting 100 percent unhealthy is far more likely to be a broken health check than a "
    "broken fleet. Second, they separate detection from action with a suspicion state, so a single "
    "missed heartbeat during a GC pause does not evict a healthy node — and they know that "
    "tightening the interval to detect faster directly buys more false positives, which in a "
    "large fleet means constant churn.",
    "The AWS Builders' Library article *Implementing health checks*, by Colm MacCárthaigh, is the "
    "definitive public treatment and describes both the correlated-failure hazard of deep checks "
    "and the fail-open behaviour AWS load balancers implement as a mitigation. Kubernetes encodes "
    "the same lesson in its probe design — liveness restarts, readiness removes from service, "
    "startup delays the others — and its documentation warns explicitly against making liveness "
    "probes check dependencies.",
    """flowchart TD
    DB["Database slows down"] --> H["Every instance runs a deep health check"]
    H --> U["All 40 instances report unhealthy simultaneously"]
    U --> LB{"Load balancer"}
    LB -->|"naive"| Z["Removes everything<br/>total outage from a partial fault"]
    LB -->|"fail open"| K["All unhealthy is treated as<br/>a broken check, keeps routing"]
    S["Shallow liveness plus out-of-band deep check<br/>that pages instead of evicting"] --> K
    style Z fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style K fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),

"Cell-Based Architecture": P(
    "Run many complete, independent copies of the stack and assign each customer to one, so a "
    "failure can only affect that copy.",
    "AWS's internal service architecture, Slack's cellular migration, Salesforce pods, DoorDash "
    "and Roblox cells, most large multi-tenant SaaS platforms.",
    "Each cell is a full vertical slice — compute, storage, queues — sized to a maximum tenant "
    "count. A thin router maps a tenant or a request key to its cell. Cells share no state and are "
    "deployed independently.",
    "In a shared fleet, any bug, poison workload, hot partition or bad deploy is global by "
    "default. Redundancy protects against a machine dying; it does nothing about a defect that "
    "every machine shares.",
    "The blast radius of almost anything is one cell. Deployments roll cell by cell, so a bad "
    "release is caught at a fraction of the fleet. Cells give you a natural unit of capacity "
    "planning, testing and per-tenant isolation, and a natural way to offer different tiers.",
    "Capacity is stranded per cell, because headroom in one cannot serve another. Anything "
    "genuinely global — a user directory, a billing ledger, the router itself — does not fit the "
    "model and becomes the shared fate you were trying to eliminate. Cross-cell operations are "
    "distributed transactions. And a tenant that outgrows its cell needs a live data migration, "
    "which you will do repeatedly.",
    "A bounded blast radius bought with stranded capacity and a routing layer that cannot itself "
    "be cellular.",
    "**The whole design lives in the cell router, and the router is the one thing that is not in a "
    "cell.** It therefore has to be radically simpler than everything it routes to — ideally a "
    "thin, cacheable mapping lookup with no business logic, deployed on its own schedule, and "
    "capable of running from stale mapping data if its own store is unavailable. Get that wrong "
    "and you have added enormous complexity while keeping a single point of failure at the front. "
    "Second, and this is the part that separates a real cellular architecture from a diagram: "
    "**cells only bound the blast radius if deployments and configuration changes are also "
    "per-cell.** A config push that reaches every cell simultaneously ignores the boundary "
    "completely, and configuration causes more incidents than code does. In practice most of the "
    "realised benefit shows up as 'we broke one cell and caught it' rather than as surviving "
    "hardware failure. Third, cell size is a genuine trade with no default: small cells bound "
    "damage tightly and multiply operational overhead and stranded capacity, large cells are "
    "efficient and take more customers down — and the honest way to choose is to decide what "
    "fraction of customers you can afford to affect at once, then size backwards from that.",
    "AWS publishes this as a formal pattern in *Reducing the Scope of Impact with Cell-Based "
    "Architecture*, drawn from how their own services are built. Slack's engineering blog "
    "documented their migration to a cellular architecture, motivated specifically by "
    "availability-zone grey failures — partial, hard-to-detect degradation that their health "
    "checks could not distinguish from normal operation — where the practical response was to be "
    "able to drain an entire cell quickly rather than to diagnose the fault.",
    """flowchart TD
    R["Cell router<br/>thin mapping, no business logic"] --> C1["Cell 1<br/>full stack, own data"]
    R --> C2["Cell 2<br/>full stack, own data"]
    R --> C3["Cell 3<br/>full stack, own data"]
    C2 -.->|"bad deploy or poison tenant"| B["Only cell 2 affected"]
    G["Global config push to all cells at once"] -.-> X["Boundary ignored<br/>the cells bought you nothing"]
    style B fill:#1c6853,stroke:#4fc3a1,color:#e4ecea
    style X fill:#2b1c17,stroke:#e0705a,color:#e4ecea"""),

"Chaos Engineering": P(
    "Deliberately inject failure into a running system to find out whether it behaves the way you "
    "believe it does.",
    "Netflix's Chaos Monkey and ChAP, AWS Fault Injection Service, Gremlin, LitmusChaos, game days "
    "at most large operators.",
    "State a hypothesis about a steady-state metric, inject a specific failure — kill an instance, "
    "add latency, drop a dependency — against a small share of production traffic, and compare the "
    "affected population against a control, aborting automatically if the metric moves.",
    "Failover paths that are never exercised do not work. Every organisation has a retry, a "
    "fallback or a replica promotion that has been in the code for two years, has never run, and "
    "will not work the first time it is needed — and the first time it is needed is during an "
    "incident.",
    "Latent failure-handling bugs are found on a Tuesday afternoon with the whole team available, "
    "rather than at 3 a.m. It validates that monitoring actually detects the failures it claims "
    "to. It builds genuine, evidence-based confidence in failover rather than assumed confidence.",
    "An experiment in production can cause a real incident, and eventually one will — the cost is "
    "real and must be budgeted. It requires organisational permission that is hard to obtain and "
    "easy to lose permanently to a single bad experiment. And it only tests failures you thought "
    "of, which makes it weak against exactly the novel, correlated failures that cause the largest "
    "outages.",
    "Verified failure handling bought with deliberate risk to production and the political capital "
    "to take it.",
    "**It is an experiment, and what makes it one is a hypothesis and a steady-state metric "
    "defined before anything is broken.** 'We believe stream starts per second stays within 1 "
    "percent when this instance dies' is chaos engineering; killing a box and watching dashboards "
    "is a fire drill with worse documentation. The disciplines teams skip: the blast radius starts "
    "tiny and *increases* across runs rather than starting at cluster scale; the abort condition "
    "is automatic and must not depend on the human running the test noticing something; and it "
    "runs in **production**, because staging does not have your traffic shape, your data skew, "
    "your cache hit rates or your DNS. Netflix's ChAP implements exactly this — it routes a small "
    "slice of live traffic into a canary and a control cluster, injects the failure into the "
    "canary only, and compares the two statistically rather than eyeballing a graph. The honest "
    "prerequisite, and the reason many programmes fail at the first attempt: **if your "
    "observability cannot already detect the failure you are about to inject, the experiment "
    "teaches you nothing except that something went wrong**, and you should fix the monitoring "
    "first.",
    "Netflix built Chaos Monkey in 2011 after moving to AWS, on the reasoning that instances would "
    "fail anyway and the only way to be sure the system tolerated it was to make it happen "
    "constantly. Basiri et al., *Chaos Engineering* (IEEE Software, 2016), is the paper that "
    "formalised the practice into the hypothesis-and-steady-state method and describes ChAP's "
    "canary-and-control design. Netflix's steady-state metric is stream starts per second, which "
    "is a useful example in itself: it is a business measure, not a systems one.",
    """flowchart TD
    H["Hypothesis: SPS stays within 1 percent"] --> SEL["Route 1 percent of live traffic"]
    SEL --> CAN["Canary cluster, failure injected"]
    SEL --> CTL["Control cluster, untouched"]
    CAN --> CMP{"Compare steady-state metric"}
    CTL --> CMP
    CMP -->|"within bounds"| W["Hypothesis held, widen blast radius"]
    CMP -->|"metric moves"| AB["Automatic abort<br/>not a human noticing"]
    style AB fill:#2a2317,stroke:#d9a441,color:#e4ecea
    style W fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),
}

DEPLOYMENT = {
"Blue-Green": P(
    "Run two identical production environments and switch all traffic from one to the other.",
    "AWS load balancer target group swaps, Kubernetes service selector flips, CodeDeploy's "
    "blue/green mode, classic two-datacentre releases.",
    "Blue serves live traffic. Green is deployed with the new version and verified in place. When "
    "it passes, traffic is switched to green in one operation. Blue is kept warm and idle as the "
    "rollback target.",
    "Deploying in place means a window where the system is half-upgraded and a rollback means "
    "another in-place deploy under pressure. A separate environment makes the release a single, "
    "reversible switch.",
    "Rollback is instant and is the same operation as the release, so it is well tested by "
    "construction. The new version can be smoke-tested in a real production environment before it "
    "takes any user traffic. There is no half-upgraded state.",
    "Two full environments means double the infrastructure during the release, which for a large "
    "fleet is not a rounding error. Long-lived connections and in-flight requests do not switch "
    "cleanly. Any state accumulated in the old environment — sessions, local caches, in-memory "
    "queues — is stranded. And it gives you no gradual exposure at all: the change reaches 100 "
    "percent of users at once.",
    "Instant, well-tested rollback bought with double infrastructure and an all-at-once exposure.",
    "**The database does not flip, and that is what makes this hard.** Two application "
    "environments are the easy half; the schema is shared, so old and new code must both work "
    "against exactly one schema for the whole switching period — which means blue-green does not "
    "remove the need for expand-contract, it *requires* it. The rollback claim is where the "
    "consequence becomes concrete: switching traffic back is instant, but any write green made "
    "under a new schema, a new encoding or a new business rule is still in the database, and blue "
    "may not be able to read it. 'Instant rollback' is therefore only true for stateless change, "
    "and stating that boundary out loud is the difference between a strategy and a slogan. The "
    "second thing they check is what the switch actually is: **DNS is not a flip.** Resolver "
    "caches, client-side pinning and libraries that resolve once at startup mean the old "
    "environment keeps taking real traffic long after the TTL has expired, so the cutover is "
    "gradual, unbounded and unobservable. They switch at the load balancer's target group or the "
    "service selector, where the change is immediate and enumerable. Third, they keep blue warm "
    "and receiving zero traffic through the whole bake period, because an hour of idle fleet costs "
    "far less than a cold start during a rollback.",
    "Martin Fowler's bliki entry on blue-green deployment, crediting Dan North and Jez Humble, is "
    "the canonical write-up, and it is notable that Fowler devotes a substantial section to the "
    "database precisely because it is the part the pattern does not solve. Jez Humble and David "
    "Farley's *Continuous Delivery* develops the same point: the schema must be compatible with "
    "both versions, which pushes you towards backwards-compatible migrations regardless of which "
    "deployment strategy you choose.",
    """flowchart TD
    LB["Load balancer"] -->|"100 percent"| BLUE["Blue, current version"]
    LB -.->|"0 percent, warm"| GREEN["Green, new version"]
    BLUE --> DB["One shared database"]
    GREEN --> DB
    DB --> N["Schema must serve both versions<br/>expand-contract is a prerequisite"]
    N --> RB["Rollback is instant for code<br/>and impossible for writes green already made"]
    style DB fill:#2a2317,stroke:#d9a441,color:#e4ecea
    style RB fill:#2b1c17,stroke:#e0705a,color:#e4ecea"""),

"Canary": P(
    "Expose a new version to a small fraction of traffic and measure it before going further.",
    "Spinnaker with Kayenta, Argo Rollouts, Istio and Envoy weighted routing, Facebook's staged "
    "rollouts, every large web platform.",
    "Deploy the new version alongside the old and route a small percentage of traffic to it. "
    "Compare its error rate, latency and business metrics against a baseline. Promote in stages, "
    "or roll back automatically.",
    "Testing cannot reproduce production's traffic mix, data skew, client diversity or scale, so "
    "some defects only appear under real load. Exposing all users to an unverified version means "
    "every defect is a full-scale incident.",
    "Bad releases affect a small, bounded share of users. Rollback happens before most people "
    "notice. It provides real evidence about a release rather than a green test suite, and the "
    "evidence includes business metrics a test suite cannot check.",
    "It catches only what it can measure in the observation window, so slow memory leaks, data "
    "corruption and month-end logic ship straight through. Two versions run simultaneously, so "
    "both must tolerate the same data and the same peers. Sticky sessions and caching can make the "
    "canary population systematically unusual. And the whole process is slow, which is a real cost "
    "when you are shipping a fix.",
    "Bounded release risk bought with a slower release and a verdict limited to what you measured.",
    "**A canary is a statistical test, and most canaries are not powered to detect anything.** If "
    "the new version breaks 1 request in 500 and your canary receives 200 requests an hour, you "
    "will observe zero failures and promote with confidence — the canary produced a green result "
    "because it produced no information. The number to work out before choosing a percentage is "
    "how many requests you need to detect the error rate you actually care about, and the honest "
    "answer is often that 1 percent of your traffic needs several hours, or that at your volume a "
    "canary is not a viable safety mechanism and you need a different control. Second, and this is "
    "the mistake even mature teams make: **compare the canary against a control deployed at the "
    "same time**, not against the existing fleet. A freshly started process has a cold cache, an "
    "unwarmed JIT and empty connection pools, so measured against a fleet that has been warm for a "
    "week every canary looks worse and every team learns to ignore the signal. Netflix's Kayenta "
    "runs a canary and a baseline as a matched pair started together, taking equal traffic, and "
    "compares them with a Mann-Whitney U test rather than a threshold — which is what turns "
    "canary analysis from an opinion into a result. Third, they gate on user-facing and business "
    "metrics, not CPU: a release that is 4 percent slower and 30 percent less likely to convert "
    "will pass every infrastructure check you have.",
    "Netflix and Google jointly built Kayenta, the automated canary analysis service in Spinnaker, "
    "and its design is the clearest public statement of the baseline-pair and statistical-test "
    "approach. Savor et al., *Continuous Deployment at Facebook and OANDA* (ICSE 2016), documents "
    "the staged-exposure variant at scale — internal employees first, then progressively larger "
    "slices of production — and reports that deployment size, not deployment frequency, correlates "
    "with incident rate.",
    """flowchart TD
    D["Deploy"] --> C["Canary, new version<br/>started now"]
    D --> B["Baseline, old version<br/>started now, same traffic"]
    F["Existing warm fleet"] -.->|"wrong comparison<br/>cold cache makes canary look bad"| C
    C --> T{"Statistical comparison<br/>canary against baseline"}
    B --> T
    T -->|"enough requests to be powered"| P["Promote or roll back"]
    T -->|"200 requests an hour"| N["Green result, zero information"]
    style N fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style P fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),

"Rolling Update": P(
    "Replace instances of the old version with the new one a few at a time, keeping the service up "
    "throughout.",
    "Kubernetes Deployments, AWS Auto Scaling instance refresh, Nomad, essentially every "
    "orchestrator's default strategy.",
    "Take a small batch out of rotation, replace it, wait for the new instances to pass readiness, "
    "then move to the next batch. `maxSurge` and `maxUnavailable` control how much extra capacity "
    "is allowed and how much may be missing at once.",
    "Replacing everything at once is an outage, and running two full environments is expensive. A "
    "rolling replacement gets continuous availability from the capacity you already have.",
    "No downtime and no extra environment. It is the orchestrator default, so it needs no "
    "additional tooling. Capacity is maintained throughout if surge is allowed.",
    "Both versions serve simultaneously for the whole rollout, so every change must be compatible "
    "with the version it is replacing — including its messages, its cache entries and its database "
    "reads. **Rollback is another rolling update, so it takes as long as the deploy did**, which "
    "is precisely the wrong property during an incident. There is no verification gate: a rolling "
    "update will happily distribute a broken version across the entire fleet, one batch at a time, "
    "unless the readiness probe happens to fail on the breakage. And long-lived connections do not "
    "drain by themselves.",
    "Zero-downtime deploys from existing capacity bought with mixed versions and a slow rollback.",
    "The failure that catches almost everyone is the one the orchestrator cannot fix for you: "
    "**pod termination and endpoint removal are concurrent, not ordered.** When a pod is deleted "
    "the kubelet sends SIGTERM at the same time the endpoints controller starts removing it from "
    "the service, and kube-proxy, the ingress and any client-side load balancer each update their "
    "routing some milliseconds to seconds later — so a well-behaved process that exits promptly on "
    "SIGTERM will drop requests that were routed to it *after* it began shutting down. The fix is "
    "counter-intuitive and looks like a hack: a `preStop` hook that simply sleeps for a few "
    "seconds, doing nothing except keeping the process alive and serving while the removal "
    "propagates, followed by a graceful shutdown that drains in-flight work within the termination "
    "grace period. Second, `maxUnavailable: 0` with `maxSurge: 1` is the safe setting and is not "
    "free — it requires headroom for an extra pod, and on a full cluster the rollout simply "
    "stalls, which is a far better failure than the alternative and should be alerted on. Third, "
    "they never treat a rolling update as a *strategy* on its own, because it has no verification "
    "step; it is the mechanism underneath a canary or a progressive rollout, and used alone it is "
    "an efficient way to break the whole fleet slowly.",
    "The behaviour is documented in Kubernetes' own pod termination lifecycle, which states that "
    "endpoint removal and the SIGTERM to the container happen concurrently and that there is no "
    "ordering guarantee between them. The `preStop` sleep is the widely adopted community "
    "workaround and appears in production guidance from most managed Kubernetes providers, which "
    "is a useful signal in itself: when the standard fix for a platform behaviour is a sleep, the "
    "behaviour is a sharp edge everyone hits.",
    """sequenceDiagram
    participant K as Kubelet
    participant E as EndpointsController
    participant PX as KubeProxy
    participant P as Pod
    K->>P: SIGTERM
    E->>PX: remove endpoint
    Note over PX: rules updated some time later
    PX->>P: request still routed here
    Note over P: process already exiting, request dropped
    Note over K,P: preStop sleep keeps it serving until removal propagates"""),

"Feature Flag": P(
    "Separate deploying code from releasing behaviour, by putting the new path behind a runtime "
    "switch.",
    "LaunchDarkly, Flagsmith, Unleash, Facebook's Gatekeeper, and a homegrown config table in "
    "almost every large codebase.",
    "The new behaviour ships disabled. A flag service or config store decides at runtime, per "
    "request and often per user, which path executes. Enabling is a configuration change, not a "
    "deploy.",
    "Coupling release to deploy means every release is a full deploy cycle, rollback is a deploy, "
    "and long-running work must live on a branch until it is finished — which is where merge pain, "
    "integration risk and 'big bang' releases come from.",
    "Release becomes instant and reversible without a build. Trunk-based development becomes "
    "possible because unfinished work can be merged safely. Gradual rollout, A/B testing and "
    "per-tenant enablement all fall out of the same mechanism. A bad feature is turned off in "
    "seconds rather than rolled back in minutes.",
    "**Combinatorial explosion**: n flags in one code path is 2^n combinations and you test maybe "
    "three of them. Flags read at different moments within a single request give an inconsistent "
    "experience to one user. The flag service is now a dependency of every feature you have, on "
    "the request path. And flag state is configuration that changes production behaviour with no "
    "deploy, which means it needs deploy-grade review, audit and rollback — and usually does not "
    "get any of them.",
    "Decoupled release bought with a permanent combinatorial testing debt and an untracked "
    "configuration surface.",
    "**Flags are inventory, and inventory has a carrying cost.** Every flag left in the codebase "
    "is a permanent, untested branch that somebody will eventually toggle, and the canonical "
    "disaster is exactly that: Knight Capital lost roughly 440 million dollars in 45 minutes in "
    "2012 because a flag that had controlled a retired feature was repurposed for new behaviour "
    "while the old code sat unremoved on the servers, and a deploy that reached seven of eight "
    "servers left the eighth running dead code under a flag that now meant something else. So: "
    "every flag gets an owner and an expiry date at creation, release flags are deleted within "
    "days of reaching 100 percent, a flag value is never reused for a new meaning, and the total "
    "flag count is a tracked metric that is expected to go down. The distinction that makes the "
    "cleanup actually happen is Pete Hodgson's taxonomy: **release toggles live for days, "
    "experiment toggles for weeks, ops and permission toggles for years** — treating all four the "
    "same is why nobody knows which ones are safe to remove. Finally, the flag system is on the "
    "request path of everything, so it must evaluate locally against a cached ruleset, fail to a "
    "known default, and never block a request on a network call to the flag vendor.",
    "Flickr's 2009 post *Flipping Out* is the original public description of the practice, "
    "including dark launches, and remains the clearest short statement of why it works. Pete "
    "Hodgson's *Feature Toggles* on martinfowler.com (2017) supplies the taxonomy and the "
    "lifecycle argument. Knight Capital's collapse is documented in the SEC's administrative "
    "proceeding against the firm, and the flag-reuse detail is the part every engineer should "
    "know: the technical fault was not the flag mechanism, it was dead code that was never removed.",
    """flowchart TD
    C["Flag created"] --> R["Rolled out to 100 percent"]
    R --> D{"Deleted within days"}
    D -->|"yes"| G["Code path collapses to one branch"]
    D -->|"no"| P["Permanent untested branch<br/>old code still deployed"]
    P --> K["Someone reuses the flag<br/>for a different meaning"]
    K --> X["Dead code executes<br/>Knight Capital, 2012"]
    style G fill:#1c6853,stroke:#4fc3a1,color:#e4ecea
    style X fill:#2b1c17,stroke:#e0705a,color:#e4ecea"""),

"Strangler Fig": P(
    "Replace a legacy system incrementally by routing individual capabilities to a new "
    "implementation until nothing is left of the old one.",
    "Monolith-to-services migrations, mainframe replacement programmes, platform re-platforming at "
    "essentially every company that has survived long enough to need one.",
    "Put an interception layer in front of the legacy system — an HTTP facade, a proxy, an event "
    "stream. Implement one capability in the new system, route that capability's traffic to it, "
    "verify, repeat. Decommission the old system when the last route has moved.",
    "A rewrite-and-switch replacement of a system that is still being changed is a bet that pays "
    "out only at the very end, and the end recedes. Meanwhile the legacy system keeps evolving, so "
    "the replacement is aiming at a moving target.",
    "Value is delivered continuously rather than at a distant cutover. Risk is spread across many "
    "small, individually reversible steps. The legacy system keeps running and keeps earning "
    "throughout. Each increment can be rolled back independently.",
    "Two systems run simultaneously for the entire duration, which is double the operational "
    "surface and double the on-call. The interception layer is new infrastructure that must be at "
    "least as reliable as both systems behind it. Data is the real difficulty: one side must own "
    "each entity, or you have built bidirectional synchronisation, which is a distributed "
    "agreement problem you did not sign up for.",
    "Incremental, reversible replacement bought with running two systems and a router for the "
    "whole journey.",
    "The interception seam is the design decision, and it has to be chosen deliberately — an HTTP "
    "facade, a database-level split, an event stream — because if the seam is wrong every "
    "increment becomes a special case and the migration stalls in negotiation. But the thing that "
    "actually kills these programmes is not technical: **they do not finish.** The straightforward "
    "80 percent moves within a year, the remaining 20 percent is the part with no tests, no living "
    "owner and the strangest business rules, funding and attention move to the next initiative, "
    "and the organisation is left permanently operating two systems plus a routing layer — a "
    "strictly worse position than either endpoint, and one that is now very hard to argue for "
    "money to fix. So the top 1 percent define 'done' as **the decommissioning of the old system**, "
    "not as the launch of the new one; they put a date on it, they track the percentage of traffic "
    "still hitting legacy as the programme's headline metric, and they treat the routing layer as "
    "scaffolding with a deletion ticket already filed. The second discipline is refusing to carry "
    "the old model across: a strangler that reimplements the legacy schema in a new language has "
    "spent the budget and bought nothing.",
    "Martin Fowler named the pattern in 2004 after strangler figs he saw in Queensland, and "
    "renamed it *Strangler Fig Application* in 2019; his write-up is the standard reference and is "
    "explicit that the incremental approach's value is risk reduction rather than speed. The "
    "failure to finish is not attributable to a single named company in the public record — it is "
    "a widely reported pattern across large migration programmes, and treating decommissioning as "
    "the completion criterion is the standard advice that emerged from it.",
    """flowchart LR
    C["Clients"] --> F["Interception facade"]
    F -->|"orders, moved"| N["New system"]
    F -->|"reporting, moved"| N
    F -->|"the difficult 20 percent<br/>no tests, no owner"| L["Legacy system"]
    L -.-> D["Never decommissioned<br/>two systems plus a router, permanently"]
    N -.-> M["Done means legacy is switched off<br/>not that the new system launched"]
    style D fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style M fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),

"Expand-Contract": P(
    "Change a schema or an interface without downtime by adding the new shape, migrating, and only "
    "then removing the old one.",
    "Online database migrations at every company that cannot take downtime, API versioning, "
    "protobuf field evolution. Also known as parallel change.",
    "**Expand**: add the new column, field or endpoint and start writing both old and new. "
    "**Migrate**: backfill historical rows and move readers to the new shape. **Contract**: stop "
    "writing the old shape, verify nothing reads it, and drop it. Each phase is a separate deploy.",
    "A schema change and a code change cannot be simultaneous in a system with more than one "
    "instance, because there is always a moment when both versions are running against one "
    "database. Any change that is not backwards compatible therefore requires downtime — or this "
    "pattern.",
    "Zero downtime for structural change. Every phase is independently reversible, which is not "
    "true of a single destructive migration. It composes with blue-green, canary and rolling "
    "updates, all of which require exactly this property.",
    "Three or more deploys for one logical change, spread over days or weeks, which is a real "
    "drag on delivery. During the expand phase the system carries both shapes, so writes are "
    "duplicated and the code has a branch on every path that touches the field. Backfilling a "
    "large table is a long-running job with its own load profile. And the contract phase is "
    "routinely never done, leaving permanent dual-write code and a dead column.",
    "Zero-downtime schema change bought with three deploys and a period of duplicated writes.",
    "Three deploys is the minimum, and **the step people skip is verifying that nothing still "
    "reads the old shape before contracting**. The correct move is to instrument the old read path "
    "with a counter and wait until it reads zero for longer than the lifetime of your "
    "longest-lived client — which for a mobile app is months, not days. Dropping the column that "
    "'nothing uses' is what takes down a nightly job three weeks later, and it is entirely "
    "preventable with a counter. Stripe's published migration playbook adds the step that pays for "
    "itself: a **dual-read comparison phase**, where the new path is the source of truth and the "
    "old path is read alongside it purely to log mismatches. That surfaces the backfill's bugs "
    "while the old data still exists to fix them from, which is the only window in which they are "
    "cheap. Second, on a large table the DDL itself is the outage risk — locking behaviour for "
    "`ALTER TABLE` varies by engine, version and operation in ways that are easy to get wrong, "
    "which is precisely why `gh-ost` and `pt-online-schema-change` exist, and reaching for one of "
    "them is a sign of experience rather than of over-engineering.",
    "Stripe's engineering post *Online migrations at scale* (2017) describes the four-phase version "
    "in production: dual write to both old and new, backfill existing rows, dual read with the new "
    "data as the source of truth and the old as a comparison, then stop writing and remove the old "
    "field. Danilo Sato's *ParallelChange* entry on martinfowler.com is the general formulation of "
    "the same three-step structure for any interface, not just a schema. GitHub's `gh-ost` and "
    "Percona's `pt-online-schema-change` are the tooling that exists because the DDL step is "
    "dangerous on large tables.",
    """flowchart TD
    E["1 Expand<br/>add new column, write both"] --> M["2 Backfill<br/>migrate historical rows"]
    M --> R["3 Dual read<br/>new is truth, old logged for comparison"]
    R --> V["4 Verify<br/>counter on old read path reads zero<br/>for longer than your slowest client lives"]
    V --> C["5 Contract<br/>stop writing old, drop it"]
    R -.->|"skipped"| B["Backfill bugs found after<br/>the old data is gone"]
    style V fill:#1c6853,stroke:#4fc3a1,color:#e4ecea
    style B fill:#2b1c17,stroke:#e0705a,color:#e4ecea"""),

"Sidecar": P(
    "Run cross-cutting functionality in a separate process co-located with the application, "
    "sharing its lifecycle and network namespace.",
    "Istio and Linkerd data planes, Envoy as a service-mesh proxy, log and metric shippers, "
    "Netflix Prana, Vault agent injectors.",
    "A second container is scheduled in the same pod as the application. It shares the network "
    "namespace and local storage, so the application talks to it over localhost, and traffic can "
    "be transparently redirected through it with iptables rules.",
    "Retries, mTLS, circuit breaking, tracing and service discovery must be implemented correctly "
    "in every service — and in a polyglot estate that means writing and maintaining the same "
    "policy library six times, with six sets of bugs and six upgrade schedules.",
    "Cross-cutting behaviour is implemented once and deployed everywhere regardless of language. "
    "Policy is upgraded independently of the applications. Applications become smaller, and teams "
    "stop reimplementing resilience.",
    "One extra process per instance, so its memory and CPU are multiplied by your pod count — at "
    "thousands of pods that is a meaningful line in the bill. It is on the data path, so its p99 "
    "is added to every call, inbound and outbound. The mesh's control plane becomes a dependency "
    "of every request path in the cluster. And debugging gains a layer that the application "
    "developer usually cannot see into.",
    "Uniform, language-independent policy bought with a proxy on every pod and on every request.",
    "**The real cost is not CPU, it is lifecycle**, and for years the defining sidecar bugs were "
    "ordering bugs: the application container starts before the proxy is ready and its first "
    "outbound calls fail with a connection refused, and a batch job finishes successfully but the "
    "sidecar never exits, so the pod never completes and the job hangs forever. Anyone who ran a "
    "mesh before Kubernetes fixed this wrote shell workarounds for both — polling the proxy's "
    "readiness endpoint at startup, and curling its quit endpoint at the end. Kubernetes only "
    "addressed it properly with **native sidecar containers**: an init container declared with "
    "`restartPolicy: Always`, which starts before the application, keeps running alongside it, and "
    "is excluded from the pod's completion condition. Knowing that history is the difference "
    "between choosing a mesh with open eyes and discovering it in an incident. Second, the honest "
    "justification test: the sidecar earns its cost when you are genuinely polyglot and cannot "
    "ship one policy library, and usually does not when you have one language and a good client "
    "library. Third, the industry has priced the overhead and is moving — Istio's ambient mode "
    "removes the per-pod sidecar for the common case precisely because a proxy per pod turned out "
    "to be expensive at scale.",
    "Burns and Oppenheimer's *Design Patterns for Container-Based Distributed Systems* (HotCloud "
    "2016) named the sidecar, ambassador and adapter patterns from Google's container experience. "
    "The lifecycle problem is documented in Kubernetes' own history: native sidecar containers "
    "reached beta in 1.29 and stable in 1.33, and the KEP motivating them cites exactly the "
    "startup-ordering and job-completion failures above. Istio's ambient mode is the current "
    "public response to the per-pod resource cost.",
    """flowchart TD
    S["Pod starts"] --> Q{"Sidecar ordering"}
    Q -->|"plain container"| A["App starts first<br/>first outbound calls fail<br/>job ends, sidecar never exits, pod hangs"]
    Q -->|"native sidecar<br/>init container, restartPolicy Always"| B["Proxy ready before app<br/>excluded from pod completion"]
    B --> C["Every call still pays the proxy p99<br/>inbound and outbound"]
    style A fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style B fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),

"Ambassador": P(
    "Put a local proxy in front of the application's outbound calls so it can connect to a remote "
    "service as if it were local.",
    "Envoy as an egress proxy, Airbnb's SmartStack with a local HAProxy per host, Cloud SQL Auth "
    "Proxy, database connection proxies such as PgBouncer deployed per node.",
    "The application connects to a fixed local address. The ambassador handles discovery, TLS, "
    "load balancing across remote instances, retries, circuit breaking and observability, then "
    "forwards the request.",
    "Every client library in every language would otherwise need to implement service discovery, "
    "mTLS, retry policy and outlier detection identically — and legacy applications cannot be "
    "changed to do any of it at all.",
    "The application's networking code collapses to a localhost connection. Discovery and policy "
    "are managed centrally and can be changed without touching or redeploying the application. "
    "Legacy and third-party binaries gain modern networking behaviour without modification.",
    "The ambassador's own limits silently become the application's limits — its connection pool, "
    "its file descriptors, its concurrency ceiling replace whatever the client library had, and "
    "usually nobody notices until saturation. It is a single process on the host or pod, so it is "
    "a local single point of failure. And it hides the remote topology completely, which is "
    "convenient right up to the point where you need to reason about it.",
    "Uniform outbound networking bought with a local proxy whose limits are now yours.",
    "The subtlety people miss is about **errors, not latency**. Because the application now talks "
    "to localhost, it has lost the ability to distinguish 'the remote service returned an error' "
    "from 'the network failed' from 'the ambassador itself is unhealthy' — every failure arrives "
    "as a 503 from a proxy, with the remote service's own status, headers and error body possibly "
    "rewritten or discarded. Unless the error taxonomy and the tracing are deliberately re-plumbed "
    "through the proxy, every outage looks identical from inside the application, and on-call "
    "spends the first twenty minutes of every incident determining which of three things broke. "
    "The second thing they check on day one is the resource ceiling: the ambassador's connection "
    "pool size and concurrency limit are now the *actual* limits of the application, replacing the "
    "client library's, and an application that was tuned for 200 concurrent outbound calls will "
    "quietly queue behind a proxy configured for 64. Airbnb's SmartStack is worth reading as the "
    "pre-mesh version of the idea — a local HAProxy per host with discovery kept entirely out of "
    "the application — because it makes the same argument without the control plane, and shows how "
    "much of the value comes from the local proxy alone.",
    "Burns and Oppenheimer's HotCloud 2016 paper names the ambassador as one of three "
    "container-based patterns, defined specifically as proxying *outbound* connections on the "
    "application's behalf. Airbnb's SmartStack, comprising Nerve for registration and Synapse for "
    "configuring a local HAProxy, is the well-documented production instance from 2013 and "
    "predates service meshes by several years. Google's Cloud SQL Auth Proxy is the same pattern "
    "narrowed to one dependency, handling authentication and encryption so the application can use "
    "a plain local connection.",
    """flowchart LR
    APP["Application<br/>connects to localhost 8080"] --> AMB["Ambassador proxy<br/>discovery, mTLS, retries, outlier detection"]
    AMB --> R1["Remote instance 1"]
    AMB --> R2["Remote instance 2"]
    AMB -.-> E["All failures look like a local 503<br/>remote status and body may be rewritten"]
    AMB -.-> L["Proxy pool size is now<br/>the application concurrency limit"]
    style E fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style L fill:#2a2317,stroke:#d9a441,color:#e4ecea"""),

"Backend-for-Frontend": P(
    "Give each client type its own backend service that aggregates and shapes data specifically "
    "for it.",
    "SoundCloud's mobile and web BFFs, Netflix's device-specific API adapters, most large "
    "consumer products with a mobile app and a web app that diverged.",
    "Each client — iOS, Android, web, partner API — talks to a backend built for it. That backend "
    "calls the domain services, aggregates their responses, and returns exactly the payload that "
    "client's screens need, in one round trip.",
    "One general-purpose API cannot be optimal for a mobile client on a high-latency connection "
    "and a desktop client on fibre at the same time. A shared API accretes optional fields and "
    "query parameters for every client, and eventually changing it safely requires knowing all of "
    "them.",
    "Each client gets payloads and round-trip counts tuned to its constraints. Client teams can "
    "change their own backend without coordinating with anyone else, which removes the biggest "
    "source of cross-team delay. The domain services stay clean of presentation concerns.",
    "Duplication across BFFs is structural rather than accidental — a new field means N changes, "
    "in N repositories, on N release schedules. Each BFF is another deployable, another on-call "
    "rota and another hop of latency. And without discipline the BFFs accumulate business logic "
    "and you have built a distributed monolith with the domain rules in the presentation tier.",
    "Client-optimised APIs bought with N backends to keep in step for every change.",
    "The rule that keeps a BFF from becoming three divergent copies of your business logic is that "
    "**a BFF owns aggregation and shaping, never domain rules** — the moment a discount is "
    "calculated inside the iOS BFF, the Android app is wrong and nobody will notice for a quarter. "
    "The second point is organisational and it is the one that decides whether the pattern works "
    "at all: **a BFF must be owned by the client team**, not by a platform team. Phil Calçado's "
    "account from SoundCloud is explicit that the pattern paid off because the team that owned the "
    "frontend also owned its backend; a BFF maintained by a separate team is simply an extra queue "
    "in your delivery pipeline with a worse SLA than the API it replaced, and you have taken on "
    "the duplication cost while keeping the coordination cost. Third, they know what the "
    "alternative buys: teams reach for GraphQL, and increasingly federated GraphQL, to collapse N "
    "BFFs into one schema — Netflix did exactly that, replacing device-specific backends with a "
    "federated graph — and the honest framing is that this converts a code-duplication problem "
    "into a schema-governance problem rather than eliminating the work.",
    "Phil Calçado's 2015 post *The Back-end for Front-end Pattern* is the canonical write-up and "
    "describes how SoundCloud arrived at it after their general-purpose API became a bottleneck "
    "between teams. Netflix reached the same conclusion earlier from the device side — Daniel "
    "Jacobson's 2012 *Embracing the Differences* described per-device adapters replacing a "
    "one-size-fits-all API — and later published their move to GraphQL federation, which "
    "consolidated those device-specific backends into a single federated schema owned across "
    "teams.",
    """flowchart TD
    IOS["iOS app"] --> B1["iOS BFF"]
    WEB["Web app"] --> B2["Web BFF"]
    PART["Partner"] --> B3["Partner BFF"]
    B1 --> D1["Orders service"]
    B2 --> D1
    B3 --> D1
    B1 --> D2["Pricing service"]
    B2 --> D2
    RULE["Aggregation and shaping only<br/>domain rules stay in the services"] -.-> B1
    OWN["Each BFF owned by its client team<br/>or it is just another queue"] -.-> B2
    style RULE fill:#1c6853,stroke:#4fc3a1,color:#e4ecea
    style OWN fill:#1c6853,stroke:#4fc3a1,color:#e4ecea"""),
}
