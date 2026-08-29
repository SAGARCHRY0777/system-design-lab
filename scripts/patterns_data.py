"""Pattern data for gen_pattern_catalogue.py.

Split out because the catalogue is mostly content, and mixing a thousand lines
of prose into the renderer makes both harder to change.

Each entry:
    what      one-line definition
    where     a real system that ships it, so the pattern is not hypothetical
    how       the mechanism, concretely
    why       the problem it exists for
    adv       what you gain
    dis       what you lose
    tradeoff  the single sentence to remember
    top1      what an experienced engineer does that a competent one does not.
              This field is the reason the catalogue exists -- every other field
              is available in any reference.
    bridge    (GoF only) the distributed counterpart
    harder    (GoF only) why the distributed version costs more
"""


def P(what, where, how, why, adv, dis, tradeoff, top1, bridge=None, harder=None):
    return dict(what=what, where=where, how=how, why=why, adv=adv, dis=dis,
                tradeoff=tradeoff, top1=top1, bridge=bridge, harder=harder)


GOF_CREATIONAL = {
"Singleton": P(
    "Exactly one instance of a type, globally reachable.",
    "Logger and config objects in almost every codebase; connection pools.",
    "A private constructor and a static accessor that lazily creates and caches the instance.",
    "Some resources genuinely must be unique — one connection pool, one metrics registry — and "
    "creating a second silently doubles the resource.",
    "Guarantees uniqueness; avoids repeatedly constructing something expensive.",
    "Global mutable state. Hidden dependencies that do not appear in any signature. Hostile to "
    "testing, because tests cannot substitute or reset it. Thread-safety is easy to get wrong.",
    "Uniqueness bought with global state and untestability.",
    "They mostly do not use it. They register a single instance in a dependency-injection "
    "container instead — you still get one instance, but it arrives as a constructor argument, so "
    "it is visible, substitutable in tests, and has an obvious lifetime. When they *do* use the "
    "classic form, it is for something with no state worth resetting. The tell that it is being "
    "misused: a test that passes alone and fails in a suite.",
    "Leader election · distributed lock",
    "One process needs a static field. A cluster needs consensus, a lease and a fencing token — "
    "and during a partition two nodes can both believe they are the singleton."),

"Factory Method": P(
    "A method that creates objects, letting subclasses decide the concrete type.",
    "Framework extension points; `Iterator` creation in collection libraries.",
    "Define a creation method in a base class; subclasses override it to return their own type.",
    "Callers should depend on an interface, not on a constructor for a concrete class.",
    "Decouples construction from use; new types need no caller changes.",
    "A class per variant. Indirection that is not worth it when there are only two cases.",
    "Flexibility bought with indirection.",
    "They add it when the *second* variant appears, not in anticipation of one. A factory with a "
    "single implementation is speculative generality — the cost is paid now, the benefit may "
    "never arrive. They also prefer a plain function over a class hierarchy when the language "
    "allows it.",
    "Service discovery · DI container",
    "'Which implementation' becomes 'which instance, and is it healthy right now'."),

"Abstract Factory": P(
    "Create families of related objects without naming their concrete classes.",
    "Cross-platform UI toolkits; cloud-provider abstraction layers.",
    "An interface with several creation methods; each concrete factory returns a matched set.",
    "Some objects only work together — a Windows button with a Windows scrollbar — and mixing "
    "families breaks things.",
    "Guarantees a consistent family; swapping the whole set is one line.",
    "Adding a new *product* to the family changes every factory. Heavy for small variation.",
    "Family consistency bought with rigidity.",
    "They are sceptical of it for cloud abstraction specifically. Providers differ in "
    "*capability*, not only in naming, so the abstraction leaks the moment one lacks a primitive "
    "— and you end up with the intersection of every provider's features, which is worse than "
    "picking one. They use it where the families are genuinely symmetric, and accept lock-in "
    "where they are not.",
    "Cloud provider abstraction · driver families",
    "The families differ in what they can do, not just in what they are called."),

"Builder": P(
    "Construct a complex object step by step, separating construction from representation.",
    "HTTP request builders; query builders; `StringBuilder`.",
    "A builder accumulates parameters through chained calls, then produces the object.",
    "Constructors with many optional parameters become unreadable and error-prone — two adjacent "
    "booleans are a bug waiting to happen.",
    "Readable at the call site; supports immutability; validates once at build time.",
    "More code than a constructor. An unbuilt builder is an easy thing to leave dangling.",
    "Call-site clarity bought with boilerplate.",
    "They validate in `build()`, not in each setter, so the object cannot exist in an invalid "
    "state — and they make the built object immutable. The version that quietly causes bugs is a "
    "reusable builder whose state leaks between builds.",
    "Fluent request builders · infrastructure-as-code",
    "A half-built distributed resource is already running and already costing money."),

"Prototype": P(
    "Create new objects by cloning an existing instance.",
    "Container images; VM templates; database snapshots; game entity spawning.",
    "The object exposes a `clone()` that copies its own state.",
    "Sometimes construction is expensive but copying is cheap — or the desired initial state only "
    "exists at runtime.",
    "Avoids expensive setup; captures runtime-configured state.",
    "Deep versus shallow copy is a persistent source of bugs. Cloning objects holding handles, "
    "locks or connections is usually wrong.",
    "Cheap creation bought with copy-semantics hazards.",
    "They ask what the clone must *not* inherit — identity, connections, locks, caches — and "
    "explicitly reset those. The classic production bug is a cloned object that inherited the "
    "original's open connection or its ID.",
    "Container images · VM templates · snapshots",
    "Cloning state is easy; cloning identity is not. The clone must not inherit leases or "
    "client connections."),
}

