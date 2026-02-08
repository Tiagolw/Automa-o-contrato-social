---
name: error-handling-patterns
description: Master error handling patterns across languages including exceptions, Result types, error propagation, and graceful degradation to build resilient applications. Use when implementing error handling, designing APIs, or improving application reliability.
---

# Error Handling Patterns

Build resilient applications with robust error handling strategies that gracefully handle failures and provide excellent debugging experiences.

## When to Use This Skill
- Implementing error handling in new features
- Designing error-resilient APIs
- Debugging production issues
- Improving application reliability
- Creating better error messages for users and developers
- Implementing retry and circuit breaker patterns
- Handling async/concurrent errors
- Building fault-tolerant distributed systems

## Core Concepts

### 1. Error Handling Philosophies

**Exceptions vs Result Types:**
- **Exceptions**: Traditional try-catch, disrupts control flow. (Use for: Unexpected errors, exceptional conditions)
- **Result Types**: Explicit success/failure, functional approach. (Use for: Expected errors, validation failures)
- **Error Codes**: C-style, requires discipline.
- **Option/Maybe Types**: For nullable values.
- **Panics/Crashes**: Unrecoverable errors, programming bugs.

### 2. Error Categories

**Recoverable Errors:**
- Network timeouts
- Missing files
- Invalid user input
- API rate limits

**Unrecoverable Errors:**
- Out of memory
- Stack overflow
- Programming bugs (null pointer, etc.)

## Language-Specific Patterns

### Python Error Handling

**Custom Exception Hierarchy:**
```python
class ApplicationError(Exception):
    """Base exception for all application errors."""
    def __init__(self, message: str, code: str = None, details: dict = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}
        self.timestamp = datetime.utcnow()

class ValidationError(ApplicationError): pass
class NotFoundError(ApplicationError): pass
class ExternalServiceError(ApplicationError):
    def __init__(self, message: str, service: str, **kwargs):
        super().__init__(message, **kwargs)
        self.service = service
```

**Context Managers for Cleanup:**
```python
@contextmanager
def database_transaction(session):
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()
```

**Retry with Exponential Backoff:**
```python
def retry(max_attempts=3, backoff_factor=2.0, exceptions=(Exception,)):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt < max_attempts - 1:
                        time.sleep(backoff_factor ** attempt)
                        continue
                    raise
            return None
        return wrapper
    return decorator
```

### TypeScript/JavaScript Error Handling

**Custom Error Classes:**
```typescript
class ApplicationError extends Error {
  constructor(
    message: string,
    public code: string,
    public statusCode: number = 500,
    public details?: Record<string, any>,
  ) {
    super(message);
    this.name = this.constructor.name;
    Error.captureStackTrace(this, this.constructor);
  }
}
```

**Result Type Pattern:**
```typescript
type Result<T, E = Error> = { ok: true; value: T } | { ok: false; error: E };
function Ok<T>(value: T): Result<T, never> { return { ok: true, value }; }
function Err<E>(error: E): Result<never, E> { return { ok: false, error }; }
```

**Async Error Handling:**
```typescript
async function fetchUserOrders(userId: string): Promise<Order[]> {
  try {
    const user = await getUser(userId);
    return await getOrders(user.id);
  } catch (error) {
    if (error instanceof NotFoundError) return [];
    if (error instanceof NetworkError) return retryFetchOrders(userId);
    throw error;
  }
}
```

### Rust Error Handling
**Result and Option Types:**
```rust
fn read_number_from_file(path: &str) -> Result<i32, AppError> {
    let contents = read_file(path)?;  // Auto-converts io::Error
    let number = contents.trim().parse()
        .map_err(AppError::Parse)?;   // Explicitly convert ParseIntError
    Ok(number)
}
```

### Go Error Handling
**Explicit Error Returns:**
```go
func getUser(id string) (*User, error) {
    user, err := db.QueryUser(id)
    if err != nil {
        return nil, fmt.Errorf("failed to query user: %w", err)
    }
    return user, nil
}
```

## Universal Patterns

### Pattern 1: Circuit Breaker
Prevent cascading failures in distributed systems.
```python
class CircuitBreaker:
    def call(self, func):
        if self.state == CircuitState.OPEN:
            raise Exception("Circuit breaker is OPEN")
        try:
            result = func()
            self.on_success()
            return result
        except Exception:
            self.on_failure()
            raise
```

### Pattern 2: Error Aggregation
Collect multiple errors instead of failing on first error.
```typescript
class ErrorCollector {
  private errors: Error[] = [];
  add(error: Error) { this.errors.push(error); }
  throw() {
    if (this.errors.length > 0) throw new AggregateError(this.errors);
  }
}
```

### Pattern 3: Graceful Degradation
Provide fallback functionality when errors occur.
```python
def get_user_profile(user_id):
    return with_fallback(
        primary=lambda: fetch_from_cache(user_id),
        fallback=lambda: fetch_from_database(user_id)
    )
```

## Best Practices
- **Fail Fast**: Validate input early, fail quickly
- **Preserve Context**: Include stack traces, metadata, timestamps
- **Meaningful Messages**: Explain what happened and how to fix it
- **Log Appropriately**: Error = log, expected failure = don't spam logs
- **Handle at Right Level**: Catch where you can meaningfully handle
- **Clean Up Resources**: Use try-finally, context managers, defer
- **Don't Swallow Errors**: Log or re-throw, don't silently ignore
- **Type-Safe Errors**: Use typed errors when possible

## Common Pitfalls
- Catching Too Broadly (`except Exception`)
- Empty Catch Blocks
- Logging AND Re-throwing (duplicate logs)
- Not Cleaning Up Resources
- Poor Error Messages ("Error occurred")
- Returning Error Codes instead of exceptions/Results
- Ignoring Async Errors

## Resources
- `references/exception-hierarchy-design.md`: Designing error class hierarchies
- `references/error-recovery-strategies.md`: Recovery patterns for different scenarios
- `references/async-error-handling.md`: Handling errors in concurrent code
- `assets/error-handling-checklist.md`: Review checklist for error handling
- `assets/error-message-guide.md`: Writing helpful error messages
- `scripts/error-analyzer.py`: Analyze error patterns in logs
