#!/usr/bin/env python3
"""
GitLab Web App Analyzer - Regression Test Suite

This is a comprehensive test script that validates the GitLab Web App Analyzer's
detection accuracy and performance. It tests 34 web applications across multiple
frameworks and provides detailed reporting.

USAGE:
    python3 test-analyzer.py GITLAB_TOKEN

EXAMPLE:
    python3 test-analyzer.py glpat-xyz123

WHAT IT DOES:
    1. Runs the GitLab Web App Analyzer on all repositories
    2. Validates that 34 expected web applications are detected
    3. Calculates performance metrics (seconds per repo, projected time for 1000 repos)  
    4. Compares against 30-minute target for 1000 repositories
    5. Provides clear PASS/FAIL results for both detection and performance

OUTPUT:
    - Detection results: ✅/❌ for each application tested
    - Performance benchmark: Average time per repo and 1000-repo projection
    - Final result: SUCCESS/PARTIAL SUCCESS/FAILURE with clear explanations

EXIT CODES:
    0 = All tests passed (100% detection + performance target met)
    1 = Test failed (detection failed OR performance target exceeded)
"""

import subprocess
import csv
import time
import sys
from pathlib import Path
from datetime import datetime

# Configuration
GITLAB_URL = "https://gitlab.com"
OUTPUT_FILE = f"test-analyzer-results-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
PERFORMANCE_TARGET_MINUTES = 30.0
PERFORMANCE_TARGET_SECONDS_PER_REPO = 1.8

# Expected web applications (should all be detected as YES)
EXPECTED_APPS = [
    "test-laravel-invoice-ninja",
    "test-codeigniter-app", 
    "test-python-serverless",
    "test-go-serverless",
    "test-go-cms",
    "test-gin-rest-api",
    "test-symfony-demo",
    "test-quarkus-todo",
    "test-fastapi-fullstack",
    "test-django-cms",
    "test-blazor-application",
    "test-aspnet-clean-arch",
    "test-aspnet-ecommerce",
    "test-nodejs-serverless",
    "test-mean-stack",
    "test-express-ecommerce",
    "test-java-serverless",
    "test-spring-ecommerce",
    "test-spring-petclinic",
    # New .NET repositories added 2025-01-08
    "test-aspnet-core-webapi-sample",
    "test-aspnet-core-mvc-eshop",
    "test-blazor-server-efcore",
    "test-blazor-wasm-efcore",
    "test-aspnet-mvc5-ef6",
    "test-aspnet-webapi-legacy",
    "test-dotnet-minimal-api",
    "Umbraco CMS",
    "Dnn.Platform",
    "BlogEngine.NET",
    "NopCommerce",
    "OrchardCore",
    "Hippotech 2.0 Github",
    "WebGoat",
    "Juice Shop",
    "Gs Reactive Rest Service",
    "Node Express Realworld Example App",
    "Spring Petclinic",
    "Go Gin Example",
    "Laravel",
    "Flask",
    # Recent repositories added 2025-01-08
    "test-lambda-java8-dynamodb",
    "test-app-service-java-quickstart", 
    "test-play-java-starter-example",
    "test-spring-mvc-showcase"
]

def validate_prerequisites(gitlab_token):
    """Validate all prerequisites are met"""
    if not gitlab_token:
        print("Usage: python3 test-analyzer.py GITLAB_TOKEN")
        print("Example: python3 test-analyzer.py glpat-xyz123")
        return False
    
    if not Path("gitlab-web-app-analyzer.py").exists():
        print("Error: gitlab-web-app-analyzer.py not found")
        return False
    
    return True

def run_analyzer(gitlab_token):
    """Run the GitLab analyzer and return execution time"""
    print("Simple Enterprise Regression Test")
    print("=================================")
    print("Testing all web applications for detection (excluding deleted repos)")
    print()
    
    print("Running GitLab Web App Analyzer on all repositories...")
    
    start_time = time.time()
    
    try:
        subprocess.run([
            "python3", "gitlab-web-app-analyzer.py",
            "--gitlab-url", GITLAB_URL,
            "--token", gitlab_token,
            "--output", OUTPUT_FILE
        ], check=True, capture_output=False)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        print(f"Analyzer completed in {execution_time:.0f}s")
        print()
        
        return execution_time
        
    except subprocess.CalledProcessError as e:
        print(f"Error: Analyzer failed with exit code {e.returncode}")
        return None
    except FileNotFoundError:
        print("Error: python3 not found")
        return None

