#!/usr/bin/env python3
"""
Performance Tracking Module for GitLab Web App Analyzer

Provides optional performance tracking with minimal integration overhead.
Supports decorators and context managers for clean code integration.
"""

import time
from contextlib import contextmanager
from functools import wraps
from typing import Dict, List, Optional, Any, Callable


class PerformanceTracker:
    """Tracks performance metrics for GitLab analyzer"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset all metrics"""
        self.api_calls = {
            'project_list': {'count': 0, 'total_time': 0.0},
            'project_info': {'count': 0, 'total_time': 0.0},
            'languages': {'count': 0, 'total_time': 0.0},
            'file_tree': {'count': 0, 'total_time': 0.0},
            'file_content': {'count': 0, 'total_time': 0.0},
            'other': {'count': 0, 'total_time': 0.0}
        }
        self.repo_metrics = {}  # repo_name -> metrics dict
        self.app_type_metrics = {}  # app_type -> aggregated metrics
        self.current_repo_name = None
    
    def track_api_call(self, call_type: str, duration: float):
        """Track an API call by type and duration"""
        if call_type not in self.api_calls:
            call_type = 'other'
        
        self.api_calls[call_type]['count'] += 1
        self.api_calls[call_type]['total_time'] += duration
    
    def track_repo_api_call(self, repo_name: str, call_type: str, duration: float):
        """Track an API call for a specific repository"""
        if repo_name in self.repo_metrics:
            if call_type not in self.repo_metrics[repo_name]['api_calls']:
                call_type = 'other'
            self.repo_metrics[repo_name]['api_calls'][call_type]['count'] += 1
            self.repo_metrics[repo_name]['api_calls'][call_type]['total_time'] += duration
    
    def start_repo_analysis(self, repo_name: str):
        """Start tracking metrics for a repository"""
        self.current_repo_name = repo_name
        self.repo_metrics[repo_name] = {
            'start_time': time.time(),
            'api_calls': {k: {'count': 0, 'total_time': 0.0} for k in self.api_calls.keys()},
            'analysis_time': 0.0,
            'total_time': 0.0,
            'app_type': None
        }
    
    def finish_repo_analysis(self, repo_name: str, app_type: str, analysis_time: float):
        """Finish tracking metrics for a repository"""
        if repo_name in self.repo_metrics:
            repo_metrics = self.repo_metrics[repo_name]
            repo_metrics['total_time'] = time.time() - repo_metrics['start_time']
            repo_metrics['analysis_time'] = analysis_time
            repo_metrics['app_type'] = app_type
            
            # Aggregate by app type
            if app_type not in self.app_type_metrics:
                self.app_type_metrics[app_type] = {
                    'count': 0,
                    'total_time': 0.0,
                    'analysis_time': 0.0,
                    'api_calls': {k: {'count': 0, 'total_time': 0.0} for k in self.api_calls.keys()}
                }
            
            app_metrics = self.app_type_metrics[app_type]
            app_metrics['count'] += 1
            app_metrics['total_time'] += repo_metrics['total_time']
            app_metrics['analysis_time'] += repo_metrics['analysis_time']
            
            for call_type, metrics in repo_metrics['api_calls'].items():
                app_metrics['api_calls'][call_type]['count'] += metrics['count']
                app_metrics['api_calls'][call_type]['total_time'] += metrics['total_time']
        
        self.current_repo_name = None
    
    @contextmanager
    def track_repository(self, repo_name: str):
        """Context manager for repository analysis tracking"""
        self.start_repo_analysis(repo_name)
        analysis_start_time = time.time()
        
        class RepoTracker:
            def __init__(self, tracker, repo_name):
                self.tracker = tracker
                self.repo_name = repo_name
                self.analysis_start_time = analysis_start_time
            
            def finish(self, app_type: str):
                """Finish tracking with app type"""
                analysis_time = time.time() - self.analysis_start_time
                self.tracker.finish_repo_analysis(self.repo_name, app_type, analysis_time)
        
        try:
            yield RepoTracker(self, repo_name)
        except Exception:
            # Ensure cleanup even on error
            analysis_time = time.time() - analysis_start_time
            self.finish_repo_analysis(repo_name, 'Error', analysis_time)
            raise
    
    @contextmanager
    def track_api_call_context(self, call_type: str, debug: bool = False):
        """Context manager for API call tracking"""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.track_api_call(call_type, duration)
            if self.current_repo_name:
                self.track_repo_api_call(self.current_repo_name, call_type, duration)
            
            if debug:
                print(f"DEBUG: API call '{call_type}' took {duration:.3f}s")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary"""
        total_api_calls = sum(metrics['count'] for metrics in self.api_calls.values())
        total_api_time = sum(metrics['total_time'] for metrics in self.api_calls.values())
        
        return {
            'total_api_calls': total_api_calls,
            'total_api_time': total_api_time,
            'api_calls_by_type': self.api_calls,
            'app_type_metrics': self.app_type_metrics,
            'repo_count': len(self.repo_metrics)
        }


class NoOpTracker:
    """No-operation performance tracker for when tracking is disabled"""
    
    def __init__(self):
        pass
    
    def reset(self):
        pass
    
    def track_api_call(self, call_type: str, duration: float):
        pass
    
    def track_repo_api_call(self, repo_name: str, call_type: str, duration: float):
        pass
    
    def start_repo_analysis(self, repo_name: str):
        pass
    
    def finish_repo_analysis(self, repo_name: str, app_type: str, analysis_time: float):
        pass
    
    @contextmanager
    def track_repository(self, repo_name: str):
        """No-op context manager"""
        class NoOpRepoTracker:
            def finish(self, app_type: str):
                pass
        
        yield NoOpRepoTracker()
    
    @contextmanager
    def track_api_call_context(self, call_type: str, debug: bool = False):
        """No-op context manager"""
        yield
    
    def get_summary(self) -> Dict[str, Any]:
        """Return empty summary"""
        return {
            'total_api_calls': 0,
            'total_api_time': 0.0,
            'api_calls_by_type': {},
            'app_type_metrics': {},
            'repo_count': 0
        }


def create_performance_tracker(enabled: bool = False) -> PerformanceTracker:
    """Factory function to create appropriate tracker based on enabled flag"""
    return PerformanceTracker() if enabled else NoOpTracker()


def track_api_call(call_type: str):
    """Decorator for automatic API call tracking"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Only track if analyzer has performance_tracker and it's enabled
            if hasattr(self, 'performance_tracker') and hasattr(self.performance_tracker, 'track_api_call_context'):
                with self.performance_tracker.track_api_call_context(call_type, getattr(self, 'debug', False)):
                    return func(self, *args, **kwargs)
            else:
                return func(self, *args, **kwargs)
        return wrapper
    return decorator


def enhance_api_call_with_retry(original_method: Callable) -> Callable:
    """Enhance the _api_call_with_retry method to support performance tracking"""
    @wraps(original_method)
    def enhanced_method(self, api_call, max_retries=3, call_type='other'):
        # If performance tracking is enabled, use context manager
        if hasattr(self, 'performance_tracker') and hasattr(self.performance_tracker, 'track_api_call_context'):
            with self.performance_tracker.track_api_call_context(call_type, getattr(self, 'debug', False)):
                # Call original method without call_type parameter (it's not in original signature)
                return original_method(self, api_call, max_retries)
        else:
            # Call original method without modification
            return original_method(self, api_call, max_retries)
    
    return enhanced_method