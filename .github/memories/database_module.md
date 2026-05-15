# Database Module Memory

## Purpose

This module provides the core database functionality for the Agentic Testing Ground project, enabling persistent storage of run data and related information.

## Functionality

*   **Connection Management**: Handles asynchronous connections to MongoDB using `motor` and `pymongo`.
*   **Configuration**: Reads database configuration from a provided dictionary or falls back to `config.py` (which uses environment variables and defaults).
*   **Collection Initialization**: Ensures that required MongoDB collections (`runs`, `attack_prompts`, `defense_responses`, `evaluation_results`) are created upon initialization.
*   **Data Models**: Utilizes Pydantic models defined in `db/models.py` for data validation within the application.

## Responsibilities

*   **Database Connection**: Establishing and managing the connection to MongoDB.
*   **Collection Access**: Providing access to initialized MongoDB collections.
*   **Schema Definition**: Defining Pydantic models for data structures (in `db/models.py`).

## Usage

*   The `initialize_database` function in `db/__init__.py` should be called during application startup to set up the database connection and collections.
*   CRUD operations (Create, Read, Update, Delete) for data are **not** handled by `db_client.py`. These operations should be implemented in modules that utilize the `DatabaseClient` (e.g., `api_gateway/services/engine_client.py`).
*   The `DatabaseClient` provides methods to get the database object and collection objects.

## References

*   `db/db_client.py`: Contains the `DatabaseClient` class for connection management.
*   `db/models.py`: Defines Pydantic models for data validation.
*   `db/__init__.py`: Contains the `initialize_database` function and collection creation logic.
*   `config.py`: Source for default database configuration.