def parse_results():
    """Parse CSV results and return repository data"""
    if not Path(OUTPUT_FILE).exists():
        print(f"Error: Results file not found: {OUTPUT_FILE}")
        return None
    
    repositories = []
    try:
        with open(OUTPUT_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                repositories.append({
                    'name': row.get('Repository Name', ''),
                    'is_web_app': row.get('Is Web App', ''),
                    'confidence': row.get('Confidence Level', ''),
                    'web_app_type': row.get('Web App Type', ''),
                    'backend_framework': row.get('Backend Framework', '')
                })
        return repositories
    except Exception as e:
        print(f"Error parsing CSV file: {e}")
        return None

def check_detection_results(repositories):
    """Check detection results for expected applications"""
    print("Checking enterprise test applications:")
    print("======================================")
    
    passed = 0
    failed = 0
    failed_apps = []
    
    for app_name in EXPECTED_APPS:
        # Find this app in the results
        found = False
        for repo in repositories:
            if repo['name'] == app_name and repo['is_web_app'].upper() == 'YES':
                print(f"✅ {app_name}: DETECTED")
                passed += 1
                found = True
                break
        
        if not found:
            print(f"❌ {app_name}: NOT DETECTED")
            failed += 1
            failed_apps.append(app_name)
    
    total = len(EXPECTED_APPS)
    detection_rate = (passed * 100) // total if total > 0 else 0
    
    return {
        'total': total,
        'passed': passed, 
        'failed': failed,
        'detection_rate': detection_rate,
        'failed_apps': failed_apps
    }

def calculate_performance(execution_time, total_repos):
    """Calculate performance metrics"""
    if total_repos <= 0:
        total_repos = 1  # Prevent division by zero
    
    seconds_per_repo = execution_time / total_repos
    minutes_per_1000 = (seconds_per_repo * 1000) / 60
    performance_pass = seconds_per_repo <= PERFORMANCE_TARGET_SECONDS_PER_REPO
    
    return {
        'total_repos': total_repos,
        'seconds_per_repo': seconds_per_repo,
        'minutes_per_1000': minutes_per_1000,
        'performance_pass': performance_pass
    }

def display_results(detection_results, performance_results, execution_time):
    """Display comprehensive test results"""
    print()
    print("Summary:")
    print("========")
    print(f"Applications tested: {detection_results['total']}")
    print(f"Detected as web apps: {detection_results['passed']}")
    print(f"Not detected: {detection_results['failed']}")
    print(f"Detection rate: {detection_results['detection_rate']}%")
    print(f"Execution time: {execution_time:.0f}s")
    
    print()
    print("Performance Benchmark:")
    print("====================")
    print(f"Total repositories analyzed: {performance_results['total_repos']}")
    print(f"Average per repository: {performance_results['seconds_per_repo']:.2f}s")
    print(f"Projected for 1000 repos: {performance_results['minutes_per_1000']:.1f} minutes")
    print(f"Performance target: {PERFORMANCE_TARGET_MINUTES} minutes ({PERFORMANCE_TARGET_SECONDS_PER_REPO}s per repo)")
    
    if performance_results['performance_pass']:
        print("Performance result: ✅ PASS")
    else:
        print("Performance result: ❌ FAIL")
    
    print()
    
    # Final result
    detection_success = detection_results['failed'] == 0
    performance_success = performance_results['performance_pass']
    
    if detection_success and performance_success:
        print("🎉 SUCCESS: All tests passed!")
        print("✅ Detection: All enterprise applications detected (100%)")
        print("✅ Performance: Meets 30-minute target for 1000 repos")
        print("GitLab Web App Analyzer is working correctly.")
        return 0
    elif detection_success and not performance_success:
        print("⚠️  PARTIAL SUCCESS: Detection passed, performance failed")
        print("✅ Detection: All enterprise applications detected (100%)")
        print("❌ Performance: Exceeds 30-minute target for 1000 repos")
        print("Consider optimizing analyzer performance.")
        return 1
    else:
        print("❌ FAILURE: Detection test failed")
        print(f"❌ Detection: {detection_results['failed']} applications not detected")
        if not performance_success:
            print("❌ Performance: Exceeds 30-minute target for 1000 repos")
        else:
            print("✅ Performance: Meets 30-minute target for 1000 repos")
        
        if detection_results['failed_apps']:
            print()
            print("Please investigate the following:")
            print()
            print("Failed applications:")
            for app in detection_results['failed_apps']:
                print(f"  - {app}")
        
        print()
        print(f"Results saved to: {OUTPUT_FILE}")
        return 1

def main():
    """Main test execution"""
    # Get GitLab token from command line
    if len(sys.argv) != 2:
        print("Usage: python3 test-analyzer.py GITLAB_TOKEN")
        print("Example: python3 test-analyzer.py glpat-xyz123")
        return 1
    
    gitlab_token = sys.argv[1]
    
    # Validate prerequisites
    if not validate_prerequisites(gitlab_token):
        return 1
    
    # Run analyzer
    execution_time = run_analyzer(gitlab_token)
    if execution_time is None:
        return 1
    
    # Parse results
    repositories = parse_results()
    if repositories is None:
        return 1
    
    # Check detection results
    detection_results = check_detection_results(repositories)
    
    # Calculate performance metrics
    performance_results = calculate_performance(execution_time, len(repositories))
    
    # Display results and get exit code
    exit_code = display_results(detection_results, performance_results, execution_time)
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main())