GOF_STRUCTURAL = {
"Adapter": P(
    "Convert one interface into another the caller expects.",
    "ORM drivers; payment gateway integrations; anti-corruption layers.",
    "Wrap the incompatible object and translate calls.",
    "You do not control the third-party interface, and you do not want its shape leaking through "
    "your codebase.",
    "Integrates incompatible code without modifying either side; contains the foreign model.",
    "An extra layer to maintain. Can hide semantic mismatches that are not merely syntactic.",
    "Compatibility bought with a translation layer.",
    "They use it as a boundary for the *domain model*, not just for method signatures — a true "
    "anti-corruption layer. The failure they avoid: an adapter that mirrors the vendor's model "
    "one-to-one, which spreads the vendor's concepts through your code while adding a layer.",
    "Anti-corruption layer · protocol translation",
    "The adapter now fails independently of both sides it adapts."),

"Bridge": P(
    "Separate an abstraction from its implementation so the two can vary independently.",
    "JDBC and database drivers; rendering backends; storage interfaces.",
    "The abstraction holds a reference to an implementation interface; both hierarchies evolve "
    "separately.",
    "Without it, `N` abstractions × `M` implementations means `N×M` classes.",
    "Collapses a combinatorial class explosion to `N+M`; either side changes alone.",
    "Indirection, and an abstraction that must genuinely fit every implementation.",
    "Independent variation bought with an extra indirection.",
    "They reach for it only when both axes are *actually* varying. Most codebases have one "
    "implementation and will always have one, and a bridge there is pure cost.",
    "Storage/driver interfaces · pluggable backends",
    "Implementations differ in failure modes, not only in method bodies."),

"Composite": P(
    "Treat individual objects and compositions of them uniformly.",
    "File system trees; UI component trees; nested permission groups.",
    "Leaf and container implement the same interface; the container delegates to children.",
    "Callers should not need to know whether they hold one thing or a thousand.",
    "Uniform treatment; recursive structures become natural.",
    "The interface becomes the union of leaf and container needs, so leaves get methods that make "
    "no sense for them. Recursion depth and cycles are real hazards.",
    "Uniformity bought with a weakened interface.",
    "They guard the depth and detect cycles, because the production failure is a stack overflow "
    "on user-supplied nesting. Distributed, they know a scatter-gather composite is as slow as "
    "its slowest member — every single time.",
    "Scatter-gather · fan-out aggregation",
    "A composite call takes the slowest member's latency, every time — *The Tail at Scale*."),

"Decorator": P(
    "Attach behaviour to an object dynamically, without changing its type.",
    "HTTP middleware; Java I/O streams; service mesh sidecars.",
    "Wrap the object in something implementing the same interface, adding behaviour around calls.",
    "Subclassing for every combination of optional behaviours explodes combinatorially.",
    "Compose behaviour at runtime; each concern stays separate.",
    "Deep wrapping is very hard to debug — a stack trace forty frames of wrappers deep tells you "
    "nothing. Order matters and is invisible at the call site.",
    "Composability bought with debuggability.",
    "They keep the chain shallow and make the order explicit and reviewable, because "
    "auth-then-log and log-then-auth are different systems. In middleware they know the ordering "
    "*is* the security model.",
    "Middleware · service mesh sidecar · filter chain",
    "Each decorator is now a network hop with its own latency and its own failure mode."),

"Facade": P(
    "One simplified interface over a complex subsystem.",
    "API gateways; SDK entry points; backend-for-frontend.",
    "A single class exposing the few operations callers actually need.",
    "Subsystems accumulate surface area that most callers should never see.",
    "Reduces coupling; gives newcomers one obvious entry point.",
    "Can become a god object. Hides capability that some caller eventually needs, producing "
    "pressure to leak the subsystem back out.",
    "Simplicity bought with hidden capability.",
    "They keep the subsystem reachable for the callers who need it, rather than making the facade "
    "the only door. Distributed, they watch for the facade becoming both a single point of "
    "failure and a deployment bottleneck for every team behind it.",
    "API gateway · backend-for-frontend",
    "It becomes a single point of failure and a release bottleneck for every team behind it."),

"Flyweight": P(
    "Share common state across many objects instead of duplicating it.",
    "String interning; glyph caches; connection pools.",
    "Split intrinsic (shared) from extrinsic (per-use) state; cache and reuse the intrinsic part.",
    "Millions of near-identical objects exhaust memory when each carries its own copy.",
    "Large memory savings when duplication is genuinely high.",
    "Shared state must be immutable or you have introduced a data race. Complicates the object "
    "model for what is often a modest saving.",
    "Memory bought with shared-mutability risk.",
    "They measure first. It is a real win at millions of objects and pure complexity at "
    "thousands. Its distributed descendant — connection pooling — they *always* use, and they "
    "size it with Little's Law rather than by copying a default.",
    "Connection pooling · shared caches · interning",
    "Shared state across processes needs invalidation; a pooled connection can be stale in ways "
    "an interned string never is."),

"Proxy": P(
    "A stand-in that controls access to another object.",
    "Reverse proxies; lazy-loading ORM entities; sidecars; read-through caches.",
    "Same interface as the subject; intercepts calls to add laziness, access control, caching or "
    "remoting.",
    "You want to intervene between caller and subject without either knowing.",
    "Adds cross-cutting behaviour transparently.",
    "Transparency is the danger: a call that looks local is a network round trip, or triggers a "
    "lazy load. This is exactly the N+1 query problem.",
    "Transparency bought with hidden cost.",
    "They make the expensive case *visible* rather than seamless. An ORM lazy-loading proxy that "
    "silently issues a query per loop iteration is the single most common performance bug in web "
    "applications, and it exists because the proxy hid the cost perfectly.",
    "Reverse proxy · sidecar · read-through cache",
    "A remote proxy can be reachable while its subject is not — exactly the case needing a "
    "timeout and a circuit breaker."),
}

