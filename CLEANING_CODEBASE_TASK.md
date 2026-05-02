# Codebase Cleaning & Refactoring Task Plan

## Architectural Philosophy: "The Frame and The Pieces"
To effectively clean and decouple this application, we are dividing the architecture into two distinct layers:
1. **The Frame (Core Structure):** The fundamental skeleton. This includes the internal state structures, database models, the unified graph topology, the run manager/executor, the main server, and the API layer organization.
2. **The Pieces (Functional Components):** The modular elements that plug into the frame. This includes individual nodes (attack, defense, eval, routing), middleware (database, WebSocket), strategies (manual, automatic), and specific API endpoint behaviors.

**Execution Strategy:** We will strictly focus on refactoring **The Frame** first. Once the core structure is completely solid, decoupled, and stateless, we will move on to updating the Pieces.

---

## Identified Problems and Proposed Solutions

### Problem 1: Run Executor & Run Manager Are Overloaded
**Current State:** The `RunExecutor` and `RunManager` are doing far too much. They currently manage manual attack logic, handle waiting/pausing for user input, directly update database statuses, and emit WebSocket events.
**Solution: Make the Executor "Dumb" and Stateless.**
*   **Remove Statefulness:** Eliminate all logic related to "waiting for manual input", pausing, and resuming from the Run layer. 
*   **Request-Response Paradigm:** Manual runs must be treated as a standard, stateless request-response cycle. The API call initiates a single graph iteration. The system does not "wait" in memory; it completes the cycle, persists data, and terminates. The "pause" is simply the time between external API calls.
*   **Refined Flow:** API Request → Initialization → RunExecutor → WorkflowEngine → Graph runs for *one* iteration (based on Strategy) → Middleware handles persistence/WebSockets → Execution completes → Response sent to API.

### Problem 2: Divergent Graph Topologies
**Current State:** `engine/graph_builder.py` explicitly uses different logic branches (`manual_routing_logic` vs. `automatic_routing_logic`) depending on the run mode. 
**Solution: Unified Topology via Strategy Pattern.**
*   **Single Graph:** There will be only one graph structure. The graph itself does not care if it is in manual or automatic mode.
*   **Strategy-Driven Routing:** The chosen `Strategy` object is the "brain." It dictates the flow. If the strategy is Automatic, it tells the graph to loop. If the strategy is Manual, it tells the graph to terminate after one cycle.
*   **No "Wait" Nodes:** Remove all explicit "wait for input" states or nodes from the graph definition.

### Problem 3: LangGraph Streaming & Middleware Responsibility
**Current State:** There was confusion regarding where the event stream lives. The `RunExecutor` previously had its hands in control flow and WebSocket emissions that bypassed middleware.
**Solution: Strict `astream` Interception.**
*   **Workflow Engine Owns the Stream:** The `WorkflowEngine` is solely responsible for using LangGraph's `astream` feature to iterate through the graph's lifecycle. 
*   **Middleware Exclusivity:** As the `WorkflowEngine` streams the graph's execution, it intercepts the steps to trigger middleware hooks (`after_step`, etc.).
*   **Zero Executor Involvement:** All Database persistence and WebSocket broadcasting must be handled *exclusively* by their respective middlewares. The `RunExecutor` simply sets up the `WorkflowEngine` and calls `execute_run`.

### Problem 4: Middleware Selection & Injection
**Current State:** It is unclear who is responsible for choosing and attaching the correct mode-specific middleware (e.g., Manual vs. Automatic Database/WebSocket middleware).
**Solution: The Builder/Factory Pattern.**
*   **Graph Builder / Factory Responsibility:** When building the graph, the `ConfigurableGraphBuilder` (or a dedicated Middleware Factory) will inspect the selected `Strategy` and `GraphConfig`.
*   **Dynamic Injection:** Based on the strategy, the builder will instantiate the correct middleware implementations and inject them into the `WorkflowEngine`. The `RunExecutor` remains entirely agnostic to which middleware is being used.

### Problem 5: Database Structure for Manual Runs
**Current State:** The current models (`RunModel`, `ManualSession`, `ManualTurn`) need to be mapped correctly without duplicating the core v2.5 models (Attack, Defence, Evaluation).
**Solution: The Session "Chat Thread" Mapping Layer.**
*   **Re-use Core Models:** Continue using the existing `v2.5` Attack, Defence, and Evaluation models for all modes.
*   **The Session Paradigm:** Introduce/refine the `Session` concept. A Session acts as a sequence of interactions (like a chat thread).
*   **Data Hierarchy:**
    *   **Run:** The overarching container (1 Run -> Many Sessions).
    *   **Session:** Contains its own `Session ID`, stores a reference to its parent `Run ID`, and holds a list of Turns.
    *   **Turn:** A single tuple consisting of pointers to one Attack, Defence, and Evaluation step. 
*   **Reference Direction:** The Run does not store its Sessions. Sessions reference the Run ID. This ensures clean, queryable relationships without heavy nested objects.






<!-- # Architecture Refactoring Plan: Codebase Cleaning Tasks

This document outlines the identified problems in the current codebase and proposes actionable solutions for refactoring, focusing on decoupling, clarifying responsibilities, and adhering to a stateless request-response model for manual operations.

## Core Architectural Principles:

1.  **Stateless Request-Response for Manual Operations:** Manual runs are treated as single API request-response cycles. The graph executes one iteration, persists data, and returns. Subsequent manual interactions require new API calls.
2.  **Strategy-Driven Flow:** The `Strategy` object dictates the graph's execution behavior (continuous looping vs. single iteration) and routing decisions.
3.  **Clear Separation of Concerns:** 
    *   **RunExecutor/RunManager:** Manage run lifecycle, initialize `WorkflowEngine`; unaware of manual vs. automatic mode specifics.
    *   **WorkflowEngine:** Orchestrates graph execution via `astream`, manages middleware invocation.
    *   **GraphBuilder:** Constructs the graph topology, injects nodes and middleware based on `GraphConfig` and `Strategy`.
    *   **Middleware:** Exclusively handle persistence (`DatabaseMiddleware`) and event broadcasting (`WebSocketMiddleware`).
    *   **Nodes:** Perform specific actions within a graph step.
4.  **Middleware Selection Factory:** A factory (or GraphBuilder) injects appropriate middleware based on the `Strategy` and `GraphConfig`.

---

## Identified Problems and Proposed Solutions:

### 1. RunExecutor and RunManager Overloaded with Manual Flow Logic

*   **Problem:** These components currently handle manual attack logic, waiting, pausing, input management, and direct event emissions, violating separation of concerns.
*   **Current State:** Logic for manual waits (`_handle_manual_wait`), input providing (`provide_manual_input`), and direct WebSocket calls are present.
*   **Proposed Solution:
    *   **Remove Manual Logic:** Delete all code related to manual input handling, waiting states, and direct event emissions from `RunExecutor` and `RunManager`.
    *   **Enforce Statelessness:** Ensure these components only facilitate the standard request-response flow, initializing the `WorkflowEngine` and starting the graph execution (`astream`).
    *   **Refined Flow (Stateless Manual):
        1.  API Call → RunManager → RunExecutor → WorkflowEngine (configures graph with state/strategy).
        2.  WorkflowEngine uses `astream` to execute ONE graph iteration as dictated by the strategy.
        3.  Middleware persists data and broadcasts events for that iteration.
        4.  Graph execution completes; WorkflowEngine returns iteration result.
        5.  RunExecutor signals iteration completion; API returns response.
        6.  Next manual step requires a new API call. The 'pause' is implicit. -->
