> **Attention**  
> <span style="background-color: #fffbe6; padding: 8px 12px; border-radius: 4px; display: block;">
> This repository is an *instructive tool* and is part of a series of guidebooks on safety tools. Use it for learning and demonstration purposes only; it is **not intended for unsupervised or production-critical use**.
> </span>


# rmrf - The Safer 'rm -rf' that No One Asked For

rmrf is a safer version of 'rm -rf', though it is not intended to be used as a direct replacement. Instead, it demonstrates how operators can design their own safe tools for managing complex systems. It is now easier than ever to build your own tools, giving operators the opportunity to take control of their own destiny, to design their own fate. They now have the ability to build better tools to help future versions of themselves.

rmrf is an exploration of the basics of building a safe operational tool and is intended as an example as opposed to a production-ready tool. We have used 'rm -rf' as a starting point because it is a highly visible and well-known command that is clearly dangerous in many situations, and, what one might consider the ultimate 'footgun'.

When operating complex systems, we don't want 'footguns'; we want safe, easy-to-use tools that follow safety best practices. rmrf is a starting point for operators to build their own tools and understand the basics of creating safe tools.

## How It Works

```mermaid
flowchart TD
    %% --- Main workflow (vertical) ---
    A[Plan] --> B[Validate]
    B --> C[Stage]
    C --> D[Apply]
    D --> E[Verify]
    E --> F[Learn]
    F --> A

    %% --- Near-miss paths ---
    B -->|preflight issue| G[Near Miss]
    C -->|staging issue| G
    G --> F

    %% --- Failure and rollback paths ---
    D -->|apply error| H[Failure]
    E -->|verification fails| H
    H --> R[Rollback]
    R --> F

    %% --- Color styling ---
    classDef phase fill:#eaeaea,stroke:#333,stroke-width:1px;
    classDef nearMiss fill:#ffcc80,stroke:#d9822b,stroke-width:1px,color:#000;
    classDef failure fill:#ff9999,stroke:#b30000,stroke-width:1px,color:#000;
    classDef good fill:#a8e6a3,stroke:#2d7a2d,stroke-width:1px,color:#000;

    class A,B,C,D phase;
    class E,F,R good;
    class G nearMiss;
    class H failure;

```

With rmrf we plan actions, and then execute them in a multi-stage workflow with safety checkpoints:

1. **Plan** - Scan targets, calculate risk score, generate unique plan ID
2. **Validate** - Check against protection level constraints and policies
3. **Approve** - For high-risk operations, require approval from a different user
4. **Stage** - Create verified backup copies with SHA-256 checksums
5. **Apply** - Execute the action with verification
6. **Verify** - Confirm the action was successful
7. **Learn** - Record lessons learned and close out the plan

High-risk deletions in production environments require multi-user approval. The approving user must be a different Linux user (different UID) than the plan creator, preventing a single person from executing dangerous operations without oversight.

## Getting Started

See the [Quick Start Guide](docs/quickstart.md) for installation and setup instructions.

## Caveats and Limitations

rmrf is not intended to implement every possible safety feature in every situation. Much like cybersecurity, safety is driven by economics;we simply can't implement everything. However, there are certain low-hanging fruits and relatively straightforward items that we can do to make our tools and systems safer, and rmrf does its best to implement these.