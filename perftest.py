#!/usr/bin/env python3
"""
Performance Testing Script for GitLab Web App Analyzer

Analyzes runtime performance per app type (.NET, Java, Node.js, etc.) with detailed
metrics on API calls, processing time, and bottlenecks to optimize for 1000-repo scanning.
"""

import csv
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

import click

# Import the enhanced analyzer
import importlib.util
import sys

# Load the analyzer module from the hyphenated filename
spec = importlib.util.spec_from_file_location("gitlab_web_app_analyzer", "gitlab-web-app-analyzer.py")
analyzer_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyzer_module)

# Import the classes we need
GitLabAnalyzer = analyzer_module.GitLabAnalyzer


class PerformanceReporter:
    """Generates detailed performance reports"""
    
    def __init__(self, analyzer: GitLabAnalyzer):
        self.analyzer = analyzer
        self.target_total_repos = 1000
        self.target_total_time = 30 * 60  # 30 minutes in seconds
        
    def generate_report(self, results: List[Dict], total_time: float) -> str:
        """Generate comprehensive performance report"""
        performance_summary = self.analyzer.performance_tracker.get_summary()
        
        report_lines = [
            "=" * 80,
            "GitLab Web App Analyzer - Performance Test Report",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 80,
            "",
            "EXECUTIVE SUMMARY",
            "-" * 40,
            f"Repositories analyzed: {len(results)}",
            f"Total execution time: {total_time:.1f}s",
            f"Average time per repo: {total_time/len(results):.2f}s",
            f"Total API calls: {performance_summary['total_api_calls']}",
            f"Total API time: {performance_summary['total_api_time']:.1f}s",
            f"API overhead: {(performance_summary['total_api_time']/total_time)*100:.1f}%",
            "",
            "1000-REPO PROJECTION",
            "-" * 40,
        ]
        
        # Calculate projections
        avg_time_per_repo = total_time / len(results)
        projected_total_time = avg_time_per_repo * self.target_total_repos
        projected_minutes = projected_total_time / 60
        
        report_lines.extend([
            f"Projected time for 1000 repos: {projected_total_time:.0f}s ({projected_minutes:.1f} minutes)",
            f"Target time (30 minutes): {'✅ ACHIEVABLE' if projected_minutes <= 30 else '❌ TOO SLOW'}",
            f"Speed improvement needed: {(projected_minutes/30):.1f}x" if projected_minutes > 30 else "Current speed is sufficient",
        ])
        
        # API call breakdown
        report_lines.extend([
            "",
            "API CALL BREAKDOWN",
            "-" * 40,
        ])
        
        for call_type, metrics in performance_summary['api_calls_by_type'].items():
            if metrics['count'] > 0:
                avg_time = metrics['total_time'] / metrics['count']
                report_lines.append(
                    f"{call_type.ljust(15)}: {metrics['count']:4d} calls, "
                    f"{metrics['total_time']:6.1f}s total, {avg_time:.3f}s avg"
                )
        
        # Performance by app type
        report_lines.extend([
            "",
            "PERFORMANCE BY APP TYPE",
            "-" * 40,
            f"{'App Type'.ljust(20)} {'Count'.rjust(5)} {'Avg Time'.rjust(10)} {'API Calls'.rjust(10)} {'API Time'.rjust(10)} {'Analysis'.rjust(10)}",
            "-" * 75,
        ])
        
        app_type_metrics = performance_summary['app_type_metrics']
        
        # Sort by average time (slowest first)
        sorted_app_types = sorted(
            app_type_metrics.items(),
            key=lambda x: x[1]['total_time'] / x[1]['count'],
            reverse=True
        )
        
        for app_type, metrics in sorted_app_types:
            count = metrics['count']
            avg_total_time = metrics['total_time'] / count
            total_api_calls = sum(api_metrics['count'] for api_metrics in metrics['api_calls'].values())
            avg_api_calls = total_api_calls / count
            total_api_time = sum(api_metrics['total_time'] for api_metrics in metrics['api_calls'].values())
            avg_api_time = total_api_time / count
            avg_analysis_time = metrics['analysis_time'] / count
            
            report_lines.append(
                f"{app_type.ljust(20)} {count:5d} {avg_total_time:8.2f}s {avg_api_calls:8.1f} {avg_api_time:8.2f}s {avg_analysis_time:8.2f}s"
            )
        
        # Detailed API breakdown by app type
        report_lines.extend([
            "",
            "DETAILED API BREAKDOWN BY APP TYPE",
            "-" * 40,
        ])
        
        for app_type, metrics in sorted_app_types:
            report_lines.extend([
                f"",
                f"{app_type} ({metrics['count']} repos):",
            ])
            
            for call_type, api_metrics in metrics['api_calls'].items():
                if api_metrics['count'] > 0:
                    avg_calls = api_metrics['count'] / metrics['count']
                    avg_time = api_metrics['total_time'] / api_metrics['count']
                    avg_total_time = api_metrics['total_time'] / metrics['count']
                    report_lines.append(
                        f"  {call_type.ljust(12)}: {avg_calls:5.1f} calls/repo, "
                        f"{avg_time:.3f}s/call, {avg_total_time:.2f}s/repo"
                    )
        
        # Optimization recommendations
        report_lines.extend([
            "",
            "OPTIMIZATION RECOMMENDATIONS",
            "-" * 40,
        ])
        
        # Find slowest API call types
        api_call_times = [(call_type, metrics['total_time']/metrics['count']) 
                         for call_type, metrics in performance_summary['api_calls_by_type'].items() 
                         if metrics['count'] > 0]
        api_call_times.sort(key=lambda x: x[1], reverse=True)
        
        if projected_minutes > 30:
            report_lines.extend([
                f"⚠️  Current speed is {(projected_minutes/30):.1f}x too slow for 30-minute target",
                "",
                "Priority optimizations:",
            ])
            
            # Recommend optimizations based on data
            slowest_api = api_call_times[0] if api_call_times else None
            if slowest_api:
                report_lines.append(f"1. Optimize '{slowest_api[0]}' calls (avg {slowest_api[1]:.3f}s each)")
            
            # Find app types with most API calls
            highest_api_usage = max(
                [(app_type, sum(api_metrics['count'] for api_metrics in metrics['api_calls'].values()) / metrics['count'])
                 for app_type, metrics in app_type_metrics.items()],
                key=lambda x: x[1]
            ) if app_type_metrics else None
            
            if highest_api_usage:
                report_lines.append(f"2. Reduce API calls for {highest_api_usage[0]} (avg {highest_api_usage[1]:.1f} calls/repo)")
            
            report_lines.extend([
                "3. Consider parallel processing for file content retrieval",
                "4. Implement aggressive caching for repeated API calls",
                "5. Optimize file discovery with targeted patterns",
            ])
        else:
            report_lines.extend([
                "✅ Current performance meets 30-minute target!",
                "",
                "Potential optimizations for even better performance:",
                "1. Further reduce file tree traversal depth",
                "2. Cache project metadata across runs",
                "3. Implement smarter early termination",
            ])
        
        report_lines.extend([
            "",
            "=" * 80,
        ])
        
        return "\n".join(report_lines)


