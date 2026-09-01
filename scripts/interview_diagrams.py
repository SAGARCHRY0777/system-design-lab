"""One framing diagram per interview track.

Kept apart from `interview_data.py` because that file is the question bank and
this is presentation: mixing them would mean editing 1,800 lines of prose to
change a picture.

Each diagram is the thing the track's questions keep circling back to -- the
shape a candidate is expected to already have in their head. Not decoration: if
a diagram here does not answer at least one of its own track's questions, it
should not be here.
"""

DIAGRAMS: dict[str, str] = {
    "foundations": """flowchart LR
    P["Pick any two<br/>under a partition"] --> C["Consistency<br/>every read sees the last write"]
    P --> A["Availability<br/>every request gets an answer"]
    P --> T["Partition tolerance<br/>the network WILL split"]
    T --> N["Not optional.<br/>So the real choice<br/>is C or A."]
""",

    "caching": """flowchart LR
    CL["Client"] --> AP["App"]
    AP -->|"1 - look"| CA["Cache"]
    CA -->|"HIT, ~95%<br/>1 ms"| AP
    AP -.->|"2 - MISS only<br/>~30 ms"| DB[("Database")]
    DB -.->|"3 - populate"| CA
    X["Cache dies:<br/>100% of reads land<br/>on the database at once"] -.-> DB
""",

    "databases": """flowchart TB
    Q["A query arrives"] --> D{"What shape<br/>is the access?"}
    D -->|"known key,<br/>one row"| K["Point lookup<br/>index does the work"]
    D -->|"range over<br/>one column"| R["Range scan<br/>ordering does the work"]
    D -->|"join across<br/>many tables"| J["Normalised relational<br/>correctness does the work"]
    D -->|"whole document<br/>at once"| N["Denormalised<br/>read speed, write amplification"]
""",

    "sharding-replication": """flowchart TB
    subgraph rep["Replication — COPIES of the same data"]
        direction LR
        PR[("Primary")] -.->|"lag"| RA[("Replica")]
        PR -.-> RB[("Replica")]
    end
    subgraph sh["Sharding — SPLITS of different data"]
        direction LR
        S1[("Shard 1<br/>keys a-h")]
        S2[("Shard 2<br/>keys i-p")]
        S3[("Shard 3<br/>keys q-z")]
    end
    rep --> W["Replication buys read capacity<br/>and survives a node loss."]
    sh --> V["Sharding buys write capacity<br/>and dataset size."]
    W --> Z["Different axes.<br/>Most systems need both."]
    V --> Z
""",

    "messaging": """flowchart LR
    PD["Producer"] -->|"publish and return<br/>caller does not wait"| Q[["Queue"]]
    Q --> C1["Consumer"]
    Q --> C2["Consumer"]
    C1 -->|"ack"| Q
    C2 -.->|"fails N times"| DLQ[["Dead letter"]]
    DLQ -.-> H["A human looks at it.<br/>Without this a poison message<br/>occupies a worker forever."]
""",

    "api-design": """flowchart TB
    subgraph rest["REST"]
        R1["GET /users/1"] --> R2["GET /users/1/orders"] --> R3["N more calls<br/>for each order"]
    end
    subgraph gql["GraphQL"]
        G1["One query,<br/>exactly the fields wanted"] --> G2["One round trip.<br/>Cost moves to the server."]
    end
    subgraph grpc["gRPC"]
        P1["Binary, typed,<br/>streaming"] --> P2["Fast between services.<br/>Awkward from a browser."]
    end
""",

    "security": """flowchart LR
    U["User"] -->|"1 - credentials"| I["Identity provider"]
    I -->|"2 - signed token<br/>short lived"| U
    U -->|"3 - token on every call"| G["API Gateway"]
    G -->|"4 - verify SIGNATURE<br/>not the contents"| G
    G -->|"5 - authenticated:<br/>who are you"| S["Service"]
    S -->|"6 - authorised:<br/>may you do THIS"| D[("Data")]
""",

    "observability": """flowchart TB
    M["Metrics<br/>cheap, aggregate<br/>tells you SOMETHING is wrong"] --> AL{"Alert"}
    T["Traces<br/>one request end to end<br/>tells you WHERE"] --> AL
    L["Logs<br/>expensive, detailed<br/>tells you WHY"] --> AL
    AL --> SLO["Alert on SLO burn,<br/>not on CPU.<br/>A page nobody acts on<br/>trains people to ignore pages."]
""",

    "architecture": """flowchart LR
    A["Monolith<br/>one deploy, no boundaries"] --> B["Modular monolith<br/>boundaries, still one deploy"]
    B --> C["Services<br/>boundaries plus a network"]
    B --> D["The boundaries are<br/>the valuable part, and free."]
    C --> E["The network is the<br/>expensive part, and deferrable."]
""",
}
