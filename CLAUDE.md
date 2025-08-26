# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DataLad Registry is a web service for registering and tracking DataLad datasets. It provides:
- REST API for dataset URL submission and retrieval
- Automated metadata extraction from DataLad datasets
- Integration with DataLad catalog and usage dashboard
- Support for read-only replica deployment

## Development Commands

### Testing
```bash
# Run tests with environment variables from env.test
(set -a && . ./env.test && set +a && python -m pytest -s -v)

# Run specific test file
(set -a && . ./env.test && set +a && python -m pytest -s -v path/to/test_file.py)

# Run with coverage
(set -a && . ./env.test && set +a && coverage run -m pytest && coverage report)
```

### Code Quality
```bash
# Format code with black
black datalad_registry datalad_registry_client

# Sort imports with isort
isort datalad_registry datalad_registry_client

# Run linting
flake8 datalad_registry datalad_registry_client

# Type checking
mypy datalad_registry datalad_registry_client

# Run all pre-commit hooks
pre-commit run --all-files

# Run codespell for typos
codespell datalad_registry
```

### Container Services

#### Test Environment
```bash
# Start test services
(set -a && . ./env.test && set +a && podman-compose -f docker-compose.test.yml up -d)

# Stop test services
(set -a && . ./env.test && set +a && podman-compose -f docker-compose.test.yml down)
```

#### Development Environment
```bash
# Start development services (requires .env.dev file)
(set -a && . ./.env.dev && set +a && podman-compose -f docker-compose.yml -f docker-compose.dev.override.yml up -d --build)

# Stop development services
(set -a && . ./.env.dev && set +a && podman-compose -f docker-compose.yml -f docker-compose.dev.override.yml down)
```

### Database Migrations
```bash
# Create new migration
flask db migrate -m "description of changes"

# Apply migrations
flask db upgrade

# Downgrade migration
flask db downgrade
```

## Architecture Overview

### Core Components

1. **Flask Application** (`datalad_registry/__init__.py`): Main web service using Flask-OpenAPI3 for automatic API documentation
2. **Celery Worker** (`datalad_registry/make_celery.py`): Background task processing for dataset metadata extraction
3. **Database Models** (`datalad_registry/models.py`): SQLAlchemy models for RepoUrl, UrlMetadata, and ExtractedMetadata
4. **API Blueprints** (`datalad_registry/blueprints/api/`): RESTful API endpoints for dataset operations

### Key Services

- **Web Service**: Flask application serving the API (port 5000)
- **Worker Service**: Celery worker for async task processing
- **Database**: PostgreSQL for persistent storage
- **Message Broker**: Redis for Celery task queue
- **Flower**: Celery monitoring dashboard (optional)

### Environment Configuration

The application uses environment variables for configuration, managed through:
- `template.env`: Template for creating environment files
- `env.test`: Test environment configuration
- `.env.dev`: Development environment (created from template.env)
- `.env.read-only`: Read-only replica configuration

Key environment variables:
- `DATALAD_REGISTRY_OPERATION_MODE`: PRODUCTION, DEVELOPMENT, or READ_ONLY
- `SQLALCHEMY_DATABASE_URI`: PostgreSQL connection string
- `CELERY_BROKER_URL`: Redis broker URL
- `DATALAD_REGISTRY_DATASET_CACHE`: Path for caching cloned datasets

### Task Processing Flow

1. URL submission triggers `url_chk_dispatcher` task
2. Dispatcher validates URL and creates `process_dataset_url` task
3. Dataset is cloned and metadata extracted via `extract_ds_meta`
4. Extracted metadata stored in database with relationships to RepoUrl

### DataLad Client Extension

The `datalad_registry_client` package provides a DataLad extension for interacting with the registry:
- `datalad registry-submit-urls`: Submit dataset URLs
- `datalad registry-get-urls`: Retrieve registered URLs

## Testing Considerations

- Tests use `env.test` configuration with separate containers
- Database is ephemeral for test runs
- Use `@pytest.mark.devserver` for tests requiring Flask dev server
- Use `@pytest.mark.slow` for long-running tests
- Test fixtures available in `conftest.py` files

## Important Notes

- Always use absolute paths in Docker volume mounts
- The `./instance` directory is the Flask instance folder for configuration
- Worker service doesn't auto-reload on code changes (requires restart)
- Pre-commit hooks automatically fix formatting issues - commit again if they modify files