def get_test_repos_by_type(all_repos: List[Any], app_type_filter: Optional[str] = None, max_per_type: int = 3) -> List[Any]:
    """Get a subset of repos for testing, optionally filtered by app type"""
    if app_type_filter:
        # For specific app type testing, we need to use known repo names
        # This is a simplified approach - in practice you'd want a more sophisticated mapping
        app_type_patterns = {
            '.NET': ['dotnet', 'aspnet', 'blazor'],
            'Java': ['java', 'spring', 'quarkus'],
            'Node.js': ['nodejs', 'express', 'mean'],
            'Python': ['python', 'django', 'flask', 'fastapi'],
            'PHP': ['php', 'laravel', 'symfony'],
            'Go': ['go', 'gin']
        }
        
        patterns = app_type_patterns.get(app_type_filter, [])
        filtered_repos = []
        for repo in all_repos:
            repo_name_lower = repo.name.lower()
            if any(pattern in repo_name_lower for pattern in patterns):
                filtered_repos.append(repo)
        
        return filtered_repos[:max_per_type * 3]  # Get more repos for specific type testing
    
    # For general testing, get a balanced subset
    test_repos = []
    app_type_patterns = {
        '.NET': ['dotnet', 'aspnet', 'blazor'],
        'Java': ['java', 'spring', 'quarkus'],
        'Node.js': ['nodejs', 'express', 'mean'],
        'Python': ['python', 'django', 'flask', 'fastapi'],
        'PHP': ['php', 'laravel', 'symfony'],
        'Go': ['go', 'gin']
    }
    
    for app_type, patterns in app_type_patterns.items():
        type_repos = []
        for repo in all_repos:
            repo_name_lower = repo.name.lower()
            if any(pattern in repo_name_lower for pattern in patterns):
                type_repos.append(repo)
                if len(type_repos) >= max_per_type:
                    break
        test_repos.extend(type_repos)
    
    return test_repos


@click.command()
@click.option('--gitlab-url', help='GitLab instance URL')
@click.option('--token', help='Personal access token')
@click.option('--mode', type=click.Choice(['small', 'full', 'app-type']), default='small', 
              help='Test mode: small (subset), full (all repos), app-type (specific type)')
