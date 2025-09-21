"""
Centralized logging utilities with JSON formatting
"""

import json
import logging
import sys
from typing import Dict, Any, Optional
from datetime import datetime, UTC

from db.session import get_db_session

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    
    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, 'extra_data'):
            log_entry.update(record.extra_data)
        
        return json.dumps(log_entry)

def get_logger(name: str) -> logging.Logger:
    """Get a logger with JSON formatting"""
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    
    return logger

def log_to_database(
    session: Any,
    kind: str,
    message: str,
    metadata: Optional[Dict[str, Any]] = None
):
    """Log an action to the database"""
    try:
        from db.models import Action
        
        action = Action(
            kind=kind,
            meta_json={
                "message": message,
                "timestamp": datetime.now(UTC).isoformat(),
                **(metadata or {})
            }
        )
        
        session.add(action)
        session.commit()
        
    except Exception as e:
        # Don't let logging errors break the application
        logger = get_logger(__name__)
        logger.error(f"Failed to log to database: {e}")

class DatabaseLogHandler(logging.Handler):
    """Custom log handler that writes to database"""
    
    def __init__(self, level=logging.WARNING):
        super().__init__(level)
        self.logger = get_logger(__name__)
    
    def emit(self, record):
        try:
            # Only log warnings and errors to database
            if record.levelno >= logging.WARNING:
                with get_db_session() as session:
                    log_to_database(
                        session,
                        kind=f"log_{record.levelname.lower()}",
                        message=record.getMessage(),
                        metadata={
                            "module": record.module,
                            "function": record.funcName,
                            "line": record.lineno,
                            "level": record.levelname
                        }
                    )
        except Exception as e:
            # Prevent logging loops
            self.logger.error(f"Database logging failed: {e}")

def setup_database_logging():
    """Set up database logging for warnings and errors"""
    root_logger = logging.getLogger()

    # Prevent attaching multiple handlers during reloads
    if any(isinstance(h, DatabaseLogHandler) for h in root_logger.handlers):
        return

    db_handler = DatabaseLogHandler()
    root_logger.addHandler(db_handler)

class StructuredLogger:
    """Enhanced logger with structured data support"""
    
    def __init__(self, name: str):
        self.logger = get_logger(name)
        self.name = name
    
    def info(self, message: str, **kwargs):
        """Log info with structured data"""
        extra_data = {"extra_data": kwargs} if kwargs else {}
        self.logger.info(message, extra=extra_data)
    
    def warning(self, message: str, **kwargs):
        """Log warning with structured data"""
        extra_data = {"extra_data": kwargs} if kwargs else {}
        self.logger.warning(message, extra=extra_data)
    
    def error(self, message: str, **kwargs):
        """Log error with structured data"""
        extra_data = {"extra_data": kwargs} if kwargs else {}
        self.logger.error(message, extra=extra_data)
    
    def debug(self, message: str, **kwargs):
        """Log debug with structured data"""
        extra_data = {"extra_data": kwargs} if kwargs else {}
        self.logger.debug(message, extra=extra_data)
    
    def action(self, action_type: str, message: str, **metadata):
        """Log an action with database storage"""
        self.info(f"Action: {action_type} - {message}", action_type=action_type, **metadata)
        
        # Also store in database
        try:
            with get_db_session() as session:
                log_to_database(
                    session,
                    kind=action_type,
                    message=message,
                    metadata=metadata
                )
        except Exception as e:
            self.error(f"Failed to log action to database: {e}")
    
    def performance(self, operation: str, duration: float, **metadata):
        """Log performance metrics"""
        self.info(
            f"Performance: {operation} took {duration:.2f}s",
            operation=operation,
            duration=duration,
            **metadata
        )
    
    def analytics(self, metric: str, value: float, **metadata):
        """Log analytics data"""
        self.info(
            f"Analytics: {metric} = {value}",
            metric=metric,
            value=value,
            **metadata
        )

def get_structured_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance"""
    return StructuredLogger(name)

# Performance monitoring decorator
def log_performance(logger_name: str = None):
    """Decorator to log function performance"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            import time
            
            logger = get_logger(logger_name or func.__module__)
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                logger.info(
                    f"Performance: {func.__name__} completed in {duration:.2f}s",
                    extra={
                        "extra_data": {
                            "function": func.__name__,
                            "duration": duration,
                            "success": True
                        }
                    }
                )
                
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                
                logger.error(
                    f"Performance: {func.__name__} failed after {duration:.2f}s: {e}",
                    extra={
                        "extra_data": {
                            "function": func.__name__,
                            "duration": duration,
                            "success": False,
                            "error": str(e)
                        }
                    }
                )
                raise
        
        return wrapper
    return decorator

# Initialize database logging on import
setup_database_logging()

