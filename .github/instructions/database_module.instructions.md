# Database Module Instructions

## Purpose

This module is responsible for managing the MongoDB database, providing a structured interface for data storage and retrieval. It will serve as the central repository for session data, run information, and other persistent data required by the project.

## Key Responsibilities

*   **Database Connection**: Establish and manage a robust connection to the MongoDB instance.
*   **Data Modeling**: Define Mongoose schemas and models for various data entities, such as runs, sessions, attack payloads, responses, and evaluation results. These models should be well-structured for efficient querying and data integrity.
*   **CRUD Operations**: Implement clear interfaces for Create, Read, Update, and Delete operations on the defined models. These interfaces should abstract direct Mongoose calls to provide a cleaner, object-oriented way of interacting with the database.
*   **Object-Oriented Interface**: Develop an object-oriented approach to database interactions, making it easier for other modules to use the database services.
*   **Integration**: Facilitate seamless integration with the `alat-sessions` module and any other components that require data persistence.
*   **Configuration Management**: Retrieve database connection details (URL, credentials, etc.) from the `config.py` file. Sensitive information should be sourced from the `.env` file, while non-sensitive configurations can be directly defined in `config.py`.
*   **Database Client**: Implement `db_client.py` for asynchronous database operations using `motor`.

## Context and References

*   **ODM**: Use Mongoose as the Object Data Mapper (ODM) for MongoDB.
*   **Session Storage Integration**: This module will work closely with `alat-sessions/src/persistence/storage.py` and `alat-sessions/src/session_manager.py`.
*   **Configuration Source**: Database configurations will be loaded from `config.py`. Sensitive data (like passwords and API keys) should be read from the `.env` file. Non-sensitive configurations can be directly defined within `config.py`.
*   **Shared State**: Refer to `engine/src/core/state.py` for the `ArenaState` structure, which will guide the design of database models.
*   **Project Architecture**: Adhere to the general architectural guidelines in `engine/.github/copilot-instructions.md`.

## Working Directory

*   `AgenticLLMAdversarialTestbed/database/` (for core database logic and models)
*   `AgenticLLMAdversarialTestbed/engine/` (for integration points with Orchestrator and other modules)
*   `AgenticLLMAdversarialTestbed/config.py` (for configuration loading)
*   `AgenticLLMAdversarialTestbed/.env` (for sensitive environment variables)