@click.option('--app-type', help='Specific app type to test (when mode=app-type)')
@click.option('--output', help='Output report filename')
@click.option('--max-per-type', default=3, help='Max repos per app type for small test (default: 3)')
@click.option('--rate-limit', default=20.0, help='Requests per second (default: 20)')
@click.option('--debug', is_flag=True, help='Enable debug logging')
@click.option('--no-rate-limit', is_flag=True, help='Disable rate limiting (for testing)')
def main(gitlab_url, token, mode, app_type, output, max_per_type, rate_limit, debug, no_rate_limit):
    """Performance testing for GitLab Web App Analyzer"""
    
    # Generate default output filename if not provided
    if not output:
        timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
        output = f'perftest-report-{mode}-{timestamp}.txt'
    
    # Get GitLab URL from environment if not provided
    if not gitlab_url:
        gitlab_url = os.getenv('GITLAB_URL')
        if not gitlab_url:
            raise click.ClickException("GitLab URL must be provided via --gitlab-url or GITLAB_URL environment variable")
    
    # Get token from environment if not provided
    if not token:
        token = os.getenv('GITLAB_TOKEN')
    
    click.echo(f"Starting GitLab Performance Test...")
    click.echo(f"GitLab URL: {gitlab_url}")
    click.echo(f"Test mode: {mode}")
    if app_type:
        click.echo(f"App type filter: {app_type}")
    click.echo(f"Rate limit: {rate_limit} requests/second")
    click.echo(f"Output file: {output}")
    
    try:
        # Initialize analyzer with performance tracking enabled
        analyzer = GitLabAnalyzer(gitlab_url, token, rate_limit, debug, search_depth=2, enable_performance_tracking=True)
        
        # Set no_rate_limit flag for testing
        if no_rate_limit:
            analyzer.no_rate_limit = True
            click.echo("Rate limiting disabled for testing")
        
        # Get repositories
        click.echo("Fetching repositories...")
        all_repositories = analyzer.get_repositories()
        click.echo(f"Found {len(all_repositories)} total repositories")
        
        # Select test repositories based on mode
        if mode == 'small':
            repositories = get_test_repos_by_type(all_repositories, max_per_type=max_per_type)
            click.echo(f"Selected {len(repositories)} repositories for balanced testing")
        elif mode == 'app-type':
            if not app_type:
                raise click.ClickException("--app-type must be specified when mode=app-type")
            repositories = get_test_repos_by_type(all_repositories, app_type_filter=app_type)
            click.echo(f"Selected {len(repositories)} repositories for {app_type} testing")
        else:  # full
            repositories = all_repositories
            click.echo(f"Testing all {len(repositories)} repositories")
        
        if not repositories:
            raise click.ClickException("No repositories found for testing")
        
        # Analyze repositories with performance tracking
        results = []
        test_start_time = time.time()
        
        with click.progressbar(repositories, label='Analyzing repositories') as repos:
            for repo in repos:
                result = analyzer.analyze_repository(repo)
                results.append(result)
        
        test_total_time = time.time() - test_start_time
        
        # Generate performance report
        click.echo(f"Generating performance report...")
        reporter = PerformanceReporter(analyzer)
        report = reporter.generate_report(results, test_total_time)
        
        # Write report to file
        with open(output, 'w', encoding='utf-8') as f:
            f.write(report)
        
        # Display summary to console
        click.echo("\nPERFORMance TEST COMPLETE!")
        click.echo(f"Report saved to: {output}")
        click.echo("-" * 50)
        
        # Show key metrics
        performance_summary = analyzer.performance_tracker.get_summary()
        avg_time_per_repo = test_total_time / len(results)
        projected_total_time = avg_time_per_repo * 1000
        projected_minutes = projected_total_time / 60
        
        click.echo(f"Repositories analyzed: {len(results)}")
        click.echo(f"Total time: {test_total_time:.1f}s")
        click.echo(f"Average per repo: {avg_time_per_repo:.2f}s")
        click.echo(f"Total API calls: {performance_summary['total_api_calls']}")
        click.echo(f"API time: {performance_summary['total_api_time']:.1f}s")
        click.echo(f"1000-repo projection: {projected_minutes:.1f} minutes")
        
        if projected_minutes <= 30:
            click.echo("✅ 30-minute target: ACHIEVABLE")
        else:
            click.echo(f"❌ 30-minute target: Need {(projected_minutes/30):.1f}x speed improvement")
        
        click.echo(f"\nFull details in: {output}")
        
    except Exception as e:
        raise click.ClickException(f"Performance test failed: {e}")


if __name__ == '__main__':
    main()