GOF_BEHAVIORAL = {
"Chain of Responsibility": P(
    "Pass a request along a chain until a handler deals with it.",
    "HTTP middleware pipelines; Netflix Zuul filters; event bubbling in UIs.",
    "Each handler either processes the request or forwards it to the next.",
    "The sender should not know which handler will act, or how many exist.",
    "Handlers are added and reordered without touching the sender.",
    "A request can fall off the end unhandled. Debugging means tracing the whole chain.",
    "Decoupling bought with control-flow opacity.",
    "They always define terminal behaviour, so nothing silently falls through, and they make the "
    "chain order explicit configuration rather than registration-order accident. In middleware "
    "the order is the security model, so it gets reviewed like one.",
    "Middleware pipeline · filter chain",
    "A handler mid-chain can be slow rather than absent, and the chain has no natural timeout."),

"Command": P(
    "Encapsulate a request as an object.",
    "Undo/redo stacks; job queues; event sourcing; CQRS write side.",
    "Wrap the action and its parameters in an object with an `execute()`.",
    "Requests need to be queued, logged, retried, scheduled or undone — none of which is possible "
    "with a bare method call.",
    "Enables undo, queueing, retry, audit and replay.",
    "A class per action. Serialised commands must stay compatible with future code.",
    "Deferability bought with indirection and versioning obligations.",
    "They treat a serialised command as a **permanent public API**. A command written today may "
    "be replayed in two years by code that does not exist yet, so it is versioned from day one "
    "and never has a field's meaning quietly changed. That discipline is what makes event "
    "sourcing survivable.",
    "Message · job · event sourcing",
    "A serialised command outlives its sender: it must be versioned, idempotent and replay-safe."),

"Interpreter": P(
    "Represent a grammar and evaluate sentences in it.",
    "SQL engines; regular expressions; rules engines; query DSLs.",
    "Model grammar rules as a class hierarchy; evaluate recursively over the tree.",
    "Some problems are best expressed in a small language rather than in code.",
    "Users express intent declaratively; the language can be optimised independently.",
    "Grammars grow. A hand-rolled interpreter becomes a maintenance burden fast, and performance "
    "is usually poor without a compilation step.",
    "Expressiveness bought with a language to maintain forever.",
    "They resist writing one. A configuration DSL becomes Turing-complete by accident, and then "
    "you own a programming language you never meant to design. When it is genuinely warranted "
    "they use an existing grammar or parser generator.",
    "Query planners · SQL and DSL execution",
    "The same query has different optimal plans on different shards."),

"Iterator": P(
    "Traverse a collection without exposing its internal structure.",
    "Every standard library; database cursors; paginated APIs.",
    "An object holding traversal position, with `next()` and `hasNext()`.",
    "Callers should not depend on whether it is an array, a tree or a stream.",
    "Uniform traversal; supports laziness and infinite sequences.",
    "Concurrent modification during traversal. State that must be cleaned up.",
    "Abstraction bought with lifetime and concurrency concerns.",
    "In distributed systems they insist on **cursor** pagination over offset pagination. Offset "
    "pagination silently skips and duplicates rows when the underlying data changes mid-"
    "traversal, and the bug is invisible in testing because test data does not move. This one "
    "distinction separates people who have run a paginated API in production from people who "
    "have not.",
    "Cursor pagination · scroll APIs",
    "The collection changes mid-traversal; offset pagination silently skips and duplicates."),

"Mediator": P(
    "Objects communicate through a hub rather than directly with each other.",
    "Message brokers; saga orchestrators; UI dialog coordinators; air traffic control.",
    "A mediator holds the interaction rules; participants only know the mediator.",
    "`N` objects talking directly to each other is `N²` couplings, and every one is a reason to "
    "redeploy something.",
    "Collapses `N²` couplings to `N`; interaction logic lives in one reviewable place.",
    "The mediator accumulates all the complexity it removed from everyone else, and becomes a god "
    "object. It is also, distributed, a single point of failure.",
    "Decoupling bought by concentrating complexity in one place.",
    "They watch for the mediator becoming the thing nobody dares change. Distributed, the "
    "critical question is one most people skip: **is the mediator itself redundant?** A message "
    "broker mediating twelve services caps all twelve at its own availability, and it is "
    "routinely the least redundant thing in the diagram.",
    "Message broker · orchestrator · saga coordinator",
    "It becomes the availability ceiling for everything it mediates."),

"Memento": P(
    "Capture and restore an object's state without violating encapsulation.",
    "Undo stacks; database savepoints; consumer offsets; VM snapshots.",
    "The object produces an opaque snapshot only it can interpret.",
    "Rollback requires saved state, but exposing internals to save them breaks encapsulation.",
    "Undo without leaking internals.",
    "Memory cost per snapshot. Snapshots go stale as the class evolves.",
    "Reversibility bought with storage and versioning.",
    "They snapshot *deltas* rather than full state where they can, and version the snapshot "
    "format. Distributed, they know a snapshot across nodes is not a moment in time unless it is "
    "coordinated — which is what Chandy–Lamport exists for, and why 'just snapshot everything at "
    "midnight' is not a backup strategy.",
    "Snapshots · checkpoints · consumer offsets",
    "A distributed snapshot is not a single moment unless coordinated (Chandy–Lamport)."),

"Observer": P(
    "Notify dependents automatically when an object changes state.",
    "Pub/sub; webhooks; UI data binding; change data capture.",
    "Subjects keep a subscriber list and call each on change.",
    "Publishers should not need to know who cares.",
    "Loose coupling; subscribers added without touching the publisher.",
    "Notification order is unspecified. Cascading updates are hard to trace. **Subscribers that "
    "are never removed are a classic memory leak.**",
    "Decoupling bought with untraceable control flow.",
    "They treat unsubscription as a lifecycle obligation, because the leak is silent and only "
    "appears under sustained load. Distributed, they know the in-process version cannot fail and "
    "the distributed version fails constantly — delivery is not guaranteed, ordering is not "
    "guaranteed, and the observer may be down. Every webhook needs retry, idempotency and a DLQ.",
    "Pub/sub · webhooks · change data capture",
    "Delivery and ordering are not guaranteed and the observer may be down. In-process this was "
    "a method call that could not fail."),

"State": P(
    "Change an object's behaviour when its internal state changes.",
    "Order lifecycles; connection state machines; workflow engines like Temporal.",
    "Each state is an object; the context delegates and states control transitions.",
    "Large conditionals over a status field become unmaintainable and permit illegal transitions.",
    "Illegal transitions become impossible rather than merely discouraged; each state is testable "
    "alone.",
    "A class per state. Overkill for two or three states.",
    "Correctness bought with class count.",
    "They draw the diagram first and treat *missing* arrows as the specification — the value is "
    "in the transitions you have made unrepresentable. Distributed, transitions must be durable "
    "and exactly-once, because a crash mid-transition leaves the machine in a state that does not "
    "appear on the diagram at all.",
    "Workflow engines · Step Functions · Temporal",
    "Transitions must be durable and exactly-once, or a crash lands you in an undefined state."),

"Strategy": P(
    "Select an interchangeable algorithm at runtime.",
    "Load balancing algorithms; compression codec selection; pricing rules; sort comparators.",
    "Encapsulate each algorithm behind a common interface; inject the chosen one.",
    "Hard-coded conditionals over algorithm choice are rigid and untestable in isolation.",
    "Algorithms swap without touching callers; each is testable alone.",
    "Callers must know enough to choose. A class per algorithm.",
    "Flexibility bought with a choice the caller now has to make.",
    "They make the *default* correct and the choice rare, rather than exposing a menu. In load "
    "balancing they know least-connections usually beats round-robin for heterogeneous request "
    "costs — and that the right strategy depends on live conditions the caller cannot see, which "
    "is an argument for choosing adaptively rather than configuring.",
    "Load balancing algorithms · routing and placement policy",
    "The right strategy depends on live conditions the caller cannot observe."),

"Template Method": P(
    "A base class defines the skeleton; subclasses fill in steps.",
    "Framework lifecycle hooks; test setup/teardown; MapReduce.",
    "A non-overridable method calls overridable steps in a fixed order.",
    "Several variants share a sequence but differ in individual steps.",
    "Removes duplication; the shared sequence is enforced, not merely documented.",
    "Inheritance-based, so it is rigid — subclasses are bound to the base's shape. Deep hierarchies "
    "become opaque.",
    "Shared structure bought with inheritance coupling.",
    "They prefer composition — pass the steps in as functions — because it composes and tests "
    "better than a hierarchy. Distributed, one slow step stalls every stage behind it, which is "
    "why pipelines need per-stage timeouts.",
    "Framework hooks · pipeline stages · MapReduce",
    "One slow or failing step stalls every stage behind it."),

"Visitor": P(
    "Add operations to an object structure without modifying its classes.",
    "AST traversal in compilers; linters; schema migration tooling.",
    "Elements accept a visitor and dispatch to the method for their type.",
    "You need new operations over a stable structure, and editing every class for each new "
    "operation does not scale.",
    "New operations without touching the elements; related logic stays together.",
    "**Adding a new element type breaks every visitor.** Double dispatch is awkward in most "
    "languages and unfamiliar to most readers.",
    "Operation extensibility bought with element rigidity.",
    "They apply the rule that decides it: use Visitor when the *structure* is stable and the "
    "*operations* churn; if new element types appear regularly, it is the wrong pattern and will "
    "punish you on every addition. In languages with pattern matching they use that instead.",
    "AST/query traversal · schema migration tooling",
    "The structure is distributed, so traversal is a distributed algorithm with partial failure."),
}
